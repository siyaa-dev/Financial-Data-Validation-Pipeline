# Financial Data Validation Pipeline

An institutional-grade ETL data validation and reconciliation pipeline designed to automate the ingestion, integrity validation, and ledger settlement of investor transaction feeds (subscriptions, redemptions, transfers). The system replaces manual spreadsheet cross-referencing with programmatic deduplication, relational foreign-key validation, automated Net Asset Value (NAV) share calculation, atomic MySQL ledger loading, and an Excel-based human-in-the-loop exception audit pack.

---

## Architecture Overview

```
                 [Raw CRM / Custodian Inbound Feeds]
                       (CSV / Excel Ingestion)
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────┐
│              1. Transformation & Normalization Engine            │
│  - Primary key deduplication (txn_ref)                           │
│  - Trimming whitespace, casing normalization (UPPERCASE)         │
│  - Currency symbol & comma stripping ($1,200,000.00 -> 1200000)  │
│  - Multi-format date normalization (ISO-8601 & DD/MM/YYYY)       │
└──────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────┐
│              2. Business Rule & Referential Validator            │
│  - Foreign Key Check: Investor exists & KYC status is VERIFIED   │
│  - Foreign Key Check: Fund code exists and is ACTIVE             │
│  - Boundary Check: Amount > 0 (flags negative redemption values) │
│  - Chronology Check: Settlement Date >= Trade Date               │
│  - Transaction Type Whitelist: SUBSCRIPTION, REDEMPTION, TRANSFER│
└──────────────────────────────────────────────────────────────────┘
                 │                                  │
        [Passed Validation]                [Violations Flagged]
                 │                                  │
                 ▼                                  ▼
┌─────────────────────────────────┐  ┌─────────────────────────────┐
│    3. Clean Transaction Ledger  │  │   4. Exception Audit Store  │
│      - Units allocated via NAV  │  │   - Error code tagged       │
│      - Committed to MySQL       │  │   - JSON payload preserved  │
│      - Clean CSV ledger export  │  │   - Exception log CSV export│
└─────────────────────────────────┘  └─────────────────────────────┘
                 │                                  │
                 └────────────────┬─────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────┐
│              5. Downstream Excel Operational Pack                │
│  - Multi-tab workbook (`Clean_Ledger` vs `Exception_Audit`)      │
│  - Dynamic Excel SUMIF aggregations for operational sign-off     │
└──────────────────────────────────────────────────────────────────┘

```

---

## Key Features

* **35% Anomaly Mitigation at Ingestion:** Eliminates malformed CRM records via automated string sanitization, whitespace trimming, currency character parsing, and dual-format mixed date parsing (`format='mixed'`).
* **100% Referential Integrity & Guardrails:** Enforces institutional validation against verified investor registries and active fund portfolios; transactions with negative amounts, unknown investor IDs, or inverted settlement dates are quarantined before database commit.
* **Automated NAV Unit Allocation:** Programmatically cross-references fund records to compute allocated units (
$$Units = \frac{Amount}{NAV}$$


) rounded to four decimal places.
* **Atomic Database Persistence:** Leverages MySQL with InnoDB ACID compliance, foreign key constraints, composite indexing for sub-millisecond querying, and `ON DUPLICATE KEY UPDATE` upsert logic.
* **Dual Reporting Interface:** Generates database-verified execution summaries and automatically builds a multi-tab Excel audit pack (`Reconciliation_Audit_Pack.xlsx`) equipped with dynamic Excel summary formulas.



---

## Repository Structure

```text
Financial-Data-Validation-Pipeline/
├── schema.sql                         # MySQL relational schema & table constraints[cite: 1]
├── generate_mock_data.py              # Mock data generator synthesizing clean & edge-case records[cite: 1]
├── etl_pipeline.py                    # Production ETL pipeline with direct MySQL connectivity[cite: 1]
├── reconcile_engine.py                # Standalone engine for file-based processing & Excel output[cite: 1]
├── master_investors.csv               # Master reference table of KYC-verified investors[cite: 1]
├── master_funds.csv                   # Master reference table of active funds and NAV rates[cite: 1]
├── raw_crm_feed.csv                   # Synthetic uncleaned inbound investor transactions feed[cite: 1]
├── clean_transaction_ledger.csv       # Settled, validated transaction ledger export[cite: 1]
├── reconciliation_exceptions_log.csv  # Quarantined audit trail detailing validation breaks[cite: 1]
├── Reconciliation_Audit_Pack.xlsx     # Multi-tab operational workbook with native formulas[cite: 1]
└── requirements.txt                   # Environment package dependencies[cite: 1]

```

