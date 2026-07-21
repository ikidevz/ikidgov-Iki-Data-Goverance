IF SCHEMA_ID('hr') IS NULL EXEC('CREATE SCHEMA hr');
IF SCHEMA_ID('marketing') IS NULL EXEC('CREATE SCHEMA marketing');
IF SCHEMA_ID('finance') IS NULL EXEC('CREATE SCHEMA finance');
IF SCHEMA_ID('regional') IS NULL EXEC('CREATE SCHEMA regional');
GO

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'employees' AND schema_id = SCHEMA_ID('hr'))
BEGIN
    CREATE TABLE hr.employees (
        id INT PRIMARY KEY,
        full_name NVARCHAR(120) NOT NULL,
        email NVARCHAR(255) NOT NULL,
        ssn NVARCHAR(11),
        salary_annual DECIMAL(12, 2),
        department NVARCHAR(60),
        sensitivity_level NVARCHAR(20) DEFAULT 'unclassified'
    );
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'campaign_contacts' AND schema_id = SCHEMA_ID('marketing'))
BEGIN
    CREATE TABLE marketing.campaign_contacts (
        id INT PRIMARY KEY,
        full_name NVARCHAR(120) NOT NULL,
        email NVARCHAR(255) NOT NULL,
        phone NVARCHAR(20),
        opt_in_status NVARCHAR(20) DEFAULT 'unknown',
        campaign_id INT,
        sensitivity_level NVARCHAR(20) DEFAULT 'unclassified'
    );
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'transactions' AND schema_id = SCHEMA_ID('finance'))
BEGIN
    CREATE TABLE finance.transactions (
        id INT PRIMARY KEY,
        account_holder NVARCHAR(120) NOT NULL,
        account_number NVARCHAR(34) NOT NULL,
        card_last4 NVARCHAR(4),
        amount DECIMAL(14, 2) NOT NULL,
        txn_date DATETIME2 NOT NULL,
        sensitivity_level NVARCHAR(20) DEFAULT 'unclassified'
    );
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'customers' AND schema_id = SCHEMA_ID('regional'))
BEGIN
    CREATE TABLE regional.customers (
        id INT PRIMARY KEY,
        full_name NVARCHAR(120) NOT NULL,
        email NVARCHAR(255) NOT NULL,
        region NVARCHAR(60),
        sensitivity_level NVARCHAR(20) DEFAULT 'unclassified'
    );
END
GO

IF NOT EXISTS (SELECT 1 FROM hr.employees WHERE id = 1)
BEGIN
    INSERT INTO hr.employees (id, full_name, email, ssn, salary_annual, department, sensitivity_level)
    VALUES (1, N'Priya Shah', N'priya.hr-lead@company.com', N'111-22-3333', 180000.00, N'HR', N'critical');
END
GO

IF NOT EXISTS (SELECT 1 FROM hr.employees WHERE id = 2)
BEGIN
    INSERT INTO hr.employees (id, full_name, email, ssn, salary_annual, department, sensitivity_level)
    VALUES (2, N'Drew Steward', N'dsteward.hr@company.com', N'222-33-4444', 125000.00, N'HR', N'high');
END
GO

IF NOT EXISTS (SELECT 1 FROM marketing.campaign_contacts WHERE id = 1)
BEGIN
    INSERT INTO marketing.campaign_contacts (id, full_name, email, phone, opt_in_status, campaign_id, sensitivity_level)
    VALUES (1, N'Mina Gomez', N'growth.lead@company.com', N'555-0101', N'opted_in', 301, N'high');
END
GO

IF NOT EXISTS (SELECT 1 FROM marketing.campaign_contacts WHERE id = 2)
BEGIN
    INSERT INTO marketing.campaign_contacts (id, full_name, email, phone, opt_in_status, campaign_id, sensitivity_level)
    VALUES (2, N'Luca Chen', N'crm.steward@company.com', N'555-0102', N'opted_in', 302, N'high');
END
GO

IF NOT EXISTS (SELECT 1 FROM finance.transactions WHERE id = 1)
BEGIN
    INSERT INTO finance.transactions (id, account_holder, account_number, card_last4, amount, txn_date, sensitivity_level)
    VALUES (1, N'Priya Shah', N'4111111111111111', N'1111', 1200.50, '2026-07-01T00:00:00', N'critical');
END
GO

IF NOT EXISTS (SELECT 1 FROM finance.transactions WHERE id = 2)
BEGIN
    INSERT INTO finance.transactions (id, account_holder, account_number, card_last4, amount, txn_date, sensitivity_level)
    VALUES (2, N'Luca Chen', N'4222222222222222', N'2222', 350.00, '2026-07-02T00:00:00', N'critical');
END
GO

IF NOT EXISTS (SELECT 1 FROM regional.customers WHERE id = 1)
BEGIN
    INSERT INTO regional.customers (id, full_name, email, region, sensitivity_level)
    VALUES (1, N'Avery Kim', N'field-ops.lead@company.com', N'West', N'high');
END
GO

IF NOT EXISTS (SELECT 1 FROM regional.customers WHERE id = 2)
BEGIN
    INSERT INTO regional.customers (id, full_name, email, region, sensitivity_level)
    VALUES (2, N'Jordan Lee', N'regional-analyst@company.com', N'South', N'high');
END
GO
