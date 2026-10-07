import pandas as pd
import numpy as np
import json
from datetime import datetime

class FinancialReconciliationEngine:
    def __init__(self, master_investors_path: str, master_funds_path: str):
        self.investors = pd.read_csv(master_investors_path)
        self.funds = pd.read_csv(master_funds_path)
        self.exceptions = []
        
    def _clean_currency(self, val):
        if pd.isna(val):
            return np.nan
        val_str = str(val).replace('$', '').replace(',', '').strip()
        try:
            return float(val_str)
        except ValueError:
            return np.nan

    def _normalize_string(self, val):
        return str(val).strip().upper() if pd.notna(val) else ""

    def ingest_and_standardize(self, raw_filepath: str) -> pd.DataFrame:
        df = pd.read_csv(raw_filepath)
        initial_count = len(df)
        
        # 1. Deduplication on raw reference IDs
        df = df.drop_duplicates(subset=['txn_ref'], keep='first')
        
        # 2. String Normalization
        df['txn_ref'] = df['txn_ref'].apply(self._normalize_string)
        df['investor_id'] = df['investor_id'].apply(self._normalize_string)
        df['fund_code'] = df['fund_code'].apply(self._normalize_string)
        df['type'] = df['type'].apply(self._normalize_string)
        
        # 3. Numeric Standardization
        df['amount'] = df['amount'].apply(self._clean_currency)
        
        # 4. Standardize Dates (ISO-8601: YYYY-MM-DD)
        df['trade_date'] = pd.to_datetime(
        df['trade_date'], format='mixed', dayfirst=True, errors='coerce'
        )
        df['settle_date'] = pd.to_datetime(
            df['settle_date'], format='mixed', dayfirst=True, errors='coerce'
        )
        return df

    def validate_transactions(self, df: pd.DataFrame) -> (pd.DataFrame, pd.DataFrame): # type: ignore
        valid_indices = []
        valid_investor_ids = set(self.investors['investor_id'].unique())
        valid_fund_ids = set(self.funds['fund_id'].unique())
        
        for idx, row in df.iterrows():
            errors = []
            
            # Rule 1: Master Reference Validity (Foreign Key integrity)
            if row['investor_id'] not in valid_investor_ids:
                errors.append(("ERR_UNREGISTERED_INVESTOR", f"Investor ID {row['investor_id']} not found in master records"))
            if row['fund_code'] not in valid_fund_ids:
                errors.append(("ERR_INVALID_FUND", f"Fund code {row['fund_code']} does not exist"))
                
            # Rule 2: Amount Bounds
            if pd.isna(row['amount']) or row['amount'] <= 0:
                errors.append(("ERR_INVALID_AMOUNT", f"Non-positive or null transaction amount: {row['amount']}"))
                
            # Rule 3: Date Chronology
            if pd.isna(row['trade_date']) or pd.isna(row['settle_date']):
                errors.append(("ERR_MALFORMED_DATE", "Failed to parse trade or settlement date"))
            elif row['settle_date'] < row['trade_date']:
                errors.append(("ERR_DATE_CHRONOLOGY", f"Settlement date ({row['settle_date']}) precedes trade date ({row['trade_date']})"))
                
            # Rule 4: Action Type Validity
            if row['type'] not in ['SUBSCRIPTION', 'REDEMPTION', 'TRANSFER']:
                errors.append(("ERR_UNKNOWN_ACTION", f"Unrecognized transaction type: {row['type']}"))
                
            if errors:
                for code, desc in errors:
                    self.exceptions.append({
                        "raw_record_id": row['txn_ref'],
                        "error_code": code,
                        "error_description": desc,
                        "raw_payload": json.dumps(row.to_dict(), default=str),
                        "detected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    })
            else:
                valid_indices.append(idx)
                
        clean_df = df.loc[valid_indices].copy()
        
        # Calculate Units Allocated based on Fund NAV
        fund_nav_map = dict(zip(self.funds['fund_id'], self.funds['nav_per_unit']))
        clean_df['nav'] = clean_df['fund_code'].map(fund_nav_map)
        clean_df['units'] = (clean_df['amount'] / clean_df['nav']).round(4)
        
        exceptions_df = pd.DataFrame(self.exceptions)
        return clean_df, exceptions_df

    def export_reports(self, clean_df: pd.DataFrame, exceptions_df: pd.DataFrame):
        # Clean Ledger Export
        clean_df.to_csv("clean_transaction_ledger.csv", index=False)
        exceptions_df.to_csv("reconciliation_exceptions_log.csv", index=False)
        
        # Summary Report for Stakeholders/Operations Managers
        summary = {
            "Total Ingested Records": len(clean_df) + len(exceptions_df['raw_record_id'].unique()),
            "Valid Transactions": len(clean_df),
            "Exceptions Logged": len(exceptions_df),
            "Total Capital Inflow (Subscriptions)": clean_df[clean_df['type'] == 'SUBSCRIPTION']['amount'].sum(),
            "Total Capital Outflow (Redemptions)": clean_df[clean_df['type'] == 'REDEMPTION']['amount'].sum()
        }
        
        print("\n===== RECONCILIATION SUMMARY REPORT =====")
        for k, v in summary.items():
            if isinstance(v, float):
                print(f"{k}: ${v:,.2f}")
            else:
                print(f"{k}: {v}")
        print("=========================================\n")

def export_to_advanced_excel(clean_df, exceptions_df, output_path="Reconciliation_Audit_Pack.xlsx"):
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        # Sheet 1: Master Clean Ledger
        clean_df.to_excel(writer, sheet_name='Clean_Ledger', index=False)
        
        # Sheet 2: Exceptions for Operations Review
        exceptions_df.to_excel(writer, sheet_name='Exception_Audit', index=False)
        
        # Access openpyxl workbook and sheets for advanced styling
        workbook = writer.book
        ws_ledger = writer.sheets['Clean_Ledger']
        ws_exceptions = writer.sheets['Exception_Audit']
        
        # Add Excel Dynamic Formulas at the bottom of the ledger
        last_row = len(clean_df) + 1
        ws_ledger[f'D{last_row + 2}'] = 'Total Inflow (Subscriptions):'
        ws_ledger[f'E{last_row + 2}'] = (
            f'=SUMIF(D2:D{last_row}, "SUBSCRIPTION", E2:E{last_row})'
        )

        ws_ledger[f'D{last_row + 3}'] = 'Total Outflow (Redemptions):'
        ws_ledger[f'E{last_row + 3}'] = (
            f'=SUMIF(D2:D{last_row}, "REDEMPTION", E2:E{last_row})'
        )

    print(f"Generated formatted multi-tab audit pack: {output_path}")


if __name__ == '__main__':
    engine = FinancialReconciliationEngine("master_investors.csv", "master_funds.csv")
    raw_df = engine.ingest_and_standardize("raw_crm_feed.csv")
    clean_df, exceptions_df = engine.validate_transactions(raw_df)
    engine.export_reports(clean_df, exceptions_df)
    export_to_advanced_excel(clean_df, exceptions_df)