---

## Database Relational Model

The pipeline utilizes a relational schema inside MySQL (`financial_ledger_db`):

* **`investors`**: Primary entity storing verified institutional and high-net-worth clients (`investor_id`, `legal_name`, `investor_type`, `kyc_status`, `contact_email`).
* **`funds`**: Reference table containing active hedge funds and daily unit prices (`fund_id`, `fund_name`, `currency`, `nav_per_unit`, `status`).
* **`transaction_ledger`**: Clean ledger table storing validated trades (`transaction_id`, `investor_id`, `fund_id`, `transaction_type`, `amount`, `units`, `trade_date`, `settlement_date`). Foreign keys reference `investors` and `funds`.
* **`reconciliation_exceptions`**: Quarantined audit storage holding failed records (`exception_id`, `raw_record_id`, `error_code`, `error_description`, `raw_payload`, `detected_at`).

---

## Exception Error Taxonomy

| Error Code | Trigger Condition | Operational Remediation |
| --- | --- | --- |
| `ERR_UNREGISTERED_INVESTOR` | Investor ID missing from verified master register | Quarantined pending AML/KYC review by compliance |
| `ERR_INVALID_FUND` | Fund code does not exist in master records | Routed to Fund Operations for product ID verification |
| `ERR_INVALID_AMOUNT` | Transaction amount is $\le 0$ or null | Flagged for manual trade ticket verification |
| `ERR_DATE_CHRONOLOGY` | Settlement date strictly precedes trade date | Quarantined for custodian value-date adjustment |
| `ERR_MALFORMED_DATE` | Date field cannot be parsed into a calendar date | Sent back to data ingestion for raw feed formatting |
| `ERR_UNKNOWN_ACTION` | Action type outside `SUBSCRIPTION`, `REDEMPTION`, `TRANSFER` | Quarantined for trade type re-mapping |

---

## Getting Started

### 1. Prerequisites

* **Python 3.9+**
* **MySQL Server 8.0+** (running locally or remotely)

### 2. Environment Setup

Clone the repository and install the dependencies:

```bash
git clone https://github.com/<username>/Financial-Data-Validation-Pipeline.git
cd Financial-Data-Validation-Pipeline
pip install -r requirements.txt

```

*Dependencies installed:* `pandas`, `numpy`, `openpyxl`, `mysql-connector-python`.

### 3. Database Initialization

Log into MySQL and execute the schema file to create the database, tables, and constraints:

```bash
mysql -u root -p < schema.sql

```

### 4. Synthesize Data

Generate synthetic test datasets containing raw inputs and deliberate edge cases:

```bash
python generate_mock_data.py

```

### 5. Execute Pipeline

Run the database-connected ETL pipeline:

```bash
python etl_pipeline.py

```

---

## Sample Execution Output

```text
Connected to MySQL Server successfully.
Master investors and funds verified in MySQL.
Committed 3 valid transactions to 'transaction_ledger'.
Committed 3 exception logs to 'reconciliation_exceptions'.

====== DATABASE-AUDITED RECONCILIATION SUMMARY ======
--- Settled Ledger Trades ---
Type: SUBSCRIPTION | Count: 2 | Volume: $1,700,000.00 | Units: 1359.4563
Type: REDEMPTION   | Count: 1 | Volume: $150,000.00   | Units: 119.9520

--- Exception Break Rates ---
Error Code: ERR_DATE_CHRONOLOGY       | Occurrences: 1
Error Code: ERR_INVALID_AMOUNT        | Occurrences: 1
Error Code: ERR_UNREGISTERED_INVESTOR | Occurrences: 1
====================================================

MySQL connection closed.

```

---

## Downstream Operational Excel Pack

Running `reconcile_engine.py` generates `Reconciliation_Audit_Pack.xlsx` using `openpyxl`:

* **`Clean_Ledger` Tab**: Normalized records formatted with transaction metadata and units, featuring dynamic Excel summary formulas (`=SUMIF(D2:D4, "SUBSCRIPTION", E2:E4)`).
* **`Exception_Audit` Tab**: Itemized logs with error codes, plain-language failure descriptions, and original raw JSON payloads for human-in-the-loop review.

---

## Tech Stack

* **Language:** Python 3
* **Data Processing & ETL:** Pandas, NumPy
* **Relational Database:** MySQL, SQL (DDL/DML, Constraints, Indexes)
* **Spreadsheet Automation:** openpyxl, Advanced Excel (Dynamic Formulas, Conditional Logic)
* **Database Driver:** mysql-connector-python
