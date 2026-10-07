import pandas as pd
import numpy as np

def create_mock_files():
    # 1. Master Reference Data
    investors_df = pd.DataFrame({
        'investor_id': ['INV-1001', 'INV-1002', 'INV-1003', 'INV-1004'],
        'legal_name': ['Blackstone Alpha Corp', 'Apex Global Holdings', 'Vanguard Offshore Fund', 'Meridian Capital Partners'],
        'investor_type': ['Institutional', 'Institutional', 'Institutional', 'High-Net-Worth'],
        'kyc_status': ['VERIFIED', 'VERIFIED', 'VERIFIED', 'VERIFIED'],
        'contact_email': ['ops@blackstone.com', 'settlements@apex.com', 'admin@vanguard.com', 'ir@meridian.com']
    })
    investors_df.to_csv('master_investors.csv', index=False)

    funds_df = pd.DataFrame({
        'fund_id': ['FUND-ALPHA', 'FUND-BETA'],
        'fund_name': ['D. E. Shaw Horizon Fund', 'D. E. Shaw Core Alpha Fund'],
        'currency': ['USD', 'USD'],
        'nav_per_unit': [1250.50, 840.25]
    })
    funds_df.to_csv('master_funds.csv', index=False)

    # 2. Raw Messy Inbound CRM Transactions
    raw_crm_data = [
        # Clean subscription
        {"txn_ref": "TXN-001", "investor_id": "INV-1001", "fund_code": "FUND-ALPHA", "type": "subscription", "amount": "500000.00", "trade_date": "2026-10-01", "settle_date": "2026-10-03"},
        # Exact duplicate row
        {"txn_ref": "TXN-001", "investor_id": "INV-1001", "fund_code": "FUND-ALPHA", "type": "subscription", "amount": "500000.00", "trade_date": "2026-10-01", "settle_date": "2026-10-03"},
        # Messy whitespace and mixed casing
        {"txn_ref": "TXN-002", "investor_id": " inv-1002 ", "fund_code": "fund-alpha", "type": "  SUBSCRIPTION  ", "amount": "$1,200,000.00", "trade_date": "01/10/2026", "settle_date": "03/10/2026"},
        # Invalid amount (Negative redemption)
        {"txn_ref": "TXN-003", "investor_id": "INV-1003", "fund_code": "FUND-BETA", "type": "redemption", "amount": "-250000.00", "trade_date": "2026-10-02", "settle_date": "2026-10-04"},
        # Unregistered / Orphan Investor ID
        {"txn_ref": "TXN-004", "investor_id": "INV-9999", "fund_code": "FUND-ALPHA", "type": "subscription", "amount": "100000.00", "trade_date": "2026-10-02", "settle_date": "2026-10-04"},
        # Chronological anomaly (Settlement before trade date)
        {"txn_ref": "TXN-005", "investor_id": "INV-1004", "fund_code": "FUND-BETA", "type": "transfer", "amount": "75000.00", "trade_date": "2026-10-05", "settle_date": "2026-10-01"},
        # Valid redemption
        {"txn_ref": "TXN-006", "investor_id": "INV-1001", "fund_code": "FUND-ALPHA", "type": "redemption", "amount": "150000.00", "trade_date": "2026-10-04", "settle_date": "2026-10-06"}
    ]
    pd.DataFrame(raw_crm_data).to_csv('raw_crm_feed.csv', index=False)
    print("Mock datasets generated: master_investors.csv, master_funds.csv, raw_crm_feed.csv")

if __name__ == '__main__':
    create_mock_files()
