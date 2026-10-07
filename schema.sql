CREATE DATABASE IF NOT EXISTS financial_ledger_db;
USE financial_ledger_db;

-- 1. Master Investors Table
CREATE TABLE IF NOT EXISTS investors (
    investor_id VARCHAR(20) PRIMARY KEY,
    legal_name VARCHAR(150) NOT NULL,
    investor_type VARCHAR(50) NOT NULL,
    kyc_status VARCHAR(20) DEFAULT 'VERIFIED',
    contact_email VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- 2. Master Funds Table
CREATE TABLE IF NOT EXISTS funds (
    fund_id VARCHAR(20) PRIMARY KEY,
    fund_name VARCHAR(150) NOT NULL,
    currency VARCHAR(3) DEFAULT 'USD',
    nav_per_unit DECIMAL(15, 4) NOT NULL,
    status VARCHAR(20) DEFAULT 'ACTIVE'
) ENGINE=InnoDB;

-- 3. Audited Transaction Ledger
CREATE TABLE IF NOT EXISTS transaction_ledger (
    transaction_id VARCHAR(50) PRIMARY KEY,
    investor_id VARCHAR(20) NOT NULL,
    fund_id VARCHAR(20) NOT NULL,
    transaction_type ENUM('SUBSCRIPTION', 'REDEMPTION', 'TRANSFER') NOT NULL,
    amount DECIMAL(18, 2) NOT NULL,
    units DECIMAL(18, 4) NOT NULL,
    trade_date DATE NOT NULL,
    settlement_date DATE NOT NULL,
    ingestion_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_ledger_investor FOREIGN KEY (investor_id) REFERENCES investors(investor_id),
    CONSTRAINT fk_ledger_fund FOREIGN KEY (fund_id) REFERENCES funds(fund_id),
    INDEX idx_trade_date (trade_date),
    INDEX idx_investor (investor_id)
) ENGINE=InnoDB;

-- 4. Exception & Anomaly Audit Log
CREATE TABLE IF NOT EXISTS reconciliation_exceptions (
    exception_id INT AUTO_INCREMENT PRIMARY KEY,
    raw_record_id VARCHAR(50) NOT NULL,
    error_code VARCHAR(50) NOT NULL,
    error_description TEXT NOT NULL,
    raw_payload JSON NOT NULL,
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_error_code (error_code)
) ENGINE=InnoDB;