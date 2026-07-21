# Example setup guide

This folder contains runnable examples for the enterprise governance workflow and for exercising the bundled Docker-backed SQL backends.

These examples are intended as a practical how-to for demonstrating governance setup, role-based access, and policy evaluation in a realistic environment.

## Files

- enterprise_setup.py: provisions example data for SQLite, PostgreSQL, MySQL, and MSSQL.
- sqlite_setup.sql, postgresql_setup.sql, mysql_setup.sql, mssql_setup.sql: idempotent seed scripts.
- ../config/governance.yaml: the canonical YAML configuration file for roles, permissions, and connector defaults.

## Quick start

### 1. Install the package locally

```bash
python -m pip install -e .
```

### 2. Start the example services

```bash
docker compose up -d --wait
```

### 3. Run the example setup

The example runner now prints a role and account overview before it applies any SQL. This helps you see the identities, permissions, and scope of each governance role in a single place.

A good first pass is to preview the flow without changing anything:

```bash
python examples/enterprise_setup.py --dialect sqlite --dry-run --skip-demo
```

When you are ready to apply the example data:

```bash
python examples/enterprise_setup.py --dialect all
```

### 4. Tear down and reset the example data

```bash
python examples/enterprise_setup.py --dialect all --teardown
```

### 5. Use a shared governance config

You can point the example runner at a specific governance profile or rely on environment selection:

```bash
python examples/enterprise_setup.py --dialect postgres --config config/governance.yaml
```

To scan SQL data with the same shared governance YAML, use the CLI with the backend you want:

```bash
ikidgov scan --type sql --path ./data/sqlite/registry.db --table employees --owner jdoe --backend postgres --config config/governance.yaml
ikidgov scan --type sql --path ./data/sqlite/registry.db --table employees --owner jdoe --backend mysql --config config/governance.yaml
ikidgov scan --type sql --path ./data/sqlite/registry.db --table employees --owner jdoe --backend mssql --config config/governance.yaml
```

Or with an environment-specific profile:

```bash
IKIGOV_ENV=dev python examples/enterprise_setup.py --dialect sqlite --dry-run
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

## Role and account walkthrough

The example is designed to show the governance model as a collection of explicit identities:

- admin: broad platform control for administrators.
- analyst: a read-oriented account for policy-restricted data access.
- auditor: a read-only account used for audit review.
- data_owner: a domain owner account that can approve classification and manage grants.
- data_steward: a stewardship account that classifies data and proposes policy changes.
- service_account: a programmatic identity for scoped integrations.

Each role is defined in the governance YAML and the example runner surfaces the username, permissions, and scope so the demo can be used as a guided walkthrough.

## Docker backend notes

- The setup scripts are intended for example and demonstration purposes.
- The SQL seed files are written to be safe to re-run.
- The runner prints progress steps so it is easier to follow what is happening.
- You can target a single backend with `sqlite`, `postgres`, `mysql`, or `mssql` instead of `all`.
