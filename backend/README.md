# Portfolio API Backend

FastAPI application for the WebbPulse portfolio, running on AWS Lambda behind an
API Gateway HTTP API with DynamoDB as the datastore. The public API contract is
unchanged from the previous Postgres deployment; only the runtime moved.

## Layout

```
app/
├── main.py                 FastAPI app, CORS, middleware
├── lambda_handler.py       Lambda entrypoint: app.lambda_handler.handler
├── config.py               Settings (env vars, the APP_SECRETS_ARN JSON secret)
├── version.py              The version reported by OpenAPI, / and /health
├── api/v1/api.py           The composition root: mounts every domain under /api/v1
├── domains/                One package per domain, no imports between them
│   ├── content/            posts, categories, the site-content singleton
│   │   ├── router.py       The domain's routers, prefixes and tags
│   │   ├── posts.py        Posts and categories route handlers
│   │   ├── site_content.py Singleton get and admin update
│   │   ├── service.py      Site-content seeding
│   │   ├── defaults.py     The literal default hero, about and values copy
│   │   ├── repository.py   The tables this domain touches
│   │   └── schemas/        Pydantic models: category, post, site_content
│   ├── resume/             projects, experience, skills, education, certifications
│   │   ├── router.py       The domain's routers, prefixes and tags
│   │   ├── crud_router.py  Factory for the soft-deleted CRUD resources
│   │   ├── projects.py     CRUD plus the featured_only and sort-mode list
│   │   ├── repository.py   The tables this domain touches
│   │   └── schemas/        Pydantic models, one per resource
│   ├── identity/           POST /api/v1/admin/login, the only signing-key user
│   │   ├── router.py       Login: limiter, timing equaliser, token mint
│   │   ├── service.py      Admin user seeding and reconciliation from settings
│   │   ├── repository.py   users
│   │   └── schemas/        Pydantic models: user, token
│   └── public/             /, /health, /sitemap.xml, /robots.txt
│       ├── router.py       The unauthenticated, unprefixed surface
│       ├── seo.py          /sitemap.xml and /robots.txt
│       ├── service.py      database_status() for the health check
│       └── repository.py   Read-only: posts and site-content
├── core/                   Cross-cutting, shared by every domain
│   ├── security.py         bcrypt, JWT, get_current_user, require_admin
│   ├── login_limiter.py    Login brute-force limiter backed by DynamoDB
│   ├── middleware.py       Trailing-slash, seeding, request logging
│   └── logging.py          Powertools logger
└── db/                     Shared datastore layer
    ├── tables.py           Canonical table and index definitions
    ├── client.py           boto3 resource/client factories
    ├── serializer.py       Python <-> DynamoDB value encoding
    ├── repository.py       Generic repository (counters, uniqueness, soft delete)
    ├── ordering.py         In-memory sort orders matching the old SQL queries
    └── entities.py         Repository instances per table
scripts/
├── create_local_tables.py  Create the tables against DynamoDB Local
├── migrate_postgres_to_dynamo.py  One-time Postgres -> DynamoDB copy
├── build_lambda.sh         Build dist/function.zip for python3.13 arm64
└── build_image.sh          Build one domain's container image
tests/                      pytest suite backed by moto
```

## Configuration

| Variable | Purpose | Default |
| --- | --- | --- |
| `DYNAMODB_TABLE_PREFIX` | Tables are named `{prefix}-{entity}` | `webbpulse-development` |
| `DYNAMODB_ENDPOINT_URL` | Point at DynamoDB Local | unset |
| `APP_SECRETS_ARN` | When set, secrets are read once per execution environment from the single Secrets Manager secret `webbpulse-<env>/app`, whose value is a JSON object keyed by `SECRET_KEY`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `ADMIN_EMAIL` | unset |
| `SECRET_KEY`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `ADMIN_EMAIL` | Secrets when not using Secrets Manager; env values win over Secrets Manager, per field | required |
| `ENVIRONMENT` | Environment label | `development` |
| `CORS_ORIGINS` | Comma-separated allowed origins (localhost dev origins are always added) | empty |
| `SITE_URL` | Base URL used in sitemap and robots | `https://www.webbpulse.com` |
| `LOG_LEVEL` | Powertools logger level | `INFO` |
| `POWERTOOLS_SERVICE_NAME` | Logger service name | `webbpulse-portfolio-api` |
| `POWERTOOLS_METRICS_NAMESPACE` | Reserved for metrics | `WebbPulse/Portfolio` |
| `LOGIN_MAX_FAILURES` / `LOGIN_FAILURE_WINDOW_SECONDS` | Login limiter | `10` / `900` |

