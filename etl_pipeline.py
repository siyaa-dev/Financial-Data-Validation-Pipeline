import json
import mysql.connector
from mysql.connector import Error
import numpy as np
import pandas as pd


class FinancialETLPipeline:

  def __init__(self, db_config: dict):
    self.db_config = db_config
    self.connection = None
    self.exceptions = []

  def connect(self):
    """Establishes connection to the MySQL database."""
    try:
      self.connection = mysql.connector.connect(**self.db_config)
      if self.connection.is_connected():
        print("Connected to MySQL Server successfully.")
    except Error as e:
      print(f"Database Connection Error: {e}")
      raise

  def seed_master_data(self):
    """Populates master investors and funds for foreign key validation."""
    cursor = self.connection.cursor()

    # Clear previous run's exceptions before committing new batch
    cursor.execute("TRUNCATE TABLE reconciliation_exceptions;")

    investor_query = """
        INSERT INTO investors (investor_id, legal_name, investor_type, kyc_status, contact_email)
        VALUES (%s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE legal_name=VALUES(legal_name);
        """
    investors_data = [
        (
            "INV-1001",
            "Blackstone Alpha Corp",
            "Institutional",
            "VERIFIED",
            "ops@blackstone.com",
        ),
        (
            "INV-1002",
            "Apex Global Holdings",
            "Institutional",
            "VERIFIED",
            "settlements@apex.com",
        ),
        (
            "INV-1003",
            "Vanguard Offshore Fund",
            "Institutional",
            "VERIFIED",
            "admin@vanguard.com",
        ),
        (
            "INV-1004",
            "Meridian Capital Partners",
            "High-Net-Worth",
            "VERIFIED",
            "ir@meridian.com",
        ),
    ]
    cursor.executemany(investor_query, investors_data)

    fund_query = """
        INSERT INTO funds (fund_id, fund_name, currency, nav_per_unit)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE nav_per_unit=VALUES(nav_per_unit);
        """
    funds_data = [
        ("FUND-ALPHA", "D. E. Shaw Horizon Fund", "USD", 1250.50),
        ("FUND-BETA", "D. E. Shaw Core Alpha Fund", "USD", 840.25),
    ]
    cursor.executemany(fund_query, funds_data)

    self.connection.commit()
    cursor.close()
    print("Master investors and funds verified in MySQL.")

  def fetch_reference_data(self):
    cursor = self.connection.cursor(dictionary=True)

    cursor.execute("SELECT investor_id FROM investors WHERE kyc_status = 'VERIFIED'")
    valid_investors = {row['investor_id'] for row in cursor.fetchall()}

    cursor.execute("SELECT fund_id, nav_per_unit FROM funds WHERE status = 'ACTIVE'")
    funds_map = {row['fund_id']: row['nav_per_unit'] for row in cursor.fetchall()}

    cursor.close()
    return valid_investors, funds_map

  def extract_and_transform(self, raw_filepath: str) -> pd.DataFrame:
    """Extracts raw CRM feed and applies string/numeric transformations."""
    df = pd.read_csv(raw_filepath)

    # 1. Deduplication on raw reference IDs
    df = df.drop_duplicates(subset=["txn_ref"], keep="first")

    # 2. String trimming and case normalization
    df["txn_ref"] = (
        df["txn_ref"].astype(str).str.strip().str.upper().replace("NAN", "")
    )
    df["investor_id"] = (
        df["investor_id"]
        .astype(str)
        .str.strip()
        .str.upper()
        .replace("NAN", "")
    )
    df["fund_code"] = (
        df["fund_code"].astype(str).str.strip().str.upper().replace("NAN", "")
    )
    df["type"] = df["type"].astype(str).str.strip().str.upper().replace("NAN", "")

    # 3. Clean monetary amounts
    def parse_currency(val):
      if pd.isna(val):
        return np.nan
      cleaned = str(val).replace("$", "").replace(",", "").strip()
      try:
        return float(cleaned)
      except ValueError:
        return np.nan

    df["amount"] = df["amount"].apply(parse_currency)

    # 4. Standardize dates to ISO YYYY-MM-DD
    df['trade_date'] = pd.to_datetime(
    df['trade_date'], format='mixed', dayfirst=True, errors='coerce'
    )
    df['settle_date'] = pd.to_datetime(
        df['settle_date'], format='mixed', dayfirst=True, errors='coerce'
    )

    return df

  def validate_records(
      self, df: pd.DataFrame, valid_investors: set, funds_map: dict
  ) -> pd.DataFrame:
    """Applies institutional validation rules and categorizes exceptions."""
    valid_rows = []

    for _, row in df.iterrows():
      errors = []

      # Referential Integrity check
      if row["investor_id"] not in valid_investors:
        errors.append((
            "ERR_UNREGISTERED_INVESTOR",
            f"Investor {row['investor_id']} missing or unverified",
        ))
      if row["fund_code"] not in funds_map:
        errors.append(
            ("ERR_INVALID_FUND", f"Fund code {row['fund_code']} does not exist")
        )

      # Boundary conditions
      if pd.isna(row["amount"]) or row["amount"] <= 0:
        errors.append((
            "ERR_INVALID_AMOUNT",
            f"Non-positive or null amount: {row['amount']}",
        ))

      # Chronological checks
      if pd.isna(row["trade_date"]) or pd.isna(row["settle_date"]):
        errors.append(
            ("ERR_MALFORMED_DATE", "Failed to parse trade or settlement date")
        )
      elif row["settle_date"] < row["trade_date"]:
        errors.append((
            "ERR_DATE_CHRONOLOGY",
            f"Settlement date ({row['settle_date'].strftime('%Y-%m-%d')})"
            f" precedes trade date ({row['trade_date'].strftime('%Y-%m-%d')})",
        ))

      # Action types
      if row["type"] not in ["SUBSCRIPTION", "REDEMPTION", "TRANSFER"]:
        errors.append(
            ("ERR_UNKNOWN_ACTION", f"Unrecognized trade action: {row['type']}")
        )

      if errors:
        for code, desc in errors:
          self.exceptions.append((
              row["txn_ref"],
              code,
              desc,
              json.dumps(row.to_dict(), default=str),
          ))
      else:
        nav = funds_map[row["fund_code"]]
        units = round(row["amount"] / float(nav), 4)
        valid_rows.append((
            row["txn_ref"],
            row["investor_id"],
            row["fund_code"],
            row["type"],
            float(row["amount"]),
            float(units),
            row["trade_date"].strftime("%Y-%m-%d"),
            row["settle_date"].strftime("%Y-%m-%d"),
        ))

    return valid_rows

  def load_to_mysql(self, valid_transactions: list):
    """Executes atomic batch inserts into MySQL."""
    cursor = self.connection.cursor()
    try:
      # 1. Insert clean transactions
      if valid_transactions:
        ledger_insert_query = """
                INSERT INTO transaction_ledger 
                (transaction_id, investor_id, fund_id, transaction_type, amount, units, trade_date, settlement_date)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE amount=VALUES(amount), units=VALUES(units);
                """
        cursor.executemany(ledger_insert_query, valid_transactions)
        print(
            f"Committed {len(valid_transactions)} valid transactions to"
            " 'transaction_ledger'."
        )

      # 2. Insert exception logs
      if self.exceptions:
        exception_insert_query = """
                INSERT INTO reconciliation_exceptions 
                (raw_record_id, error_code, error_description, raw_payload)
                VALUES (%s, %s, %s, %s);
                """
        cursor.executemany(exception_insert_query, self.exceptions)
        print(
            f"Committed {len(self.exceptions)} exception logs to"
            " 'reconciliation_exceptions'."
        )

      self.connection.commit()

    except Error as e:
      self.connection.rollback()
      print(f"Transaction rolled back due to error: {e}")
      raise
    finally:
      cursor.close()

  def generate_reconciliation_summary(self):
    """Queries MySQL directly to verify ledger state and aggregate metrics."""
    cursor = self.connection.cursor(dictionary=True)

    summary_query = """
        SELECT 
            transaction_type,
            COUNT(*) AS total_trades,
            SUM(amount) AS total_volume_usd,
            SUM(units) AS total_units_allocated
        FROM transaction_ledger
        GROUP BY transaction_type;
        """
    cursor.execute(summary_query)
    trade_summary = cursor.fetchall()

    break_query = """
        SELECT 
            error_code,
            COUNT(*) AS break_count
        FROM reconciliation_exceptions
        GROUP BY error_code;
        """
    cursor.execute(break_query)
    break_summary = cursor.fetchall()

    print("\n====== DATABASE-AUDITED RECONCILIATION SUMMARY ======")
    print("--- Settled Ledger Trades ---")
    for row in trade_summary:
      print(
          f"Type: {row['transaction_type']} | Count: {row['total_trades']} |"
          f" Volume: ${row['total_volume_usd']:,.2f} | Units:"
          f" {row['total_units_allocated']}"
      )

    print("\n--- Exception Break Rates ---")
    for row in break_summary:
      print(f"Error Code: {row['error_code']} | Occurrences: {row['break_count']}")
    print("====================================================\n")

    cursor.close()

  def close(self):
    if self.connection and self.connection.is_connected():
      self.connection.close()
      print("MySQL connection closed.")


# -------------------------------------------------------------
# Execution
# -------------------------------------------------------------
if __name__ == "__main__":
  db_credentials = {
      "host": "localhost",
      "user": "root",
      "password": "12345678",  # Update with local password
      "database": "financial_ledger_db",
  }

  pipeline = FinancialETLPipeline(db_credentials)

  try:
    pipeline.connect()
    pipeline.seed_master_data()

    valid_invs, funds = pipeline.fetch_reference_data()
    raw_df = pipeline.extract_and_transform("raw_crm_feed.csv")
    valid_txns = pipeline.validate_records(raw_df, valid_invs, funds)

    pipeline.load_to_mysql(valid_txns)
    pipeline.generate_reconciliation_summary()

  finally:
    pipeline.close()