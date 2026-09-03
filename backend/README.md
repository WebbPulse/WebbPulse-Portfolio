# Portfolio API Backend

FastAPI application for the WebbPulse portfolio, running on AWS Lambda behind an
API Gateway HTTP API with DynamoDB as the datastore. The public API contract is
unchanged from the previous Postgres deployment; only the runtime moved.

## Layout

```
app/
├── main.py                 FastAPI app, CORS, middleware, /health
├── lambda_handler.py       Lambda entrypoint: app.lambda_handler.handler
├── config.py               Settings (env vars, optional SSM secrets)
├── api/
│   ├── seo.py              /sitemap.xml and /robots.txt
│   └── v1/
│       ├── api.py          Router wiring under /api/v1
│       ├── crud_router.py  Factory for the soft-deleted CRUD resources
│       └── endpoints/      posts, admin, projects, experience, skills,
│                           education, certifications, site_content
├── core/
│   ├── security.py         bcrypt, JWT, get_current_user, require_admin
│   ├── admin.py            Admin user seeding from settings
│   ├── login_limiter.py    Login brute-force limiter backed by DynamoDB
│   ├── middleware.py       Trailing-slash, admin-seed, request logging
│   └── logging.py          Powertools logger
├── db/
│   ├── tables.py           Canonical table and index definitions
│   ├── client.py           boto3 resource/client factories
│   ├── serializer.py       Python <-> DynamoDB value encoding
│   ├── repository.py       Generic repository (counters, uniqueness, soft delete)
│   ├── ordering.py         In-memory sort orders matching the old SQL queries
│   └── entities.py         Repository instances per table
└── schemas/                Pydantic request/response models
scripts/
├── create_local_tables.py  Create the tables against DynamoDB Local
├── migrate_postgres_to_dynamo.py  One-time Postgres -> DynamoDB copy
└── build_lambda.sh         Build dist/function.zip for python3.13 arm64
tests/                      pytest suite backed by moto
```

## Configuration

| Variable | Purpose | Default |
| --- | --- | --- |
| `DYNAMODB_TABLE_PREFIX` | Tables are named `{prefix}-{entity}` | `webbpulse-development` |
| `DYNAMODB_ENDPOINT_URL` | Point at DynamoDB Local | unset |
| `SSM_PARAMETER_PREFIX` | When set, secrets are read from SSM SecureStrings `{prefix}/secret-key`, `/admin-username`, `/admin-password`, `/admin-email` | unset |
| `SECRET_KEY`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `ADMIN_EMAIL` | Secrets when not using SSM; env values win over SSM | required |
| `ENVIRONMENT` | Environment label | `development` |
| `CORS_ORIGINS` | Comma-separated allowed origins (localhost dev origins are always added) | empty |
| `SITE_URL` | Base URL used in sitemap and robots | `https://www.webbpulse.com` |
| `LOG_LEVEL` | Powertools logger level | `INFO` |
| `POWERTOOLS_SERVICE_NAME` | Logger service name | `webbpulse-portfolio-api` |
| `POWERTOOLS_METRICS_NAMESPACE` | Reserved for metrics | `WebbPulse/Portfolio` |
| `LOGIN_MAX_FAILURES` / `LOGIN_FAILURE_WINDOW_SECONDS` | Login limiter | `10` / `900` |

Settings fail fast at import time if any of the four secrets cannot be resolved.

## Data model

One on-demand table per entity: `users`, `categories`, `posts`, `projects`,
`experience`, `skills`, `education`, `certifications`, `site-content`, plus a
shared `meta` table.

- Entity tables have a numeric hash key `id`. Ids come from atomic counters so
  they stay integers and keep the existing values after migration.
- `posts` has two GSIs: `published-index` (`published_flag` = `"1"`, range
  `published_at`) for public listings and `category-index` (`category_id`,
  range `id`) for the category delete guard. Draft posts carry no
  `published_flag`, so they never appear in the index.
- `meta` (hash key `pk`, TTL attribute `ttl`) holds `COUNTER#<entity>` items,
  `UNIQUE#<entity>#<field>#<value>` lookup items that enforce unique slugs,
  usernames and emails inside a transaction, and `LOGIN_FAIL#<ip>` items for
  the login limiter.
- Timestamps are stored as fixed-width UTC ISO-8601 strings, dates as
  `YYYY-MM-DD`, and absent values are omitted rather than stored as NULL.

`app/db/tables.py` is the single source of truth for table and index names.

## Local development

```bash
uv venv --python 3.13 venv
VIRTUAL_ENV=$PWD/venv uv pip install -r requirements-dev.txt

docker compose up -d
export DYNAMODB_ENDPOINT_URL=http://localhost:8001
export DYNAMODB_TABLE_PREFIX=webbpulse-development
export SECRET_KEY=dev-secret ADMIN_USERNAME=admin ADMIN_PASSWORD=admin ADMIN_EMAIL=admin@example.com
venv/bin/python scripts/create_local_tables.py
venv/bin/uvicorn app.main:app --reload
```

The admin user is created (or reconciled with the settings) on the first
request handled by each process, so there is no separate seed step. Docs are
served at `/docs` and `/redoc`.

## Tests and lint

```bash
venv/bin/python -m pytest
venv/bin/python -m black --check app tests scripts
venv/bin/python -m isort --check-only app tests scripts
venv/bin/python -m flake8 app tests scripts
```

Tests run against moto; no AWS credentials or local DynamoDB are needed. See
`tests/README.md`.

## Building the Lambda artifact

```bash
scripts/build_lambda.sh
```

Installs `requirements.txt` for `manylinux2014_aarch64` / CPython 3.13, adds
`app/`, strips caches and test packages, and writes a deterministic
`dist/function.zip`. The handler is `app.lambda_handler.handler`; run the
function on `python3.13`, `arm64`.

## Migrating from Postgres

```bash
venv/bin/python scripts/migrate_postgres_to_dynamo.py "$DATABASE_URL" --dry-run
venv/bin/python scripts/migrate_postgres_to_dynamo.py "$DATABASE_URL"
venv/bin/python scripts/migrate_postgres_to_dynamo.py "$DATABASE_URL" --verify
```

The script copies every row with its original id, writes the uniqueness lookup
items and sets each counter to the highest id. It refuses to run when any target
table already holds data, including an admin user seeded by a Lambda that served
a request first; `--replace` purges every entity table, its lookup items and its
counter before importing. `--dry-run` reports what the target currently holds.
`--verify` re-reads Postgres and reports any row or field that differs in
DynamoDB, exiting non-zero when it finds drift. It needs `DYNAMODB_TABLE_PREFIX` (and AWS
credentials for the target account) in the environment.
