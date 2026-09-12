# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

WebbPulse is a personal portfolio website with a blog and admin panel. It is a full-stack monorepo with a React/TypeScript frontend and a FastAPI/Python backend.

## Commands

### Frontend (`frontend/`)

```bash
npm run dev:local        # Local dev server on port 5173 (proxies /api to localhost:8000)
npm run build            # TypeScript compile + Vite production build
npm run lint             # ESLint check
npm run lint:fix         # ESLint with auto-fixes
npm run format           # Prettier format
npm run format:check     # Prettier check without fixing
npm run test             # Vitest in watch mode
npm run test:run         # Run tests once with coverage
npm run test:ui          # Vitest UI mode
```

Run a single test file:
```bash
npm run test:run -- --reporter=verbose path/to/test.spec.ts
```

### Backend (`backend/`)

```bash
# Local DynamoDB via docker-compose, then the API against it
docker compose up -d
export DYNAMODB_ENDPOINT_URL=<local dynamodb url>
python scripts/create_local_tables.py

# All 44 routes in one process (root A, every domain's routers on one app)
uvicorn app.composition.app:app --reload

# One domain, exactly as the image runs it (root B; the Dockerfile CMD is
# `python -m app.entrypoints.${DOMAIN}`). run_uvicorn binds AWS_LWA_PORT,
# then PORT, then 8080
PORT=8010 python -m app.entrypoints.content

# All four as the real images, under the Lambda Web Adapter. Needs a
# CodeArtifact token; see backend/README.md
docker compose --profile domains up --build

# Tests (moto-backed, no AWS or database needed)
pytest tests/                                      # All tests
pytest tests/test_name.py::test_function_name -v   # Single test

# Lint / format (ruff replaced flake8, black and isort)
ruff check app tests
ruff format --check app tests
```

## Architecture

### Frontend

