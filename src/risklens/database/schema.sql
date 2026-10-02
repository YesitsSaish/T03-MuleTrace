-- RiskLens Banking & Anti-Money-Laundering (AML) Relational Schema
-- Compatible with PostgreSQL / Supabase / SQLite

-- 1. Accounts Table
CREATE TABLE IF NOT EXISTS accounts (
    account_id VARCHAR(64) PRIMARY KEY,
    customer_name VARCHAR(128) NOT NULL,
    account_type VARCHAR(32) DEFAULT 'INDIVIDUAL',
    kyc_status VARCHAR(32) DEFAULT 'VERIFIED',
    initial_balance NUMERIC(14, 2) DEFAULT 0.00,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    country_code VARCHAR(8) DEFAULT 'IN',
    is_seed_fraud BOOLEAN DEFAULT FALSE,
    ring_id INTEGER DEFAULT -1
);

-- 2. Transactions Table
CREATE TABLE IF NOT EXISTS transactions (
    tx_id VARCHAR(64) PRIMARY KEY,
    src_account_id VARCHAR(64) NOT NULL REFERENCES accounts(account_id) ON DELETE CASCADE,
    dst_account_id VARCHAR(64) NOT NULL REFERENCES accounts(account_id) ON DELETE CASCADE,
    amount NUMERIC(14, 2) NOT NULL,
    currency VARCHAR(8) DEFAULT 'INR',
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    channel VARCHAR(32) DEFAULT 'UPI', -- UPI, IMPS, NEFT, CARD
    device_id VARCHAR(64),
    ip_address VARCHAR(45),
    geo_location VARCHAR(64),
    is_flagged_fraud BOOLEAN DEFAULT FALSE
);

-- 3. Fraud Rings / Cases
CREATE TABLE IF NOT EXISTS fraud_cases (
    case_id VARCHAR(64) PRIMARY KEY,
    ring_id INTEGER NOT NULL,
    detected_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    case_status VARCHAR(32) DEFAULT 'OPEN', -- OPEN, IN_INVESTIGATION, RESOLVED, DISMISSED
    typology VARCHAR(64), -- 'MULE_RING', 'CIRCULAR_ROUTING', 'SMURFING'
    total_volume NUMERIC(14, 2) DEFAULT 0.00,
    involved_accounts TEXT, -- pipe separated or JSON array of account_ids
    notes TEXT
);

-- 4. Live Risk Assessments (Persisted GNN + Heuristic Scoring)
CREATE TABLE IF NOT EXISTS risk_assessments (
    assessment_id SERIAL PRIMARY KEY,
    account_id VARCHAR(64) NOT NULL REFERENCES accounts(account_id) ON DELETE CASCADE,
    assessed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    composite_risk_score NUMERIC(5, 4) NOT NULL,
    gnn_score NUMERIC(5, 4) NOT NULL,
    heuristic_score NUMERIC(5, 4) NOT NULL,
    risk_band VARCHAR(16) NOT NULL, -- 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'
    decision VARCHAR(32) NOT NULL, -- 'ALLOW', 'MANUAL_REVIEW', 'BLOCK_SUSPEND'
    violations_json TEXT,
    sensitivity_alpha NUMERIC(4, 2) DEFAULT 0.65
);

-- Indices for rapid graph traversal
CREATE INDEX IF NOT EXISTS idx_tx_src ON transactions(src_account_id);
CREATE INDEX IF NOT EXISTS idx_tx_dst ON transactions(dst_account_id);
CREATE INDEX IF NOT EXISTS idx_tx_time ON transactions(timestamp);
CREATE INDEX IF NOT EXISTS idx_acc_ring ON accounts(ring_id);
CREATE INDEX IF NOT EXISTS idx_risk_acc ON risk_assessments(account_id);
