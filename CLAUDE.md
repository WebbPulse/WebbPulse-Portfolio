# CLAUDE.md

Guidance for Claude Code (claude.ai/code) when working in this repository.

## Project Overview

WebbPulse is a personal portfolio website with a blog and admin panel. It is a
monorepo with a React/TypeScript frontend and four per-domain FastAPI/Python
Lambdas.

## Commands

### Frontend (`frontend/`)

```bash
npm run dev:local        # Dev server on 5173 (proxies /api to localhost:8000)
npm run dev:remote-api   # Dev server against https://api.webbpulse.com/api/v1
npm run build            # tsc -b + Vite production build
npm run lint             # ESLint
npm run lint:fix         # ESLint with auto-fixes
npm run format           # Prettier write
npm run format:check     # Prettier check
npm run test             # Vitest watch mode
npm run test:run         # Vitest once. CI appends -- --coverage
```

There is no `npm run dev`. Run a single test file with
`npm run test:run -- --reporter=verbose path/to/test.spec.ts`.

### Backend (`backend/`)

```bash
docker compose up -d
export DYNAMODB_ENDPOINT_URL=http://localhost:8001
python scripts/create_local_tables.py

# All 44 routes in one process (root A, every domain's routers on one app)
uvicorn app.common.composition.app:app --reload

# One domain, exactly as the image runs it (root B; the Dockerfile CMD is
# `python -m app.domains.${DOMAIN}.entrypoint`). run_uvicorn binds AWS_LWA_PORT,
# then PORT, then 8080
PORT=8010 python -m app.domains.content.entrypoint

# All four as the real images, under the Lambda Web Adapter. Needs a
# CodeArtifact token; see backend/README.md
docker compose --profile domains up --build

# Tests (moto-backed, no AWS or database needed)
pytest tests/
pytest tests/test_name.py::test_function_name -v

# Lint / format (ruff replaced flake8, black and isort)
ruff check app tests
ruff format --check app tests
```

## Architecture

### Frontend

- **Pages**: `/` (portfolio), `/blog`, `/blog/:slug`, `/privacy`,
  `/verify-email`, `/reset-password`, `/admin`
- **API layer**: All calls go through `src/services/api.ts` (`apiService`). The
  transport is `@webbpulse/api-client` and startup configuration is
  `@webbpulse/config`. That client rejects on a non-2xx, so `ApiService` adapts
  it back into the `{ data, error }` envelope every page component reads; the
  envelope is Portfolio's own and is unchanged
- **Shared packages**: `@webbpulse/api-client`, `auth`, `config`, `discovery`,
  `qrcode`, `tsconfig` and `eslint-config` resolve from CodeArtifact through
  `frontend/.npmrc`, all pinned to `^0.10.2`. Run `aws codeartifact login`
  before installing; see `frontend/README.md`
- **Auth**: identity only, with no build time switch. `AuthClient` from
  `@webbpulse/auth` holds a short-lived access token in memory and refreshes it
  from an httpOnly cookie, and `ApiService` always constructs one. The mode was
  once chosen by `VITE_AUTH_MODE`, which defaulted to `bearer`; the deploy
  stopped forwarding it in `ce34362` and silently shipped bearer bundles against
  the 24 JWT enforced admin route keys. The switch was removed rather than
  repaired, so `authMode.ts` and `bearerTokenStore.ts` no longer exist and
  `getAuthClient`/`getIdentityClient` never return null. A unit test
  (`built auth mode` in `src/services/api.test.ts`) and a `deploy-frontend.yml`
  step both fail if `VITE_AUTH_MODE` or `POST /api/v1/admin/login` comes back.
  The backend's legacy login route stays mounted and unused until a later PR
- **Dev proxy**: Vite proxies `/api/*` to `http://localhost:8000` in local dev; a
  production build reads `VITE_API_BASE_URL` and falls back to
  `https://api.webbpulse.com/api/v1`

### Backend

