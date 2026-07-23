# Example setup guide

# Example setup guide

This folder contains runnable examples for the enterprise governance workflow. Everything here connects directly to a database via SQLAlchemy — no Docker required. Bring your own running Postgres/MySQL/MSSQL server (local install, cloud DB, a container you started yourself, whatever you already have), or just use the SQLite default, which needs nothing.

These examples are intended as a practical how-to for demonstrating governance setup, role-based access, and policy evaluation in a realistic environment.

## Files

- enterprise_setup.py: provisions example data and per-role database accounts for SQLite, PostgreSQL, MySQL, and MSSQL.
- sqlite_setup.sql, postgresql_setup.sql, mysql_setup.sql, mssql_setup.sql: idempotent seed scripts.
- ../config/governance.yaml: the canonical YAML configuration file for roles, permissions, and connector defaults.

## Quick start

### 1. Install the package locally

```bash
python -m pip install -e .
```

### 2. Run the example setup

SQLite needs no setup at all — it's the default and just writes a local file:

```bash
python examples/enterprise_setup.py --dry-run --skip-demo
```

When you are ready to apply the example data:

```bash
python examples/enterprise_setup.py
```

This creates `./data/sqlite/registry.db` by default. Override the location with `--sqlite-path`.

### 3. Connect to a real Postgres/MySQL/MSSQL server

Point the script at a database you already have running, via an environment variable:

```bash
export IKIGOV_POSTGRES_URL="postgresql://user:pw@host:5432/db"
python examples/enterprise_setup.py --dialect postgresql

export IKIGOV_MYSQL_URL="mysql+pymysql://user:pw@host:3306/db"
python examples/enterprise_setup.py --dialect mysql

export IKIGOV_MSSQL_URL="mssql+pyodbc://user:pw@host:1433/db?driver=ODBC+Driver+18+for+SQL+Server"
python examples/enterprise_setup.py --dialect mssql
```

Or pass a connection string directly for a single dialect:

```bash
python examples/enterprise_setup.py --dialect postgresql --connection-string "postgresql://user:pw@host:5432/db"
```

Connection resolution order: `--connection-string` > the matching `IKIGOV_*_URL` env var > a `connection_string`/`dsn` entry in your governance config > (SQLite only) a local file.

To run every dialect in one pass, use `--dialect all` (each dialect still resolves its own connection independently):

```bash
python examples/enterprise_setup.py --dialect all --dry-run
```

### 4. Tear down and reset the example data

```bash
python examples/enterprise_setup.py --dialect all --teardown
```

### 5. Use a shared governance config

You can point the example runner at a specific governance profile or rely on environment selection:

```bash
python examples/enterprise_setup.py --dialect postgresql --config config/governance.yaml
```

To scan SQL data with the same shared governance YAML, use the CLI with the backend you want:

```bash
ikidgov scan --type sql --path ./data/sqlite/registry.db --table employees --owner jdoe --backend postgres --config config/governance.yaml
ikidgov scan --type sql --path ./data/sqlite/registry.db --table employees --owner jdoe --backend mysql --config config/governance.yaml
ikidgov scan --type sql --path ./data/sqlite/registry.db --table employees --owner jdoe --backend mssql --config config/governance.yaml
```

Or with an environment-specific profile:

```bash
IKIGOV_ENV=dev python examples/enterprise_setup.py --dry-run
```

## Config file format

The config file is YAML. It can define per-role accounts, permissions, scopes, and connector defaults.

Example:

```yaml
roles:
  analyst:
    account:
      username: analyst
      password: "<CHANGE-ME-not-a-real-password>"
    permissions:
      - select
    scope: policy_restricted

connectors:
  csv:
    default_type: string
```

If a role has no password configured, `enterprise_setup.py` skips creating that role's database account (with a message telling you what to set) rather than substituting a shared or guessed password.

## Role and account walkthrough

The example is designed to show the governance model as a collection of explicit identities:

- admin: broad platform control for administrators.
- analyst: a read-oriented account for policy-restricted data access.
- auditor: a read-only account used for audit review.
- data_owner: a domain owner account that can approve classification and manage grants.
- data_steward: a stewardship account that classifies data and proposes policy changes.
- service_account: a programmatic identity for scoped integrations.

Each role is defined in the governance YAML and the example runner surfaces the username, permissions, and scope so the demo can be used as a guided walkthrough.

## Notes

- The setup scripts are intended for example and demonstration purposes.
- The SQL seed files are written to be safe to re-run.
- The runner prints progress steps so it is easier to follow what is happening.
- You can target a single backend with `sqlite`, `postgresql`, `mysql`, or `mssql` instead of `all`.
- The script never starts, stops, or manages a database process itself — it only opens a direct connection to whatever you've configured.