Constructing the settings reads no AWS and no secret. The four secret fields are
filled from the `APP_SECRETS_ARN` JSON blob on first read, and a domain that
needs one calls `settings.require_secrets(...)`, so a missing secret fails at
use rather than at import. That is what lets `public` run with no
`secretsmanager:GetSecretValue` at all: an import-time read would fail it on
every cold start before any route was reached.

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
venv/bin/ruff check app tests
venv/bin/ruff format --check app tests
```

Those are the commands `.github/workflows/test-backend.yml` runs through the org
reusable workflow `python-ci.yml@v1`. Ruff replaced the black, isort and flake8
trio in PR 4, because that workflow runs ruff and adopting it was what let CI
reach the `webbpulse` package in CodeArtifact.

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

## Container images

Each of the four domains ships as its own container image, run on Lambda behind
the Lambda Web Adapter. There is no Lambda handler and no Mangum: the adapter
starts before the application, turns each invoke into an ordinary HTTP request
against `127.0.0.1:8080`, and turns the response back. The same image therefore
runs on Lambda and under `docker run`, which is what makes the compose stack
below a real reproduction rather than an approximation.

One `Dockerfile` builds all four. `DOMAIN` selects the entrypoint the image
runs; nothing else about the four differs except the readiness check, which the
next section explains.

### Building one domain

The image installs `webbpulse`, which is published only to CodeArtifact, so the
build needs a token. Mint one and keep it in the environment; it is never
written to a file and never committed.

```bash
export CODEARTIFACT_AUTH_TOKEN="$(aws codeartifact get-authorization-token \
  --domain webbpulse --domain-owner 432410731887 \
  --region us-west-2 --query authorizationToken --output text)"

scripts/build_image.sh content
scripts/build_image.sh public sha-1a2b3c4
```

The token reaches pip as a BuildKit secret mount, never as a build arg and never
as an `ENV`: both of those persist in `docker history` for anyone who can pull
the image. The script also derives the readiness protocol from the domain, sets
the platform to `linux/arm64` to match `terraform/lambda.tf`, and otherwise
passes straight through to `docker buildx build`. `PUSH=1` pushes instead of
loading into the local daemon. Run it with no arguments for the full list of
environment overrides.

Tokens expire after 12 hours. A build that fails with a 401 from the
CodeArtifact index usually just needs a fresh one.

### The readiness check, and why `public` is different

`AWS_LWA_READINESS_CHECK_PATH` is `/health` on all four images, but the protocol
is not. The adapter polls the readiness check on every cold start, so it must
not do I/O.

Three of the four get `create_app`'s liveness-only `GET /health`, which returns
200 without touching DynamoDB. That is what the shared route is for, and those
three use the HTTP check.

`public` is the exception. Its own `GET /health` reads the site-content
singleton to report `database`, the deploy smoke test asserts on that field, and
`build_domain_app` therefore sets `include_health=False` for it so the
database-reading route is the only `/health` its application declares. Pointing
the adapter at that path would put a DynamoDB read in front of every `public`
cold start and would fail the function to start whenever the table was briefly
unavailable. So `public` builds with `AWS_LWA_READINESS_CHECK_PROTOCOL=tcp`: the
adapter waits for the port to accept a connection and polls no route at all,
and `GET /health` goes on answering the smoke test exactly as it does today.

`scripts/build_image.sh` derives this, so a caller never has to know it. The
Dockerfile rejects the wrong pairing rather than trusting the caller, because
getting it wrong is a delayed failure: the image starts fine and only fails on a
cold start that races an unavailable table.

### Running all four locally

```bash
export CODEARTIFACT_AUTH_TOKEN="$(aws codeartifact get-authorization-token \
  --domain webbpulse --domain-owner 432410731887 \
  --region us-west-2 --query authorizationToken --output text)"

docker compose --profile domains up --build
```

| Service | Host port | Routes |
| --- | --- | --- |
| `content` | 8010 | posts, categories, the site-content singleton, under `/api/v1` |
| `resume` | 8011 | projects, experience, skills, education, certifications, under `/api/v1` |
| `identity` | 8012 | `POST /api/v1/admin/login` |
| `public` | 8013 | `/`, `/health`, `/sitemap.xml`, `/robots.txt` |
| `dynamodb-local` | 8001 | the datastore all four share |

The four are behind the `domains` compose profile, so a bare `docker compose up`
still starts only DynamoDB Local and the uvicorn workflow above keeps working
unchanged. Create the tables once with `scripts/create_local_tables.py` before
the first run.

Each domain answers only its own routes, which is the point of running them
this way: a request to a path that belongs to another domain 404s here exactly
as it would if API Gateway routed it to the wrong function.

```bash
curl localhost:8013/health          # public, the database check
curl localhost:8010/api/v1/posts/   # content
curl localhost:8010/                # 404: that route belongs to public
```

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
credentials for the target account) in the environment, plus `psycopg2-binary`, which
is installed by `requirements-dev.txt` only and is not part of the Lambda package.