- **Runtime**: four FastAPI apps, one per domain (`content`, `resume`,
  `identity`, `public`), each its own Lambda (`webbpulse-<env>-<domain>`, Python
  3.13, arm64) built as a container image from one `backend/Dockerfile`. There is
  no Lambda handler and no Mangum: the Lambda Web Adapter runs ahead of the
  process and turns each invoke into an HTTP request against `127.0.0.1:8080`,
  so the same image runs on Lambda and under `docker run`. API Gateway routes
  with explicit route keys and no `$default`: an unmatched path is a gateway
  404, not a fall-through. `tests/entrypoints/test_gateway_routes.py` keeps the
  key set and the served paths in agreement, in both directions. **CORS is owned
  by API Gateway, not by the functions**: with only explicit method keys and no
  `$default`, an `OPTIONS` preflight matches no route and gets a gateway 404
  with no CORS headers, so `module "api"` sets `cors_configuration` from
  `local.cors_origins`. The gateway answers preflight without invoking an
  integration and attaches CORS headers to every response it produces,
  authorizer 401s included, which no in-process middleware can reach. The
  functions' own `CORSMiddleware` still runs and is configured to match
- **REST API**: All routes under `/api/v1/`. OpenAPI docs at `/docs`. Ids stay
  integers and list endpoints keep `skip`/`limit`, so the frontend contract is
  unchanged. The `/api/auth` surface comes from `webbpulse.identity` through
  `app/domains/identity/package_glue.py`, not from repo code
- **Auth**: the legacy bearer path is JWT HS256 and bcrypt from
  `webbpulse.security`; `app/common/core/security.py` is a thin adapter that keeps
  `verify_token`'s `sub`-or-`None` contract, so an expired and a forged token
  are the same 401 to a caller. `get_current_user` tries that token first and
  falls back to authorizer claims read by `app/core/identity_claims.py`. **The
  application never verifies the identity signature and has no KMS access**: the
  gateway is the verifier and claims arrive in `x-amzn-request-context`, which
  the Web Adapter writes from the invoke event. A route only receives claims if
  its route key is flagged, which is why the Terraform half is not optional
- **Database**: DynamoDB, one table per entity (`webbpulse-<env>-<entity>`).
  Integer ids come from counter items in `meta`; uniqueness (username, email,
  slug) is enforced with lookup items inside `TransactWriteItems`. `posts` has
  `published-index` and `category-index` GSIs. The login limiter uses the
  `rate-limits` table
- **Config**: `DYNAMODB_TABLE_PREFIX`, `APP_SECRETS_ARN` (signing key and admin
  credentials in one JSON secret, `webbpulse-<env>/app`), `ENVIRONMENT`,
  `CORS_ORIGINS`, `SITE_URL`, `LOG_LEVEL`; `DYNAMODB_ENDPOINT_URL` points at a
  local DynamoDB
- **Secrets resolve lazily and are checked once at startup.** Importing
  `app.common.config` reads nothing and constructing `Settings` makes no Secrets
  Manager call, so every entrypoint is importable with no credentials. An env var
  wins per field; otherwise the blob is fetched on first read and cached for the
  life of the execution environment. Each domain declares what it needs in
  `Domain.requires_secrets`, and `check_required_secrets` raises on `staging`
  and `production` and warns elsewhere. `identity` needs all four, `content` and
  `resume` need `SECRET_KEY`, `public` needs none
- **Rate limiting**: API Gateway stage throttling (burst 200, rate 100), plus
  the login limiter. There is no general in-process limiter. Staging is never
  rate limited: every limiter follows `settings.rate_limiting_enabled`, the
  shared `webbpulse` convention that is False on `staging` and True elsewhere
- **Observability**: OpenTelemetry through `webbpulse.otel`, X-Ray active
  tracing, and 7-day CloudWatch log groups. Logging is `webbpulse.logging`'s
  JSON formatter with `request_id` and `user_id` merged onto every line from
  `webbpulse.log_context`. aws-lambda-powertools is gone: its correlation is a
  handler decorator and there is no handler under the Web Adapter. No custom
  metrics yet

### Key files

