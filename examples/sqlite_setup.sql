PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS employees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL,
    ssn TEXT,
    salary_annual REAL,
    department TEXT,
    sensitivity_level TEXT DEFAULT 'unclassified'
);

CREATE TABLE IF NOT EXISTS campaign_contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL,
    phone TEXT,
    opt_in_status TEXT DEFAULT 'unknown',
    campaign_id INTEGER,
    sensitivity_level TEXT DEFAULT 'unclassified'
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_holder TEXT NOT NULL,
    account_number TEXT NOT NULL,
    card_last4 TEXT,
    amount REAL NOT NULL,
    txn_date TEXT NOT NULL,
    sensitivity_level TEXT DEFAULT 'unclassified'
);

CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL,
    region TEXT,
    sensitivity_level TEXT DEFAULT 'unclassified'
);

INSERT OR IGNORE INTO employees (id, full_name, email, ssn, salary_annual, department, sensitivity_level)
VALUES
    (1, 'Priya Shah', 'priya.hr-lead@company.com', '111-22-3333', 180000.00, 'HR', 'critical'),
    (2, 'Drew Steward', 'dsteward.hr@company.com', '222-33-4444', 125000.00, 'HR', 'high');

INSERT OR IGNORE INTO campaign_contacts (id, full_name, email, phone, opt_in_status, campaign_id, sensitivity_level)
VALUES
    (1, 'Mina Gomez', 'growth.lead@company.com', '555-0101', 'opted_in', 301, 'high'),
    (2, 'Luca Chen', 'crm.steward@company.com', '555-0102', 'opted_in', 302, 'high');

INSERT OR IGNORE INTO transactions (id, account_holder, account_number, card_last4, amount, txn_date, sensitivity_level)
VALUES
    (1, 'Priya Shah', '4111111111111111', '1111', 1200.50, '2026-07-01', 'critical'),
    (2, 'Luca Chen', '4222222222222222', '2222', 350.00, '2026-07-02', 'critical');

INSERT OR IGNORE INTO customers (id, full_name, email, region, sensitivity_level)
VALUES
    (1, 'Avery Kim', 'field-ops.lead@company.com', 'West', 'high'),
    (2, 'Jordan Lee', 'regional-analyst@company.com', 'South', 'high');
