CREATE TABLE IF NOT EXISTS employees (
    id INT PRIMARY KEY,
    full_name VARCHAR(120) NOT NULL,
    email VARCHAR(255) NOT NULL,
    ssn VARCHAR(11),
    salary_annual DECIMAL(12, 2),
    department VARCHAR(60),
    sensitivity_level VARCHAR(20) DEFAULT 'unclassified'
);

CREATE TABLE IF NOT EXISTS campaign_contacts (
    id INT PRIMARY KEY,
    full_name VARCHAR(120) NOT NULL,
    email VARCHAR(255) NOT NULL,
    phone VARCHAR(20),
    opt_in_status VARCHAR(20) DEFAULT 'unknown',
    campaign_id INT,
    sensitivity_level VARCHAR(20) DEFAULT 'unclassified'
);

CREATE TABLE IF NOT EXISTS transactions (
    id INT PRIMARY KEY,
    account_holder VARCHAR(120) NOT NULL,
    account_number VARCHAR(34) NOT NULL,
    card_last4 VARCHAR(4),
    amount DECIMAL(14, 2) NOT NULL,
    txn_date DATETIME NOT NULL,
    sensitivity_level VARCHAR(20) DEFAULT 'unclassified'
);

CREATE TABLE IF NOT EXISTS customers (
    id INT PRIMARY KEY,
    full_name VARCHAR(120) NOT NULL,
    email VARCHAR(255) NOT NULL,
    region VARCHAR(60),
    sensitivity_level VARCHAR(20) DEFAULT 'unclassified'
);

INSERT IGNORE INTO employees (id, full_name, email, ssn, salary_annual, department, sensitivity_level)
VALUES
    (1, 'Priya Shah', 'priya.hr-lead@company.com', '111-22-3333', 180000.00, 'HR', 'critical'),
    (2, 'Drew Steward', 'dsteward.hr@company.com', '222-33-4444', 125000.00, 'HR', 'high');

INSERT IGNORE INTO campaign_contacts (id, full_name, email, phone, opt_in_status, campaign_id, sensitivity_level)
VALUES
    (1, 'Mina Gomez', 'growth.lead@company.com', '555-0101', 'opted_in', 301, 'high'),
    (2, 'Luca Chen', 'crm.steward@company.com', '555-0102', 'opted_in', 302, 'high');

INSERT IGNORE INTO transactions (id, account_holder, account_number, card_last4, amount, txn_date, sensitivity_level)
VALUES
    (1, 'Priya Shah', '4111111111111111', '1111', 1200.50, '2026-07-01 00:00:00', 'critical'),
    (2, 'Luca Chen', '4222222222222222', '2222', 350.00, '2026-07-02 00:00:00', 'critical');

INSERT IGNORE INTO customers (id, full_name, email, region, sensitivity_level)
VALUES
    (1, 'Avery Kim', 'field-ops.lead@company.com', 'West', 'high'),
    (2, 'Jordan Lee', 'regional-analyst@company.com', 'South', 'high');