| File | Purpose |
|---|---|
| `backend/app/common/composition/wiring.py` | The four domains and `build_domain_app` |
| `backend/app/common/composition/app.py` | Root A: every domain's routers on one app. Nothing deploys it |
| `backend/app/domains/identity/package_glue.py` | Builds the `/api/auth` router from `webbpulse.identity` |
| `backend/app/domains/<domain>/entrypoint.py` | Root B: one module per deployed function |
| `backend/Dockerfile` | Builds all four images; `DOMAIN` selects the entrypoint, `READINESS_PROTOCOL` the adapter check |
| `backend/app/common/config.py` | Pydantic Settings and the `APP_SECRETS_ARN` JSON secret |
| `backend/app/core/identity_claims.py` | Reads authorizer claims in both native and gate shapes |
| `backend/app/common/db/tables.py` | Canonical table and index definitions |
| `backend/tests/fixtures/route_contract.json` | The published contract: 44 routes |
| `backend/tests/entrypoints/test_gateway_routes.py` | Keeps route keys, served paths and flagged admin routes in agreement |
| `terraform/dynamodb.tf` | Table map |
| `terraform/lambda_domains.tf` | The four domain functions, roles, environments |
| `terraform/apigateway.tf` | HTTP API, routes, the 24 flagged admin keys |
| `terraform/identity.tf` | The identity platform module |
| `frontend/src/services/api.ts` | Centralized API client |

### Deployment

- **Infrastructure**: `terraform/`. Nothing is clicked in the console
- **Terraform Cloud**: org `WebbPulse`, workspaces `WebbPulse-Portfolio`
  (production, bound to `main`) and `WebbPulse-Portfolio-staging` (bound to
  `staging`). Credentials come from TFC dynamic provider credentials. Terraform
  never ships application code: functions are created with a placeholder and
  `ignore_changes` on the code attributes, and CI updates the code
- **Region**: `us-west-2` (the CloudFront cert is in `us-east-1` via a provider
  alias)
- **Custom domains** exist only when `staging_profile = "full"` and a zone id is
  set

| Workflow | Trigger | What it does |
|---|---|---|
| `.github/workflows/ci.yml` | PR to `main`/`staging` | `dorny/paths-filter` gates a `Backend` job on the org `python-ci.yml@v3` (uv sync, pytest on moto per test domain, ruff, pyright, bandit, pip-audit) and a `Frontend` job on `typescript-ci.yml@v2` (lint, format check, Vitest with coverage, build). An `affected` job narrows the pytest shards to the domains the diff touches. `all-checks-passed` is the aggregating gate job |
| `.github/workflows/deploy-backend.yml` | push to `main`/`staging`, paths `backend/**` minus tests, e2e, scripts and docs | An `affected` job picks the domains to rebuild, then `container-image.yml@v3` builds those images, a digest-pinned `function-image-map` is assembled, `lambda-image-deploy.yml@v3` points the functions at them, and each function is invoke-smoke-tested on `GET /health`; the e2e suite verifies the live gateway |
| `.github/workflows/deploy-frontend.yml` | push to `main`/`staging`, paths `frontend/**` | Resolves the environment, then calls the org `spa-deploy.yml@v3`: CodeArtifact login, `npm run build`, `s3 sync --delete`, CloudFront invalidation |

There is no `test-backend.yml` or `test-frontend.yml`; CI is one `ci.yml`.

### Path-scoped runs

Both backend workflows run only for the domains a diff actually affects, worked
out by the org `actions/affected-domains@v3` action from the import closure of
each `app/domains/<name>/entrypoint.py`. In `ci.yml` the result becomes
`domains-filter` and `run-shared` on `python-ci.yml`, so a change to one domain
runs that domain's pytest shard plus the shared shard, while lint, type check and
security still read the whole backend. In `deploy-backend.yml` the diff base is
the head sha of the last successful run of that workflow on the same branch, which
is safe because a partial failure never becomes a base and so widens the next
diff; the result gates the build matrix, and a change to `deploy-backend.yml`
itself rebuilds every domain. `all-checks-passed` stays the required context and
counts a skipped shard as a pass, so no ruleset changes with this.

Deploy workflows pick the `production` or `staging` GitHub Environment from the
branch and assume `vars.AWS_DEPLOY_ROLE_ARN` via OIDC. Neither waits on HCP
Terraform: applies are confirmed by hand and never auto-run.

Environment-scoped inputs each GitHub Environment must define:

| Name | Kind | Used by |
|---|---|---|
| `AWS_DEPLOY_ROLE_ARN` | variable | both deploy workflows |
| `API_BASE_URL` | variable | the frontend build (terraform output `backend_url`, no trailing slash) |
| `FRONTEND_S3_BUCKET` | variable | `deploy-frontend.yml` |
| `CLOUDFRONT_DISTRIBUTION_ID` | variable | `deploy-frontend.yml` |
| `CODEARTIFACT_DOMAIN_OWNER` | variable | repository-scoped; the account owning the `webbpulse` CodeArtifact domain |
| `CI_AWS_ROLE_ARN` | variable | repository-scoped; the role `ci.yml` assumes to read CodeArtifact |

