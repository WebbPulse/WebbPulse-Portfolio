# Portfolio API Backend

Four FastAPI applications, one per domain (`content`, `resume`, `identity`,
`public`), each running as its own container-image Lambda behind an API Gateway
HTTP API, with DynamoDB as the datastore.

## Layout

```
app/
├── config.py               Settings (env vars, the APP_SECRETS_ARN JSON secret)
├── version.py              The version reported by OpenAPI, / and /health
├── composition/            Root A: the whole surface in one process
│   ├── wiring.py           The four domains, and build_domain_app
│   ├── app.py              Every domain's routers on one application
│   ├── identity.py         Builds the shared identity router from webbpulse.identity
│   └── identity_hooks.py   Product callbacks the identity package calls
├── entrypoints/            Root B: one module per deployed function
│   └── {content,resume,identity,public}.py
├── domains/                One package per domain, no imports between them
│   ├── content/            posts, categories, the site-content singleton
│   ├── resume/             projects, experience, skills, education, certifications
│   ├── identity/           POST /api/v1/admin/login, the legacy bearer login
│   └── public/             /, /health, /sitemap.xml, /robots.txt
├── core/                   security, login_limiter, middleware, logging, identity_claims
└── db/                     tables, client, serializer, repository, ordering, entities
scripts/                    create_local_tables, build_image.sh, the migration scripts
tests/                      pytest suite backed by moto
```

The `/api/auth` surface is not repo code. `app/composition/identity.py` calls
`build_identity_router` from `webbpulse.identity`, so sessions, email links, MFA,
OAuth and passkeys all ship in the shared package. `app/domains/identity/` holds
only the legacy bearer login.

## Configuration

| Variable | Purpose | Default |
| --- | --- | --- |
| `DYNAMODB_TABLE_PREFIX` | Tables are named `{prefix}-{entity}` | `webbpulse-development` |
| `DYNAMODB_ENDPOINT_URL` | Point at DynamoDB Local | unset |
| `APP_SECRETS_ARN` | The Secrets Manager secret `webbpulse-<env>/app`, a JSON object keyed by `SECRET_KEY`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `ADMIN_EMAIL` | unset |
| `SECRET_KEY`, `ADMIN_*` | The same four as env vars. An env value wins per field | required |
| `ENVIRONMENT` | Environment label | `development` |
| `CORS_ORIGINS` | Comma-separated origins; localhost dev origins are always added | empty |
| `SITE_URL` | Base URL used in sitemap and robots | `https://www.webbpulse.com` |
| `LOG_LEVEL` | Root log level | `INFO` |
| `LOGIN_MAX_FAILURES` / `LOGIN_FAILURE_WINDOW_SECONDS` | Login limiter | `10` / `900` |

The identity function additionally receives `IDENTITY_*` variables from
`module.identity` and `lambda_domains.tf`. See `docs/identity-cutover.md`.

**Secrets resolve lazily and are checked once at startup.** Importing
`app.config` reads nothing and constructing `Settings` makes no Secrets Manager
call, so every entrypoint is importable with no credentials. The blob is fetched
on first read and cached for the life of the execution environment. Each domain
declares what it cannot serve without in `Domain.requires_secrets`, and
`check_required_secrets` raises on `staging` and `production` and warns
elsewhere. `identity` needs all four, `content` and `resume` need `SECRET_KEY`,
and `public` needs none, which is why `public` needs no
`secretsmanager:GetSecretValue` at all.

## Data model

One on-demand table per entity: `users`, `categories`, `posts`, `projects`,
`experience`, `skills`, `education`, `certifications`, `site-content`, plus
`meta` and `rate-limits`, plus the identity tables the platform module owns
(`credentials`, `refresh-tokens`, `login-attempts`, `identity-tokens`,
`totp-factors`, `recovery-codes`, `oauth-states`, `oauth-links`, `passkeys`,
`webauthn-challenges`).

- Entity tables have a numeric hash key `id`, from atomic counters, so ids stay
  integers and kept their values through the Postgres migration.
- `posts` has `published-index` (`published_flag` = `"1"`, range `published_at`)
  for public listings and `category-index` (`category_id`, range `id`) for the
  category delete guard. Draft posts carry no `published_flag`, so they never
  appear in the index.
