# Portfolio API Backend

One FastAPI application, the `public` domain, running as a container-image
Lambda behind an API Gateway HTTP API, with one DynamoDB cache table. It serves
the live system figures the site shows. Every other page is static content in
`frontend/src/content/`, and the frontend build writes `sitemap.xml` and
`robots.txt`.

## Layout

```
app/
├── common/                 Non-domain logic. Imports no domain package
│   ├── config.py           Settings, re-exported from composition
│   ├── version.py          The version reported by OpenAPI, / and /health
│   ├── composition/        Root A: the whole surface in one process
│   │   ├── wiring.py       The domain registry and build_domain_app
│   │   ├── app.py          Every router on one application
│   │   └── settings.py     Portfolio's Settings on the shared package's base
│   ├── core/               logging
│   └── db/                 tables, client
└── domains/
    └── public/             /, /health, /api/v1/public/figures
scripts/                    create_local_tables, build_image.sh
tests/                      pytest suite backed by moto
```

`app/domains/public/entrypoint.py` is root B, the module the deployed function
runs. The registry in `wiring.py` keeps the shared `webbpulse.composition`
shape, so a second domain would be one more row and one more entrypoint.

## Routes

| Route | What it does |
| --- | --- |
| `GET /` | Service name and version |
| `GET /health` | Liveness plus a read on the cache table, 503 when the read fails |
| `GET /api/v1/public/figures` | Live public figures, cached in `public-cache` and refreshed about every 15 minutes |

## Configuration

| Variable | Purpose | Default |
| --- | --- | --- |
| `DYNAMODB_TABLE_PREFIX` | Tables are named `{prefix}-{entity}` | `webbpulse-development` |
| `DYNAMODB_ENDPOINT_URL` | Point at DynamoDB Local | unset |
| `ENVIRONMENT` | Environment label | `development` |
| `CORS_ORIGINS` | Comma-separated origins; localhost dev origins are always added | the portfolio origin and localhost |
| `LOG_LEVEL` | Root log level | `INFO` |

The function reads no secret, so it has no `secretsmanager:GetSecretValue` grant.

## Data model

One on-demand table, `public-cache`, keyed by a string `pk` with TTL on `ttl`.
It holds the computed `public-figures` item and its refresh lease.
`app/common/db/tables.py` is the single source of truth for its shape.

## Local development

Dependencies live in `pyproject.toml` and are pinned by the committed `uv.lock`.
Install uv 0.12.10, then point it at the CodeArtifact index that serves the
private `webbpulse` package:

```bash
export UV_INDEX_CODEARTIFACT_USERNAME=aws
export UV_INDEX_CODEARTIFACT_PASSWORD="$(aws codeartifact get-authorization-token \
  --domain webbpulse --domain-owner 432410731887 --region us-west-2 \
  --query authorizationToken --output text)"

uv sync

docker compose up -d
export DYNAMODB_ENDPOINT_URL=http://localhost:8001
export DYNAMODB_TABLE_PREFIX=webbpulse-development
uv run python scripts/create_local_tables.py
```

**Root A**, `app.common.composition.app`, is built from the same `wiring.DOMAINS`
list as the entrypoint. Nothing deploys it.

```bash
uv run uvicorn app.common.composition.app:app --reload   # http://localhost:8000
```

**Root B**, the way Lambda runs it. `run_uvicorn` binds `AWS_LWA_PORT`, then
`PORT`, then 8080.

```bash
PORT=8013 uv run python -m app.domains.public.entrypoint
```

Docs are at `/docs` and `/redoc`.

## Tests and lint

CI runs these through `.github/workflows/ci.yml`, which delegates to the org
reusable `python-ci.yml@v3` and additionally runs `pyright`, `bandit -r app -ll`
and `pip-audit` over `uv export`.

```bash
uv run python -m pytest
uv run ruff check app tests
uv run ruff format --check app tests
```

Tests run against moto; no AWS credentials or local DynamoDB are needed. See
`tests/README.md`. `pytest.ini` defines the markers `unit`, `api` and
`integration`.