`codeartifact-domain-owner` is passed as a `with:` input to
`container-image.yml` and as a `secrets:` entry to `python-ci.yml`,
`typescript-ci.yml` and `spa-deploy.yml`. That is deliberate. Do not copy a
`secrets:` line from one caller to the other.

Deploys on `staging` are gated by the repository variable
`STAGING_DEPLOY_ENABLED`. It has to be repository-scoped because a job-level
`if` is evaluated before the job's Environment is selected, so Environment
variables are invisible there. `BACKEND_IMAGE_BUILD_ENABLED` and
`BACKEND_IMAGE_DEPLOY_ENABLED` separately gate the image build and the function
update.

## Branching and deploys

```
feature/* ──PR──▶ staging ──PR──▶ main
                     │              │
                     ▼              ▼
           AWS 621554169154   AWS 036807648992
              (staging)          (production)
```

- Branch new work from `staging`, not `main`. PR into `staging`. Releasing is a
  PR from `staging` into `main`; that PR is the release boundary.
- Never commit directly to `main` or `staging`. Never force-push either. Stacked
  PRs bottom out on `staging`.
- Use a merge commit, not a squash, for a `staging` into `main` release PR. A
  squash produces phantom conflicts on the next release.
- Hotfixes branch from `main` and PR into `main`, then are immediately
  back-merged `main` to `staging`. Skipping the back-merge is how the branches
  silently diverge.
- Both accounts are `us-west-2`. `staging` carries the same rules as `main`
  because a TFC workspace bound to that branch assumes an IAM role in a real AWS
  account: the branch is a credential, not a scratch space.

**Protection.** `main` and `staging` are covered by repository rulesets (pull
request required, force-push and deletion blocked, bypassable only by the
repository admin). The real gate is Terraform Cloud manual apply on the
production workspace: a merge cannot change AWS, only an apply can.

### A staging branch does not imply staging infrastructure

`staging_profile` is `none`, `reduced` or `full`. With `none` the staging
workspace refuses to plan and provisions nothing. `reduced` provisions Lambda,
DynamoDB, the HTTP API and S3/CloudFront on default AWS hostnames; `full` adds
the custom domains. Check the profile before assuming there is a staging
environment to deploy to.

## Gotchas

- **An API Gateway route key cannot end in a slash**, and a path part cannot mix
  a literal with a `{var}`. Both fail at apply with `BadRequestException` while
  the plan is green.
- **Explicit route keys need gateway CORS.** `OPTIONS` 404s once routes are
  method keys. Curl a preflight before declaring a flip live.
- **API Gateway CORS rejects `chrome-extension://` origins** at apply time.
- **`aws/spans` is a reserved log group.** Terraform cannot pre-create it. Let
  X-Ray create it on the first span, then set `manage_spans_log_group` to import
  it for retention.
- **Identity claims arrive as strings**, `exp` included, and the Web Adapter
  header is plain JSON, not base64.
- **`IDENTITY_RP_ID` is immutable per credential.** A passkey enrolled under a
  wrong RP id has to be re-enrolled, not fixed by a variable change.
- **Rotating a signing key is two applies** against `signing_key_count` and
  `active_signing_key`. Rotating material behind one key id strands every issued
  token, because `kid` derives from the material.
- **`var.domain_jwt_enforced` defaults to `false` in code** but is `true` as an
  HCP workspace variable in production. The repository default is not evidence
  enforcement is off; read the workspace.
- **HCP plan JSON carries sensitive variable values in plaintext.** Fetch it
  only through a jq filter, never save the raw output.

## Conventions

- **Admin/management email**: use `tyler@webbpulse.com` for all management
  addresses (DMARC reporting, contact forms).
- **No em dashes** in AWS resource names, descriptions or site copy.
- **No code comments** unless explicitly asked. Docstrings are required
  everywhere and should be concise.
- **Test markers** (`pytest.ini`): `unit`, `api`, `integration`, `auth`,
  `admin`. Run a category with `-m unit`.

## Documentation

- `docs/identity-cutover.md`: current identity state, the two pending steps
  (clear the legacy column, then close out), and the MFA, OAuth and passkey
  reference.
- `docs/migration/RETROSPECTIVE.md`: what the migrations changed, when they
  landed, and what is still open.