- `meta` (hash key `pk`, TTL `ttl`) holds `COUNTER#<entity>` items and
  `UNIQUE#<entity>#<field>#<value>` lookup items that enforce unique slugs,
  usernames and emails inside a transaction.
- `rate-limits` (hash key `pk`) holds the login limiter's `LOGIN_FAIL#<ip>`
  items.
- Timestamps are fixed-width UTC ISO-8601 strings, dates are `YYYY-MM-DD`, and
  absent values are omitted rather than stored as NULL.

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
```

**All 44 routes in one process.** `app.composition.app` is root A, built from
the same `wiring.DOMAINS` list the four entrypoints read. Nothing deploys it.

```bash
venv/bin/uvicorn app.composition.app:app --reload   # http://localhost:8000
```

**One domain, the way Lambda runs it.** `app.entrypoints.<domain>` is root B and
is exactly what the image runs. `run_uvicorn` binds `AWS_LWA_PORT`, then `PORT`,
then 8080.

```bash
PORT=8010 venv/bin/python -m app.entrypoints.content
PORT=8013 venv/bin/python -m app.entrypoints.public
```

This is the faithful one: a domain here answers only its own routes, so a
request for another domain's path 404s exactly as it would if API Gateway routed
it to the wrong function.

The admin user is created or reconciled on the first request handled by each
process, so there is no separate seed step. Docs are at `/docs` and `/redoc`.

## Tests and lint

```bash
venv/bin/python -m pytest
venv/bin/ruff check app tests
venv/bin/ruff format --check app tests
```

Tests run against moto; no AWS credentials or local DynamoDB are needed. See
`tests/README.md`. `pytest.ini` defines the markers `unit`, `api`,
`integration`, `auth` and `admin`, so `-m unit` runs one category.

CI runs the same commands through `.github/workflows/ci.yml`, which delegates to
the org reusable `python-ci.yml@v2` and additionally runs `pyright`, `bandit -r
app -ll` and `pip-audit -r requirements.txt`.

`tests/entrypoints/test_gateway_routes.py` is load-bearing: it keeps the
gateway's route keys and the served paths in agreement in both directions, and
asserts the set of routes requiring an administrator equals the flagged keys in
`apigateway.tf`.

## Logging

One JSON object per line on stdout, from `webbpulse.logging`. Each entrypoint's
`main()` calls `configure_logging(...)` before building the application, and
`app/core/logging.py` exports the `logger` every module imports.

`request_id` and `user_id` come from `webbpulse.log_context` ContextVars that
the formatter merges into every record. `request_id` is bound by
`RequestIdMiddleware`: an inbound `X-Request-ID` is honoured and bounded to 128
characters, a UUID4 minted otherwise, and the value echoed on the response.
`user_id` is bound by `get_current_user` once it resolves a principal, so an
anonymous request has no `user_id` key rather than a null one. Both also go onto
the active OpenTelemetry span as `webbpulse.request_id` and `webbpulse.user_id`.

Extra fields go through `extra={...}`; the keyword form some call sites used
under Powertools raises.

```python
logger.info("Seeded site content", extra={"id": SITE_CONTENT_ID})
```

`aws-lambda-powertools` is gone. Its correlation is a handler decorator and
there is no handler under the Web Adapter, so it never ran. No custom metrics
are emitted yet; `webbpulse.metrics` is what to use when that starts, and it
needs an explicit `namespace`.

## Container images

One `Dockerfile` builds all four images. `DOMAIN` selects the entrypoint and
`READINESS_PROTOCOL` the adapter check; the `CMD` is
`python -m app.entrypoints.${DOMAIN}`. There is no Lambda handler and no Mangum:
the Lambda Web Adapter starts before the application and turns each invoke into
an HTTP request against `127.0.0.1:8080`, so the same image runs on Lambda and
under `docker run`.

### Building one domain

The image installs `webbpulse` from CodeArtifact, so the build needs a token.

```bash
export CODEARTIFACT_AUTH_TOKEN="$(aws codeartifact get-authorization-token \
  --domain webbpulse --domain-owner 432410731887 \
  --region us-west-2 --query authorizationToken --output text)"

