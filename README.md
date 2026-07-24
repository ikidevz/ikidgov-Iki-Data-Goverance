# ikidgov — Iki Data Governance

ikidgov is a lightweight, composable data governance toolkit for scanning data sources,
classifying columns, enforcing role-based access policies, and provisioning least-privilege
database accounts — without requiring a large platform migration.

![PyPI](https://img.shields.io/pypi/v/ikidgov)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![License MIT](https://img.shields.io/badge/license-MIT-green)
![Backend](https://img.shields.io/badge/backend-SQLite%20%7C%20Postgres%20%7C%20MySQL%20%7C%20MSSQL-orange)

![Cover](assets/image.png)

## Table of contents

- [Features](#features)
- [`GovernanceFacade` — the one class you need](#governancefacade--the-one-class-you-need)
- [Installation](#installation)
- [Quick start (CLI)](#quick-start-cli)
- [Configuration](#configuration)
- [Enterprise setup script](#enterprise-setup-script-examplesenterprise_setuppy)
- [Multi-role standard setup (Database Administrator)](#multi-role-standard-setup-database-administrator)
- [Testing](#testing)
- [Project layout](#project-layout)

## Features

| Capability                    | What it gives you                                                                                                                                                                                                       |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 🔎 **Discover**               | Scan CSV, JSON, and SQL (SQLite, and via SQLAlchemy: PostgreSQL/MySQL/MSSQL) sources to register schema metadata automatically                                                                                          |
| 🏷️ **Classify**               | Tag columns with built-in or plugin-based PII/sensitivity detectors, pluggable via `ikidgov.detectors` entry points                                                                                                     |
| 🔐 **Enforce**                | Evaluate access decisions with a **fail-closed** policy model — nothing is allowed unless a role's permissions explicitly say so                                                                                        |
| 🧾 **Provision**              | Compile role-based grants into ready-to-run `CREATE USER` / `CREATE ROLE` / `GRANT` SQL for MySQL, PostgreSQL, MSSQL, or a generic dialect                                                                              |
| 👥 **Access control**         | Full CRUD for roles, permissions, and access entries, with separation-of-duty policy checks baked in                                                                                                                    |
| 📝 **Audit**                  | Every policy decision and access-control mutation is written to a rotating, lock-safe audit log                                                                                                                         |
| ⚙️ **Configure once**         | Roles, permissions, scopes, account credentials, and connector defaults live in a single YAML file, with `dev` / `staging` / `prod` overrides                                                                           |
| 🧩 **Composable & swappable** | Every module (`metadata_registry`, `connectors`, `classification_engine`, `policy_engine`, `access_control`) is registered as a discoverable `4p.modules` entry point — swap implementations without touching core code |
| 🖥️ **CLI + library**          | Use the `ikidgov` console command, import individual module interfaces, or drive everything through the single `GovernanceFacade` class below                                                                           |
| 🐘 **Multi-database**         | SQLite works out of the box with zero setup; PostgreSQL, MySQL, and MSSQL are supported via connection strings — no Docker required                                                                                     |

## `GovernanceFacade` — the one class you need

Most of the time you don't want to think about five separate modules (`metadata_registry`,
`connectors`, `classification_engine`, `policy_engine`, `access_control`) and the order
they need to be called in. **[`ikidgov.facade.GovernanceFacade`](src/ikidgov/facade.py)**
is a [Facade](https://en.wikipedia.org/wiki/Facade_pattern) over the whole toolkit — one
object, one import, every feature above reachable from it. It doesn't change any
underlying behavior; it's an additive convenience layer, and every module interface it
wraps remains fully usable on its own.

```python
from ikidgov.facade import GovernanceFacade

gov = GovernanceFacade(config_path="config/governance.yaml")

# discover a schema and register it + its columns in one call
scanned = gov.scan("csv", "customers.csv", owner="jdoe")

# classify the columns that were just registered
classification = gov.classify(scanned["columns"])

# scan + classify in a single call, if you don't need the intermediate result
scanned_and_classified = gov.scan_and_classify("csv", "customers.csv", owner="jdoe")

# fail-closed access decision
decision = gov.check_access(actor_role="analyst", action_type="select",
                             dataset_id=scanned["dataset"]["id"])

# compile role grants into dialect SQL
grants = gov.compile_grants("restrict_pii", "employees", dialect="postgresql")

# introspect everything that's wired up
gov.describe()
```

Related functionality is grouped behind small sub-facades so the surface stays flat and
discoverable:

| Sub-facade           | Wraps                                          | Example                                                         |
| -------------------- | ---------------------------------------------- | --------------------------------------------------------------- |
| `gov.registry`       | `metadata_registry` + `connectors`             | `gov.registry.list_datasets()`                                  |
| `gov.classification` | `classification_engine`                        | `gov.classification.classify(columns)`                          |
| `gov.policy`         | `policy_engine`                                | `gov.policy.check(...)`, `gov.policy.compile_grants(...)`       |
| `gov.access_control` | `access_control` (role/permission/access CRUD) | `gov.access_control.create_role(name="data_engineer")`          |
| `gov.provisioning`   | Connection-string resolution + SQL execution   | `gov.provisioning.resolve_connection_string("postgresql", ...)` |

```python
# role/permission/access CRUD
gov.access_control.create_role(name="data_engineer", description="Schema + governance ops")

# connection-string resolution (CLI override > env var > governance config > .env > default)
conn = gov.provisioning.resolve_connection_string(
    "postgresql", cli_override=None, config=gov.config,
    sqlite_path="./data/sqlite/registry.db")

# apply arbitrary SQL through the same execution engine used for provisioning
gov.provisioning.apply_sql(conn, "SELECT 1;", dialect="postgresql", dry_run=True)
```

**[`examples/enterprise_setup.py`](examples/enterprise_setup.py) is itself built on top of
`GovernanceFacade`** — see the [Enterprise setup script](#enterprise-setup-script-examplesenterprise_setuppy)
section below for a full, runnable, real-world example of the facade driving discovery,
access-control CRUD, policy checks, and per-dialect SQL provisioning end to end. Test
coverage for the facade lives in [`tests/test_facade.py`](tests/test_facade.py).

## Installation

### From PyPI

```bash
pip install ikidgov
```

This installs the `ikidgov` console command along with the importable `ikidgov` Python
package.

### From source (development install)

```bash
git clone <this repository>
cd ikidgov
python -m pip install -e ".[dev]"
```

### Optional: Docker Compose stack

Only needed if you want local Postgres/MySQL/MSSQL containers to experiment against — see
[Docker Compose stack](#docker-compose-stack-optional-unrelated-to-the-enterprise-setup-script)
below. It is unrelated to `examples/enterprise_setup.py`, which never touches Docker.

```bash
cp .env.example .env   # adjust values if needed; see "Secrets & credentials" below
docker compose up -d --wait
```

### Requirements

- Python 3.10 or newer
- PyYAML, SQLAlchemy, and the driver for whichever SQL backend(s) you target
  (`psycopg2-binary` for Postgres, `pymysql` for MySQL, `pyodbc` for MSSQL)
- Docker is entirely optional — it's only used by the standalone Docker Compose stack
  below, never by `examples/enterprise_setup.py`

## Quick start (CLI)

```bash
# 1. Scan a file and register its schema
ikidgov scan --type csv --path customers.csv --owner jdoe

# 2. Scan a SQL table with the shared governance YAML and a PostgreSQL backend
ikidgov scan --type sql --path ./data/sqlite/registry.db --table employees --owner jdoe --backend postgres --config config/governance.yaml

# 3. Scan the same table with MySQL or MSSQL
ikidgov scan --type sql --path ./data/sqlite/registry.db --table employees --owner jdoe --backend mysql --config config/governance.yaml
ikidgov scan --type sql --path ./data/sqlite/registry.db --table employees --owner jdoe --backend mssql --config config/governance.yaml

# 2. Classify the columns
ikidgov classify --dataset-id 1

# 3. Check whether a role can access a column
ikidgov policy-check --actor-role analyst --action-type select --dataset-id 1 --column email

# 4. Compile policy output for a SQL dialect
ikidgov policy-compile --policy restrict_pii --table employees --dialect mysql --format text
```

Every subcommand accepts `--format json` (default) or `--format text` for output rendering.

> Prefer scripting in Python? Every one of these steps is also a one-liner on
> [`GovernanceFacade`](#governancefacade--the-one-class-you-need) — `gov.scan(...)`,
> `gov.classify(...)`, `gov.check_access(...)`, `gov.compile_grants(...)`.

## Configuration

The main configuration file is [config/governance.yaml](config/governance.yaml). It keeps
governance settings in one place:

- roles and their permissions
- role-scoped account credentials
- connector defaults (per source type: `csv`, `json`, `sql`)
- policy-related metadata

Example:

```yaml
roles:
  analyst:
    description: Consumes data within policy limits
    account:
      username: analyst
      password: "<set a strong password — do not commit real passwords>"
    permissions:
      - select
    scope: policy_restricted

connectors:
  csv:
    default_type: string
```

### Config resolution order

ikidgov looks for a config file in this order (first match wins):

1. An explicit path passed to `load_config(path)` / the tool's `--config` option, where
   applicable
2. `$IKIDGOV_CONFIG`, if set
3. `governance.<environment>.yaml` in the current working directory, if `$IKIDGOV_ENV` or
   `$APP_ENV` is set and the file exists
4. `governance.yaml` in the current working directory
5. `config/governance.<environment>.yaml` under the current working directory
6. The bundled `config/governance.yaml` shipped with the package

Environment-specific example files are included in [config](config):

- [config/governance.dev.yaml](config/governance.dev.yaml)
- [config/governance.staging.yaml](config/governance.staging.yaml)
- [config/governance.prod.yaml](config/governance.prod.yaml)

Try them with either the environment variable or the CLI flag:

```bash
IKIDGOV_ENV=dev ikidgov show-config
ikidgov --env staging show-config
ikidgov --env prod show-config
```

### Secrets & credentials

- **Never commit real passwords.** The `governance.*.yaml` files under `config/` are
  _examples_ — replace every `password` field with a real secret sourced from your
  environment or secrets manager before using a profile outside local development.
- If a role's `account.password` is left unset, `policy-compile` will refuse to generate
  `CREATE USER` / `CREATE LOGIN` SQL for that role rather than falling back to a default —
  you must set a password explicitly for any role that needs a provisioned database account.
- `.env` is for local, disposable Docker Compose credentials only. Copy `.env.example` to
  `.env` and keep the real `.env` out of version control (see `.gitignore`).

## Docker Compose stack (optional, unrelated to the enterprise setup script)

The repository also includes an optional Docker Compose stack that spins up local
PostgreSQL, MySQL, and MSSQL containers for ad-hoc experimentation.

```bash
cp .env.example .env
docker compose up -d --wait
```

This is entirely optional and is **not** used by `examples/enterprise_setup.py` — that
script talks to databases exclusively through connection strings (see below), so it works
identically against this local stack, a cloud-hosted database, or nothing but SQLite. Docker
is never started, stopped, or otherwise managed by the script.

> Note: the bundled `scan` CLI command currently discovers schema from **SQLite** files for
> the `sql` source type (`--type sql --path <file> --table <name>`). It is not (yet) a
> multi-dialect `scan` target — the multi-dialect path is `policy-compile` /
> `enterprise_setup.py` provisioning, described below.

## Core modules

| Module                  | Responsibility                                                       |
| ----------------------- | -------------------------------------------------------------------- |
| `metadata_registry`     | Stores datasets, columns, owners, tags, and sensitivity labels       |
| `connectors`            | CSV, JSON, and SQL (SQLite) schema-discovery helpers                 |
| `classification_engine` | Applies built-in or plugin detectors to tag column sensitivity       |
| `policy_engine`         | Evaluates access decisions and compiles role grants into dialect SQL |
| `access_control`        | Role-based CRUD for roles, permissions, and access entries           |

Modules are registered as `4p.modules` entry points (see `pyproject.toml`) and detectors as
`4p.detectors` entry points, so both are discoverable and swappable without changing core code.
[`GovernanceFacade`](#governancefacade--the-one-class-you-need) is the recommended way to use
all five together.

## Enterprise setup script (`examples/enterprise_setup.py`)

[`examples/enterprise_setup.py`](examples/enterprise_setup.py) is a runnable walkthrough of
the whole governance model, **built entirely on top of [`GovernanceFacade`](#governancefacade--the-one-class-you-need)**:
it provisions example tables, prints a role/account overview, runs the access-control CRUD
and policy-check demos, and compiles + applies per-role database grants for SQLite,
PostgreSQL, MySQL, and MSSQL.

**It talks to databases through connection strings only.** There is no Docker dependency and
no container management anywhere in the script — bring your own running database (a local
install, a managed/cloud instance, or a container you started yourself), or just use the
zero-setup SQLite default.

### 1. Install the package

```bash
git clone <this repository>
cd ikidgov
python -m pip install -e ".[dev]"
```

This pulls in SQLAlchemy plus the drivers for every supported backend (`psycopg2-binary`,
`pymysql`, `pyodbc`). MSSQL also requires the [Microsoft ODBC Driver 18 for SQL
Server](https://learn.microsoft.com/sql/connect/odbc/linux-mac/installing-the-microsoft-odbc-driver-for-sql-server)
to be installed on your machine.

### 2. Try it with zero setup (SQLite)

```bash
python examples/enterprise_setup.py --dry-run --skip-demo   # preview only, no writes
python examples/enterprise_setup.py                         # apply — writes ./data/sqlite/registry.db
python examples/enterprise_setup.py --teardown               # drop the example tables
```

### 3. Point it at a real PostgreSQL / MySQL / MSSQL server

Provide a connection string using any one of these, in priority order:

| Priority | Method                                                                   | Scope                       |
| -------- | ------------------------------------------------------------------------ | --------------------------- |
| 1        | `--connection-string "<url>"`                                            | single `--dialect` run only |
| 2        | Env var: `IKIDGOV_POSTGRES_URL` / `IKIDGOV_MYSQL_URL` / `IKIDGOV_MSSQL_URL` | that dialect                |
| 3        | `<dialect>.connection_string` (or `.dsn`) in your governance YAML        | that dialect                |
| 4        | _(SQLite only)_ a local file, default `./data/sqlite/registry.db`        | sqlite                      |

```bash
# via environment variable
export IKIDGOV_POSTGRES_URL="postgresql://user:pw@host:5432/db"
python examples/enterprise_setup.py --dialect postgresql

export IKIDGOV_MYSQL_URL="mysql+pymysql://user:pw@host:3306/db"
python examples/enterprise_setup.py --dialect mysql

export IKIDGOV_MSSQL_URL="mssql+pyodbc://user:pw@host:1433/db?driver=ODBC+Driver+18+for+SQL+Server"
python examples/enterprise_setup.py --dialect mssql

# or pass the connection string directly for a single dialect
python examples/enterprise_setup.py --dialect postgresql \
  --connection-string "postgresql://user:pw@host:5432/db"
```

If nothing is configured for a server-backed dialect, the script exits immediately with an
actionable error — it never falls back to a guessed or default credential.

Run every dialect in one pass (each still resolves its own connection independently):

```bash
python examples/enterprise_setup.py --dialect all --dry-run   # preview across all four
python examples/enterprise_setup.py --dialect all             # apply to all four
python examples/enterprise_setup.py --dialect all --teardown  # reset all four
```

### 4. Wire in per-role database accounts (optional)

For every role in your governance config that has `account.password` (or
`account.password_env`) set, the script compiles and applies `CREATE USER` / `CREATE ROLE` /
`GRANT` statements scoped to that role's permissions. Roles without a configured password are
skipped with a message — never given a shared or guessed password.

```yaml
roles:
  analyst:
    account:
      username: analyst
      password_env: ANALYST_DB_PASSWORD # preferred over a plaintext `password:` field
    permissions:
      - select
    scope: policy_restricted
```

### 5. Use a specific governance profile

```bash
python examples/enterprise_setup.py --dialect postgresql --config config/governance.yaml
IKIDGOV_ENV=dev python examples/enterprise_setup.py --dry-run
```

### Useful flags

| Flag                                            | Effect                                                       |
| ----------------------------------------------- | ------------------------------------------------------------ |
| `--dialect {sqlite,postgresql,mysql,mssql,all}` | Which backend(s) to target (default `sqlite`)                |
| `--connection-string`                           | Explicit connection string (single dialect only)             |
| `--sqlite-path`                                 | Override the SQLite file location                            |
| `--config`                                      | Path to a specific governance YAML                           |
| `--dry-run`                                     | Print what would run without executing anything              |
| `--teardown`                                    | Drop the example tables/schemas before re-applying setup SQL |
| `--skip-demo`                                   | Skip the access-control CRUD and policy-check demos          |

See [examples/GUIDE.md](examples/GUIDE.md) for the full walkthrough, including the
role/account reference and config-file format.

## Multi-role standard setup (Database Administrator)

These are setup instructions written for a **senior database administrator** standing up
ikidgov's role-based access model on a new instance — the checklist you'd hand to whoever
owns least-privilege enforcement for the database layer. It only touches
`config/governance.yaml` and the `ikidgov` CLI; follow it top to bottom the first time, then
repeat steps 2–5 whenever roles change.

### Step 1 — Confirm the standard role set

ikidgov ships six roles as the baseline standard. Review this table against your org's
actual access model before changing anything — rename, extend, or retire roles here, but
keep the underlying principle: **one role per distinct, explainable set of permissions**,
never one role per person.

| Role              | Typical owner        | Responsibility                                               | Default scope         |
| ----------------- | -------------------- | ------------------------------------------------------------ | --------------------- |
| `admin`           | Platform/DevOps team | Full control over registry, policies, and roles              | none (unrestricted)   |
| `data_owner`      | Business/domain lead | Accountable for a dataset's classification and access grants | `owned_datasets_only` |
| `data_steward`    | Data engineer        | Classifies data, proposes policy changes within a domain     | `domain_restricted`   |
| `analyst`         | Data/BI consumer     | Reads data within policy limits                              | `policy_restricted`   |
| `auditor`         | Compliance/security  | Reviews governance decisions, cannot alter state             | `read_only`           |
| `service_account` | System integration   | Programmatic access via scoped API tokens                    | `token_restricted`    |

### Step 2 — Set the standard in `config/governance.yaml`

`config/governance.yaml` is the single source of truth the policy engine reads at runtime —
whatever is listed under `permissions:` for a role is the complete set of actions that role
will ever be allowed, on every dialect. Nothing is granted implicitly. This is the full,
current file for reference; edit it in place (or copy it to an environment-specific
`governance.<env>.yaml`, see [Config resolution order](#config-resolution-order)):

```yaml
roles:
  admin:
    description: Full control over registry, policies, and roles
    account:
      username: admin
      password: null
    permissions:
      - all
    scope: null

  data_owner:
    description: Accountable for a dataset's classification and access grants
    account:
      username: data_owner
      password: null
    permissions:
      - select
      - insert
      - update
      - delete
      - create
      - alter
      - drop
      - grant_access
      - approve_classification
    scope: owned_datasets_only

  data_steward:
    description: Classifies data and proposes policy changes within a domain
    account:
      username: data_steward
      password: null
    permissions:
      - select
      - insert
      - update
      - delete
      - create
      - alter
      - drop
      - classify
      - propose_policy
    scope: domain_restricted

  analyst:
    description: Consumes data within policy limits
    account:
      username: analyst
      password: null
    permissions:
      - select
    scope: policy_restricted

  auditor:
    description: Reviews governance decisions, cannot alter state
    account:
      username: auditor
      password: null
    permissions:
      - read_audit_log
    scope: read_only

  service_account:
    description: Programmatic access via scoped API tokens
    account:
      username: service_account
      password: null
    permissions:
      - select
    scope: token_restricted

connectors:
  csv:
    default_type: string
  json:
    default_type: string
  sql:
    default_type: string

sqlite:
  mode: direct
  path: ./data/sqlite/registry.db
  database_path: ./data/sqlite/registry.db

postgresql:
  mode: direct
  connection_string_env: IKIDGOV_POSTGRES_URL
  dsn_env: IKIDGOV_POSTGRES_URL
  note: set IKIDGOV_POSTGRES_URL to your PostgreSQL connection string

mysql:
  mode: direct
  connection_string_env: IKIDGOV_MYSQL_URL
  dsn_env: IKIDGOV_MYSQL_URL
  note: set IKIDGOV_MYSQL_URL to your MySQL connection string

mssql:
  mode: direct
  connection_string_env: IKIDGOV_MSSQL_URL
  dsn_env: IKIDGOV_MSSQL_URL
  note: set IKIDGOV_MSSQL_URL and install the Microsoft ODBC Driver 18 for SQL Server to connect from this host
```

Every `password: null` above is intentional — a role with no `password` or `password_env`
set is a **role definition without a live account**. That's the correct default for a fresh
checkout; you turn a role into a real login in the next step.

### Step 3 — Assign a login credential per role

For every role that needs an actual database account, replace `password: null` with
`password_env` pointing at an environment variable — never commit a plaintext password:

```yaml
data_steward:
  account:
    username: data_steward
    password_env: DATA_STEWARD_DB_PASSWORD
```

Then set that variable wherever your DBA tooling reads secrets from (shell environment,
`.env` for local work only, or your secrets manager for anything shared):

```bash
export ADMIN_DB_PASSWORD="<strong, unique password>"
export DATA_OWNER_DB_PASSWORD="<strong, unique password>"
export DATA_STEWARD_DB_PASSWORD="<strong, unique password>"
export ANALYST_DB_PASSWORD="<strong, unique password>"
export AUDITOR_DB_PASSWORD="<strong, unique password>"
export SERVICE_ACCOUNT_DB_PASSWORD="<strong, unique password>"
```

See [Secrets & credentials](#secrets--credentials) for the full policy on what belongs in
`.env` versus a secrets manager.

### Step 4 — Compile and review the grant SQL before applying it

Use the `policy-compile` CLI command to turn each role's `permissions:` list into real
`CREATE USER` / `CREATE ROLE` / `GRANT` SQL for your target dialect — review it the same way
you'd review any DDL before running it against a production instance:

```bash
# Preview as text (redacts secrets by default)
ikidgov policy-compile --policy restrict_pii --table hr.employees --dialect postgresql --format text
ikidgov policy-compile --policy restrict_pii --table hr.employees --dialect mssql --format text
ikidgov policy-compile --policy restrict_pii --table employees --dialect mysql --format text

# Structured output (JSON), useful for piping into your own change-management tooling
ikidgov policy-compile --policy restrict_pii --table hr.employees --dialect postgresql
```

Once the SQL looks right, run it with your normal DBA tooling for that engine (`psql`,
`mysql`, `sqlcmd`, or your migration runner of choice) against the target instance. Each
role's account is scoped to exactly the actions listed in `permissions:` — a `data_steward`
account cannot run anything a `data_steward` role isn't configured for, on any engine.

### Step 5 — Validate the standard is actually enforced

Before signing off, confirm the compiled grants match the access model from Step 1 using
`policy-check`:

```bash
ikidgov policy-check --actor-role analyst --action-type select --dataset-id 1 --column email
ikidgov policy-check --actor-role analyst --action-type delete --dataset-id 1 --column email
ikidgov policy-check --actor-role auditor --action-type update --dataset-id 1 --column email
```

Expect `analyst` → `select` allowed and `delete` denied, `auditor` → any write denied. Any
mismatch means the role's `permissions:` list in `governance.yaml` needs correcting before
it goes further — the policy engine is fail-closed by design, so an unexpected `DENIED` is
almost always a missing permission, and an unexpected `ALLOWED` is almost always a
permission that shouldn't have been granted.

### Step 6 — Automate the standard with `GovernanceFacade` (optional)

Everything in Steps 4–5 is also available as one Python object — useful if you script role
provisioning as part of a larger migration/change-management job instead of running the CLI
by hand. See [`GovernanceFacade`](#governancefacade--the-one-class-you-need) for the full
surface; the calls relevant to this setup are:

```python
from ikidgov.facade import GovernanceFacade

gov = GovernanceFacade(config_path="config/governance.yaml")

# Step 4 equivalent: compile a role's grants into dialect SQL, ready to review/apply
grants = gov.compile_grants("restrict_pii", "hr.employees", dialect="postgresql")
print("\n".join(grants["sql"]))

# resolve the target connection string the same way the CLI would (CLI override >
# env var > governance config > .env > default), then apply the reviewed SQL yourself
conn = gov.provisioning.resolve_connection_string(
    "postgresql", cli_override=None, config=gov.config,
    sqlite_path="./data/sqlite/registry.db")
gov.provisioning.apply_sql(conn, "\n".join(grants["sql"]), dialect="postgresql", dry_run=True)

# Step 5 equivalent: assert a role's effective access matches the standard, e.g. in a
# CI job or pre-deploy check that fails the build on drift
decision = gov.check_access(
    actor_role="analyst", action_type="select", role_permissions=["select"])
assert decision.allowed

decision = gov.check_access(
    actor_role="analyst", action_type="delete", role_permissions=["select"])
assert not decision.allowed

# role/permission/access CRUD, if you manage governance records themselves as data
gov.access_control.create_role(name="data_steward", description="Domain-restricted steward")
```

`gov.provisioning.apply_sql(..., dry_run=True)` never opens a database connection — flip to
`dry_run=False` only once the compiled SQL has been reviewed the same way you'd review it
from the CLI in Step 4.

### Step 7 — Keep it current

- Treat `config/governance.yaml` (and its `dev`/`staging`/`prod` variants) as you would a
  database migration: changes go through code review before they reach a real instance.
- Re-run Step 4's `--format text` preview after every role/permission edit so you see the
  exact SQL diff before applying it.
- New system, new integration, new team: add a new role in Step 1's table first. Don't
  reuse an existing role's credentials for a new purpose — a shared account with mixed
  purposes breaks the audit trail this whole model exists to provide.

## Testing

Install the dev extras and run the test suite locally:

```bash
python -m pip install -e ".[dev]"
pytest
```

The suite covers CLI smoke tests, config resolution/overrides, access-control CRUD, policy
evaluation, module isolation, the `GovernanceFacade` sub-facades, and the example
provisioning scripts.

## Project layout

```
src/ikidgov/
  cli/            argparse-based CLI and subcommands
  facade.py       GovernanceFacade — one-stop entry point over every module below
  config_loader.py   governance YAML resolution
  connectors/     CSV / JSON / SQL schema discovery
  core/           shared base classes (Module, Connector, Detector, Decision, CRUD base)
  detectors/      built-in and plugin PII detectors
  modules/        access_control, classification_engine, metadata_registry, policy_engine
  policies/       policy definitions (YAML), e.g. restrict_pii.yaml
config/           governance.yaml + per-environment overrides
examples/         enterprise_setup.py (facade-driven, connection-string based, no Docker) and seed SQL
init/             one-shot DB seed scripts used by the optional docker-compose.yml stack
tests/            pytest suite (including tests/test_facade.py)
```

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