`tests/entrypoints/test_gateway_routes.py` keeps the gateway's route keys in
`apigateway.tf` and the served paths in agreement in both directions.

## Logging

One JSON object per line on stdout, from `webbpulse.logging`. The entrypoint's
`main()` calls `configure_logging(...)` before building the application, and
`app/common/core/logging.py` exports the `logger` every module imports.

`request_id` comes from a `webbpulse.log_context` ContextVar that the formatter
merges into every record. It is bound by `RequestIdMiddleware`: an inbound
`X-Request-ID` is honoured and bounded to 128 characters, a UUID4 minted
otherwise, and the value echoed on the response. It also goes onto the active
OpenTelemetry span as `webbpulse.request_id`.

Extra fields go through `extra={...}`.

```python
logger.info("Refreshed figures", extra={"count": 3})
```

## Container image

The `Dockerfile` builds the `public` image. `DOMAIN` selects the entrypoint and
the adapter readiness protocol; the `CMD` is
`python -m app.domains.${DOMAIN}.entrypoint`. There is no Lambda handler and no
Mangum: the Lambda Web Adapter starts before the application and turns each
invoke into an HTTP request against `127.0.0.1:8080`, so the same image runs on
Lambda and under `docker run`.

The image installs `webbpulse` from CodeArtifact, so the build needs a token.

```bash
export CODEARTIFACT_AUTH_TOKEN="$(aws codeartifact get-authorization-token \
  --domain webbpulse --domain-owner 432410731887 \
  --region us-west-2 --query authorizationToken --output text)"

scripts/build_image.sh public sha-1a2b3c4
```

The token reaches pip as a BuildKit secret mount, never as a build arg and never
as an `ENV`: both persist in `docker history` for anyone who can pull the image.
The script sets the platform to `linux/arm64`, and otherwise passes through to
`docker buildx build`. `PUSH=1` pushes instead of loading locally. Tokens last 12
hours; a 401 from the index usually just needs a fresh one.

### The readiness check

The adapter polls its readiness check on every cold start, so it must not do
I/O. `public` serves its own `GET /health`, which reads the cache table to report
`database`, and `build_domain_app` sets `include_health=False` for it. So
`public` builds with `AWS_LWA_READINESS_CHECK_PROTOCOL=tcp`, and the adapter
waits for the port to accept a connection instead. The Dockerfile derives this
from `DOMAIN` through the final `FROM readiness-${DOMAIN}` stage, so a `DOMAIN`
with no stage fails the build.

### Running the image locally

```bash
docker compose --profile domains up --build
curl localhost:8013/health
```

The service is behind the `domains` profile, so a bare `docker compose up`
starts only DynamoDB Local on 8001. Create the table once before the first run.

## Deploys

A push to `staging` or `main` touching `backend/**` runs `deploy-backend.yml`,
a thin caller of the org `lambda-domains-deploy.yml@v3`. That workflow picks the
GitHub Environment from the branch, builds the image through
`container-image.yml@v3`, points the function at its digest through `lambda-image-deploy.yml@v3`, and
invokes it with a synthesised HTTP API v2 event asserting `GET /health` is 200.
A rerun whose `sha-<commit>` tag already exists reuses that image rather than
failing on the IMMUTABLE repository. The e2e suite, which the deploy triggers, then runs read only against the live
gateway.

The only gate is `STAGING_DEPLOY_ENABLED`, which turns staging deploys off and
never touches production.

The shared workflow stamps the newest published `webbpulse` version into the
`DEPENDENCY_RESOLUTION` build arg. It sits above the CodeArtifact layer that
floats `webbpulse`, so that layer rebuilds when a new `webbpulse` is published and
otherwise comes from the buildx cache. A change to `pyproject.toml` or `uv.lock`
still rebuilds it immediately, because those are copied in above it. Dispatching
the workflow with `fresh-dependencies=true` substitutes the run id, which forces
the layer to rebuild.

## Scripts

| Script | What it does |
| --- | --- |
| `create_local_tables.py` | Create every table against DynamoDB Local |
| `build_image.sh` | Build the domain image |