- **Pages**: `/` (portfolio), `/blog`, `/blog/:slug`, `/admin`
- **API layer**: All API calls go through `src/services/api.ts` (`apiService`). The transport is `@webbpulse/api-client` and the startup configuration is `@webbpulse/config`, both from the org CodeArtifact repository. That client rejects on a non 2xx, so `ApiService` adapts it back into the `{ data, error }` envelope every page component reads; the envelope is Portfolio's own and is unchanged
- **Shared packages**: `@webbpulse/api-client`, `@webbpulse/auth`, `@webbpulse/config`, `@webbpulse/tsconfig` and `@webbpulse/eslint-config` resolve from CodeArtifact through `frontend/.npmrc`, all pinned to `^0.4.0`. Run `aws codeartifact login` before installing; see `frontend/README.md`
- **Auth**: mid migration, selected by `VITE_AUTH_MODE`. The default `bearer` mode is the current backend: `POST /api/v1/admin/login` answers with a token that lives in `localStorage`, held by `src/services/bearerTokenStore.ts` (a local copy of the `TokenStore` that `@webbpulse/auth` 0.4.0 removed). The `identity` mode is `AuthClient` from `@webbpulse/auth`, which holds a short lived access token in memory and refreshes it from an httpOnly cookie. It is written, typed and tested but not switched on: the identity function now serves the JWKS and discovery documents plus sixteen POST routes under `/api/auth` (M2's six, M3's four email routes and M4's six MFA routes), including the `/api/auth/login`, `/api/auth/refresh` and `/api/auth/logout` that `AuthClient` needs, so what is left is the build time flip rather than any missing backend. See `IDENTITY_CUTOVER` in `frontend/src/services/api.ts`
- **Dev proxy**: Vite proxies `/api/*` → `http://localhost:8000` in local dev; a production build reads `VITE_API_BASE_URL` (set by `deploy-frontend.yml` from the `API_BASE_URL` environment variable) and falls back to `https://api.webbpulse.com/api/v1`

### Backend

- **Runtime**: four FastAPI apps, one per domain (`content`, `resume`, `identity`, `public`), each its own Lambda (`webbpulse-<env>-<domain>`, Python 3.13, arm64) built as a container image from one `backend/Dockerfile`. There is no Lambda handler and no Mangum: the [Lambda Web Adapter](https://github.com/awslabs/aws-lambda-web-adapter) runs ahead of the process and turns each invoke into an HTTP request against `127.0.0.1:8080`, so the same image runs on Lambda and under `docker run`. The image's `CMD` is `python -m app.entrypoints.${DOMAIN}`. API Gateway routes to them with explicit route keys and no `$default`: an unmatched path is a gateway 404, not a fall-through. `tests/entrypoints/test_gateway_routes.py` is what keeps the key set and the served paths in agreement, in both directions. **CORS is owned by API Gateway, not by the functions**: with only explicit method keys and no `$default`, an `OPTIONS` preflight matches no route and gets a gateway 404 with no CORS headers, so `module "api"` sets `cors_configuration` from `local.cors_origins`. The gateway answers preflight without invoking an integration and attaches the CORS headers to every response it produces, authorizer 401s included, which no in-process middleware can reach. The functions' own `CORSMiddleware` still runs and is configured to match
- **REST API**: All routes under `/api/v1/` prefix. OpenAPI docs at `/docs`. Ids stay integers and list endpoints keep `skip`/`limit` so the frontend contract is unchanged
- **Auth**: JWT tokens (HS256) and bcrypt password hashing, both from `webbpulse.security` (the package's `security` extra, PyJWT and bcrypt). `app/core/security.py` is a thin adapter over it: it keeps `verify_token`'s `sub`-or-`None` contract, so an expired and a forged token are still the same 401 to a caller, and keeps its own `HTTPBearer()` rather than the package's `bearer_claims`. Since fastapi 0.141 the inherited `HTTPBearer` answers 401 with a `WWW-Authenticate: Bearer` challenge to a missing or non-bearer `Authorization` header, which is what the gateway's JWT authorizer already answers on enforced routes; 403 is now only an authorization verdict on a request that did authenticate. Users have an `is_admin` boolean flag. The admin user is seeded from the `APP_SECRETS_ARN` secret on the first request in the `identity` process, which is the domain that owns the `users` table. `content` seeds only the `site-content` singleton it owns, and `resume` and `public` seed nothing
- **Database**: DynamoDB, one table per entity (`webbpulse-<env>-<entity>`: users, categories, posts, projects, experience, skills, education, certifications, site-content, meta). Integer ids come from counter items in `meta`; uniqueness (username, email, slug) is enforced with lookup items inside `TransactWriteItems`. `posts` has `published-index` and `category-index` GSIs
- **Config**: env vars `DYNAMODB_TABLE_PREFIX`, `APP_SECRETS_ARN` (signing key + admin credentials come from one JSON secret, `webbpulse-<env>/app`), `ENVIRONMENT`, `CORS_ORIGINS`, `SITE_URL`, `LOG_LEVEL`; `DYNAMODB_ENDPOINT_URL` points at a local DynamoDB
- **Secrets are resolved lazily, and checked once at startup.** Importing `app.config` reads nothing: constructing `Settings` makes no Secrets Manager call, so every entrypoint is importable with no credentials and a domain that never reads a secret never needs `secretsmanager:GetSecretValue`. An environment variable wins per field; otherwise the blob is fetched on the first read and cached for the life of the execution environment. Each domain declares what it cannot serve a request without in `Domain.requires_secrets`, and `check_required_secrets` calls `settings.require_secrets(...)` for exactly those before the process serves anything — a raise on `staging` and `production`, a warning elsewhere so a checkout with no AWS still runs. `identity` needs all four (it mints tokens and seeds the admin), `content` and `resume` need `SECRET_KEY` to verify bearer tokens, and `public` needs none
- **Rate limiting**: API Gateway stage throttling (burst 200, rate 100). There is no in-process limiter
- **Observability**: OpenTelemetry through `webbpulse.otel` (Transaction Search via the OTLP endpoint), X-Ray active tracing, and 7-day CloudWatch log groups for the four functions and the HTTP API access log. Logging is `webbpulse.logging`'s JSON formatter, configured by each entrypoint's `main()`, with `request_id` and `user_id` merged onto every line from `webbpulse.log_context` (bound by `RequestIdMiddleware` and by `get_current_user`). aws-lambda-powertools is gone: its `inject_lambda_context` correlation is a handler decorator and there is no handler under the Web Adapter. No custom metrics are emitted yet

### Key files

| File | Purpose |
|---|---|
| `backend/app/composition/wiring.py` | The four domains and `build_domain_app` — the single list both roots read |
| `backend/app/composition/app.py` | Root A: every domain's routers on one app, for local dev and the test suite. Nothing deploys it |
| `backend/app/entrypoints/<domain>.py` | Root B: one module per deployed function, the image's `CMD` |
| `backend/Dockerfile` | Builds all four images; `DOMAIN` selects the entrypoint, `READINESS_PROTOCOL` the adapter check |
| `backend/app/config.py` | Pydantic Settings, env vars and the `APP_SECRETS_ARN` JSON secret |
| `backend/app/domains/` | One package per domain (content, resume, identity, public); no imports between them |
| `backend/app/core/`, `backend/app/db/` | Cross-cutting code every domain shares: settings, auth, limiter, logging, DynamoDB |
| `backend/scripts/build_image.sh` | Builds one domain's container image |
| `backend/tests/fixtures/route_contract.json` | The published contract: 44 routes, 42 documented operations |
| `terraform/dynamodb.tf` | Table map — attributes, GSIs, TTL, PITR per entity |
| `terraform/lambda.tf` | The four domain functions, execution roles, ECR repositories |
| `terraform/apigateway.tf` | HTTP API, `$default` stage, `api.webbpulse.com` custom domain |
| `frontend/src/services/api.ts` | Centralized API client |
| `frontend/vite.config.ts` | Vite config with dev proxy |

### Deployment

- **Infrastructure**: `terraform/` — all AWS resources are defined in code: DynamoDB tables, the Lambda function and its artifact bucket, the HTTP API, S3/CloudFront frontend, and the Route 53 records (written into the management-account zone through `aws.dns`). Nothing is clicked in the console
- **Terraform Cloud**: org `WebbPulse`, workspaces `WebbPulse-Portfolio` (production, bound to `main`) and `WebbPulse-Portfolio-staging` (bound to `staging`). AWS credentials come from TFC dynamic provider credentials — no static keys. Terraform never ships application code: the function is created with a placeholder package and `ignore_changes` on the code attributes, and CI updates the code
- **Region**: `us-west-2` (the CloudFront cert is provisioned in `us-east-1` via a second provider alias)
- **Custom domains** exist only when `staging_profile = "full"` and a zone id is set; otherwise CloudFront and the HTTP API serve on their default hostnames
- **CI/CD**: GitHub Actions

| Workflow | Trigger | What it does |
|---|---|---|
| `.github/workflows/test-backend.yml` | PR to `main`/`staging`, paths `backend/**` | delegates to the org reusable `python-ci.yml@v1`: CodeArtifact login, then pytest on moto (no database service), `ruff check` and `ruff format --check` |
| `.github/workflows/test-frontend.yml` | PR to `main`/`staging`, paths `frontend/**` | delegates to the org reusable `typescript-ci.yml@v1`: CodeArtifact login, then lint, format check, Vitest with coverage and build |
| `.github/workflows/deploy-backend.yml` | push to `main`/`staging`, paths `backend/**` | builds the four domain images, pushes them to ECR as `sha-<commit>`, points each function at its digest-pinned URI, smoke tests each one, then verifies the live gateway serves every domain's paths from that domain's function |
| `.github/workflows/deploy-frontend.yml` | push to `main`/`staging`, paths `frontend/**` | CodeArtifact login, `npm run build` with `VITE_API_BASE_URL`, waits for any active TFC run, `s3 sync --delete`, CloudFront invalidation. Stays inline rather than using the org `spa-deploy.yml@v1`, which has no TFC wait step |

Deploy workflows pick the `production` or `staging` GitHub Environment from the branch and assume `vars.AWS_DEPLOY_ROLE_ARN` via OIDC. The TFC-polling step keeps a code deploy from racing a Terraform apply that is touching the same function.

Environment-scoped inputs each GitHub Environment must define:

| Name | Kind | Used by |
|---|---|---|
| `AWS_DEPLOY_ROLE_ARN` | variable | both deploy workflows — terraform role `webbpulse-<env>-github-actions-deploy` |
| `API_BASE_URL` | variable | backend smoke test and the frontend build (terraform output `backend_url`, no trailing slash) |
| `FRONTEND_S3_BUCKET` | variable | `deploy-frontend.yml` (terraform output `frontend_bucket`) |
| `CLOUDFRONT_DISTRIBUTION_ID` | variable | `deploy-frontend.yml` (terraform output `cloudfront_distribution_id`) |
| `CODEARTIFACT_DOMAIN_OWNER` | variable | repository-scoped; the account id owning the `webbpulse` CodeArtifact domain, used by both frontend workflows |
| `CI_AWS_ROLE_ARN` | variable | repository-scoped; the CI role `test-frontend.yml` assumes to read CodeArtifact |
| `TFC_API_TOKEN` | secret | both deploy workflows — HCP Terraform token for workspace polling; optional, the wait step is skipped when it is unset |

Deploys on `staging` are gated by the repository-level variable `STAGING_DEPLOY_ENABLED` (`true` once the staging workspace has applied and the Environment variables above exist). It has to be repository-scoped because a job-level `if` is evaluated before the job's Environment is selected, so Environment variables are invisible there.

## Branching and deploys

```
feature/* ──PR──▶ staging ──PR──▶ main
                     │              │
                     ▼              ▼
           AWS 621554169154   AWS 036807648992
              (staging)          (production)
```

- Branch new work from `staging`, not `main`. PR into `staging`. Releasing is a PR from `staging` into `main` — that PR is the release boundary.
- Never commit directly to `main` or `staging`. Never force-push either. Stacked PRs bottom out on `staging`.
- Hotfixes branch from `main` and PR into `main`, then are immediately back-merged `main` → `staging`. Skipping the back-merge is how the branches silently diverge.
- Both accounts are `us-west-2`. `staging` carries the same rules as `main` because a TFC workspace bound to that branch assumes an IAM role in a real AWS account — the branch is a credential, not a scratch space.

**Protection.** The WebbPulse org is on GitHub Team: `main` and `staging` are covered by repository rulesets (pull request required, force-push and deletion blocked, bypassable only by the repository admin). The real gate is still Terraform Cloud manual apply on the production workspace: a merge cannot change AWS, only an apply can. CI runs on every PR but is not blocking — you have to read it.

### A staging branch does not imply staging infrastructure

The project declares a staging profile — `none`, `reduced`, or `full` — through the `staging_profile` Terraform variable. The staging workspace is wired to the staging AWS account, but with profile `none` it refuses to plan and provisions nothing. `reduced` provisions Lambda + DynamoDB + HTTP API + S3/CloudFront on default AWS hostnames; `full` adds the custom domains. Check the profile before assuming there is a staging environment to deploy to.

## Conventions

- **Admin/management email**: Use `tyler@webbpulse.com` for all management addresses (DMARC reporting, contact forms, etc.)

### Test markers (backend)

pytest.ini defines markers: `unit`, `api`, `integration`, `auth`, `admin`. Run a category with `-m unit` etc.

