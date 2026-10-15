# CLAUDE.md

Guidance for Claude Code (claude.ai/code) when working in this repository.

## Project Overview

WebbPulse is a personal portfolio website with a blog. It is a
monorepo with a React/TypeScript frontend and one FastAPI/Python Lambda that
serves the live public figures.

## Commands

### Frontend (`frontend/`)

```bash
npm run dev:local        # Dev server on 5173 (proxies /api to localhost:8000)
npm run dev:remote-api   # Dev server against https://api.portfolio.webbpulse.com/api/v1
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

### Company site (`site/`)

The static webbpulse.com landing page: Vite, React and TypeScript on
`@webbpulse/tsconfig` and `@webbpulse/eslint-config`, with no backend. `npm run
build` prerenders the page and drops the client bundle, so `dist/` is HTML plus
static files. `npm run dev` serves it on 5174; `lint`, `format:check`,
`test:run` and `build` match `frontend/`, and `ci.yml` runs a path-scoped `Site`
job on `site/**`. `deploy-site.yml` publishes it; hosting is
`terraform/company_site.tf`.

### Backend (`backend/`)

```bash
docker compose up -d
export DYNAMODB_ENDPOINT_URL=http://localhost:8001
python scripts/create_local_tables.py

# Every route in one process (root A)
uvicorn app.common.composition.app:app --reload

# The public domain exactly as the image runs it (root B; the Dockerfile CMD is
# `python -m app.domains.${DOMAIN}.entrypoint`). run_uvicorn binds AWS_LWA_PORT,
# then PORT, then 8080
PORT=8013 python -m app.domains.public.entrypoint

# The real image under the Lambda Web Adapter. Needs a CodeArtifact token; see
# backend/README.md
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

- **Pages**: `/` (portfolio), `/blog`, `/blog/:slug`, `/privacy`. Any other
  path, `/admin` included, renders the 404 page. There is no admin panel and no
  sign-in in the frontend
- **Public content**: every public page reads `src/content/`, typed data files
  plus markdown (`blog/*.md` posts, `work/<slug>.md` case studies) loaded at
  build time with `import.meta.glob`. Edit content through a PR; public routes
  make no `/api/v1` content calls, and `SITE_CONTENT_DEFAULTS` parity no longer
  applies to the frontend
- **Prerender**: `npm run build` also builds `src/entry-server.tsx` for SSR and
  runs `scripts/prerender.js`, which writes `dist/<route>/index.html` for `/`,
  `/blog`, `/privacy`, every `/work/<slug>` and published post, plus
  `dist/404.html`, `dist/sitemap.xml` and `dist/robots.txt` (CloudFront does
  not route `/robots.txt` to the backend), each with head tags from
  `useDocumentMeta`. The client bundle stays: `main.tsx` hydrates when the
  root's `data-prerendered` path matches the URL and renders fresh otherwise.
  Browser-only values (theme, reduced motion, platform) go through
  `useSyncExternalStore` with a server snapshot so hydration matches. The
  `spa-frontend` `viewer_request_function` maps `/work/x` to
  `/work/x/index.html`; with the staging gate it runs inside the gate's function
- **Code splitting**: the home page is the main chunk. The blog, case study and
  privacy pages are `lazyPage` chunks in `src/routing/pages.ts`; `main.tsx`
  preloads the current route's chunk before hydrating and the prerender loads
  them all first. The command menu loads on first open. Case study bodies sit
  in the case study chunk (`content/caseStudyBodies.ts`); the main bundle reads
  `?raw&frontmatter` imports, which `build/markdownFrontmatter.ts` cuts to the
  frontmatter plus `has_write_up`
- **Scroll reveal**: `useInViewReveal` leaves content visible in the
  prerendered HTML and only hides below-the-fold elements after hydration when
  motion is allowed
- **API layer**: `src/services/api.ts` (`apiService`) holds only the anonymous
  `getPublicFigures()` read. The transport is `@webbpulse/api-client` and
  startup configuration is `@webbpulse/config`. That client rejects on a
  non-2xx, so `ApiService` adapts it back into Portfolio's own `{ data, error }`
  envelope. The content types stay in `api.ts` because `src/content/types.ts`
  imports them
- **Shared packages**: `@webbpulse/api-client`, `config`, `tsconfig` and
  `eslint-config` resolve from CodeArtifact through `frontend/.npmrc`. Run
  `aws codeartifact login` before installing; see `frontend/README.md`
- **Dev proxy**: Vite proxies `/api/*` to `http://localhost:8000` in local dev; a
  production build reads `VITE_API_BASE_URL` and falls back to
  `https://api.portfolio.webbpulse.com/api/v1`

### Backend

- **Runtime**: one FastAPI app, the `public` domain, as the Lambda
  `webbpulse-<env>-public` (Python 3.13, arm64) built as a container image from
  `backend/Dockerfile`. There is no Lambda handler and no Mangum: the Lambda Web
  Adapter runs ahead of the process and turns each invoke into an HTTP request
  against `127.0.0.1:8080`, so the same image runs on Lambda and under `docker
  run`. The domain registry in `wiring.py` keeps the shared
  `webbpulse.composition` shape, so another domain would be one more row and
  entrypoint
- **Routes**: `GET /`, `GET /health` (reads the cache table, 503 on failure)
  and `GET /api/v1/public/figures`. API Gateway routes with explicit route keys
  and no `$default`: an unmatched path is a gateway 404, not a fall-through.
  `tests/entrypoints/test_gateway_routes.py` keeps the key set and the served
  paths in agreement, in both directions. **CORS is owned by API Gateway, not by
  the function**: with only explicit method keys and no `$default`, an `OPTIONS`
  preflight matches no route and gets a gateway 404 with no CORS headers, so
  `module "api"` sets `cors_configuration` from `local.cors_origins`. The
  function's own `CORSMiddleware` still runs and is configured to match
- **No sign in**: there are no auth routes, no admin, no users and no tokens.
  The function reads no secret and has no Secrets Manager grant
- **Database**: one DynamoDB table, `webbpulse-<env>-public-cache` (string `pk`,
  TTL `ttl`), holding the computed figures and their refresh lease
- **Config**: `DYNAMODB_TABLE_PREFIX`, `ENVIRONMENT`, `CORS_ORIGINS`,
  `LOG_LEVEL`; `DYNAMODB_ENDPOINT_URL` points at a local DynamoDB
- **Sitemap and robots**: the frontend prerender writes both; the backend
  serves neither
- **Rate limiting**: API Gateway stage throttling (burst 200, rate 100). There
  is no in-process limiter
- **Observability**: OpenTelemetry through `webbpulse.otel`, X-Ray active
  tracing, and 7-day CloudWatch log groups. Logging is `webbpulse.logging`'s
  JSON formatter with `request_id` merged onto every line from
  `webbpulse.log_context`. aws-lambda-powertools is gone: its correlation is a
  handler decorator and there is no handler under the Web Adapter. No custom
  metrics yet

### Key files

| File | Purpose |
|---|---|
| `backend/app/common/composition/wiring.py` | The domain registry and `build_domain_app` |
| `backend/app/common/composition/app.py` | Root A: every router on one app. Nothing deploys it |
| `backend/app/domains/public/entrypoint.py` | Root B: the module the deployed function runs |
| `backend/app/domains/public/figures.py` | The figure sources, the cache and the refresh lease |
| `backend/Dockerfile` | Builds the image; `DOMAIN` selects the entrypoint and, through a per-domain final stage, the adapter readiness protocol |
| `backend/app/common/db/tables.py` | Canonical table definitions |
| `backend/tests/fixtures/route_contract.json` | The published contract: 3 routes |
| `backend/tests/entrypoints/test_gateway_routes.py` | Keeps route keys and served paths in agreement |
| `terraform/dynamodb.tf` | Table map |
| `terraform/lambda_domains.tf` | The public function, role and environment |
| `terraform/apigateway.tf` | HTTP API and routes |
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
| `.github/workflows/deploy-backend.yml` | push to `main`/`staging`, paths `backend/**` minus tests, e2e, scripts and docs | A thin caller of the org `lambda-domains-deploy.yml@v3`: it builds the image through `container-image.yml@v3` (an existing tag is reused, not rebuilt), points the function at its digest through `lambda-image-deploy.yml@v3`, and invoke-smoke-tests it on `GET /health`; the e2e suite verifies the live gateway |
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
variables are invisible there. `deploy-backend.yml` passes it to the shared
workflow as `staging-enabled-variable`; the backend build and deploy have no
other gate.

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

### Terraform configuration

Each value lives in exactly one place.

| Where | What |
| --- | --- |
| `terraform/env/<environment>.tfvars`, committed | Non-secret config: `bootstrap_image_tag` and `manage_spans_log_group`. WebbPulse-Platform loads the file on every plan through the workspace's `TF_CLI_ARGS_plan` env var. |
| HCP workspace variables pushed by WebbPulse-Platform | `environment`, `staging_profile`, `route53_zone_id`, `route53_write_role_arn`, `route53_read_role_arn` (assumed instead of the writer when the control plane exports `webbpulse_run_phase=plan`), the staging gate variables and the cloud identity env vars. Never repeat these in a tfvars file. |
| `webbpulse-<env>/app` Secrets Manager JSON secret | Only the Terraform-generated `SECRET_KEY` and `mfa_master_key`, which nothing reads now. Operator keys go in with `webbpulse-config --prefix webbpulse-<env> secret set <KEY>` (`json_preserve_unmanaged`). |
| `/webbpulse-<env>/config` SSM String parameter | Private non-secret config as a JSON object, owned by an operator and read through `operator-config`. Nothing reads a key from it now. |

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
- **HCP plan JSON carries sensitive variable values in plaintext.** Fetch it
  only through a jq filter, never save the raw output.

## Conventions

- **Admin/management email**: use `tyler@webbpulse.com` for all management
  addresses (DMARC reporting, contact forms).
- **No em dashes** in AWS resource names, descriptions or site copy.
- **No code comments** unless explicitly asked. Docstrings are required
  everywhere and should be concise.
- **Test markers** (`pytest.ini`): `unit`, `api`, `integration`. Run a
  category with `-m unit`.

## Documentation

- `docs/migration/RETROSPECTIVE.md`: what the migrations changed, when they
  landed, and what is still open.
