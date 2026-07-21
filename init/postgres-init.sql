-- Seed data for testing the Postgres dialect of the multi-dialect SQL connector.
-- Runs automatically on first container start (docker-entrypoint-initdb.d).

CREATE TABLE IF NOT EXISTS customers (
    id          SERIAL PRIMARY KEY,
    full_name   VARCHAR(120) NOT NULL,
    email       VARCHAR(255) NOT NULL,
    ssn         VARCHAR(11),
    signup_date TIMESTAMP WITHOUT TIME ZONE DEFAULT now()
);

INSERT INTO customers (full_name, email, ssn) VALUES
    ('Jane Doe',   'jane.doe@example.com',   '123-45-6789'),
    ('John Smith', 'john.smith@example.com', '987-65-4321'),
    ('Maria Cruz', 'maria.cruz@example.com', '456-78-9123');
