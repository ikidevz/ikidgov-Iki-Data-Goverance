-- Seed data for testing the MSSQL dialect of the multi-dialect SQL connector.
-- The official MSSQL image has no docker-entrypoint-initdb.d equivalent,
-- so this is executed explicitly by the `mssql-init` service via sqlcmd
-- after the server reports healthy (see docker-compose.yml).

IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = 'ikidgov_test')
BEGIN
    CREATE DATABASE ikidgov_test;
END
GO

USE ikidgov_test;
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'customers')
BEGIN
    CREATE TABLE customers (
        id          INT IDENTITY(1,1) PRIMARY KEY,
        full_name   NVARCHAR(120) NOT NULL,
        email       NVARCHAR(255) NOT NULL,
        ssn         NVARCHAR(11),
        signup_date DATETIME2 DEFAULT SYSUTCDATETIME()
    );

    INSERT INTO customers (full_name, email, ssn) VALUES
        (N'Jane Doe',   N'jane.doe@example.com',   N'123-45-6789'),
        (N'John Smith', N'john.smith@example.com', N'987-65-4321'),
        (N'Maria Cruz', N'maria.cruz@example.com', N'456-78-9123');
END
GO