scripts/build_image.sh content
scripts/build_image.sh public sha-1a2b3c4
```

The token reaches pip as a BuildKit secret mount, never as a build arg and never
as an `ENV`: both persist in `docker history` for anyone who can pull the image.
The script derives the readiness protocol from the domain, sets the platform to
`linux/arm64`, and otherwise passes through to `docker buildx build`. `PUSH=1`
pushes instead of loading locally. Tokens last 12 hours; a 401 from the index
usually just needs a fresh one.

### The readiness check, and why `public` is different

`AWS_LWA_READINESS_CHECK_PATH` is `/health` on all four, but the protocol is
not. The adapter polls it on every cold start, so it must not do I/O.

Three domains get `create_app`'s liveness-only `GET /health`, which returns 200
without touching DynamoDB, and use the HTTP check. `public` is the exception:
its own `GET /health` reads the site-content singleton to report `database`, the
deploy smoke test asserts on that field, and `build_domain_app` sets
`include_health=False` for it. Pointing the adapter at that path would put a
DynamoDB read in front of every `public` cold start. So `public` builds with
`AWS_LWA_READINESS_CHECK_PROTOCOL=tcp`, and the adapter waits for the port to
accept a connection instead.

`build_image.sh` derives this, and the Dockerfile rejects the wrong pairing
rather than trusting the caller, because getting it wrong is a delayed failure:
the image starts fine and only fails on a cold start that races an unavailable
table.

### Running all four locally

```bash
export CODEARTIFACT_AUTH_TOKEN="$(aws codeartifact get-authorization-token \
  --domain webbpulse --domain-owner 432410731887 \
  --region us-west-2 --query authorizationToken --output text)"

docker compose --profile domains up --build
```

| Service | Host port | Routes |
| --- | --- | --- |
| `content` | 8010 | posts, categories, site-content, under `/api/v1` |
| `resume` | 8011 | projects, experience, skills, education, certifications |
| `identity` | 8012 | `POST /api/v1/admin/login` and the `/api/auth` surface |
| `public` | 8013 | `/`, `/health`, `/sitemap.xml`, `/robots.txt` |
| `dynamodb-local` | 8001 | the datastore all four share |

The four are behind the `domains` profile, so a bare `docker compose up` still
starts only DynamoDB Local. Create the tables once before the first run.

```bash
curl localhost:8013/health          # public, the database check
curl localhost:8010/api/v1/posts/   # content
curl localhost:8010/                # 404: that route belongs to public
```

## Deploys

A push to `staging` or `main` touching `backend/**` runs `deploy-backend.yml`:
`resolve-env` picks the GitHub Environment from the branch, a matrix builds the
four images through the org `container-image.yml@v2`, `image-map` assembles a
digest-pinned map from the uploaded manifests, `deploy-images` points each
function at its digest through `lambda-image-deploy.yml@v2`, `smoke-domains`
invokes each function with a synthesised HTTP API v2 event asserting
`GET /health` is 200, and `verify-route-cuts` probes the live gateway with
`scripts/verify_route_cut.sh` to confirm each domain's paths are served by that
domain's function.

Two repository variables gate it: `BACKEND_IMAGE_BUILD_ENABLED` on `resolve-env`
and `BACKEND_IMAGE_DEPLOY_ENABLED` on `deploy-images`. They are separate on
purpose, so the build can run while nothing is updated.

## Scripts

| Script | What it does |
| --- | --- |
| `create_local_tables.py` | Create every table against DynamoDB Local |
| `build_image.sh` | Build one domain's image |
| `migrate_credentials_to_identity.py` | Copy bcrypt hashes from `users` into the identity `credentials` table |
| `clear_legacy_credentials.py` | Remove the legacy `hashed_password` column once the copy is confirmed. Dry run unless `--apply` |
| `migrate_postgres_to_dynamo.py` | The one-time Postgres copy. Historical |

`clear_legacy_credentials.py` is identity runbook Step 11 and is still pending in
production. See `docs/identity-cutover.md` before running it.
