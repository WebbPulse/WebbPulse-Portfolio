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
docker-compose up -d
DYNAMODB_ENDPOINT_URL=<local dynamodb url> uvicorn app.main:app --reload

# Tests (moto-backed, no AWS or database needed)
pytest tests/                                      # All tests
pytest tests/test_name.py::test_function_name -v   # Single test

# Lint / format
flake8 app/ tests/ --max-line-length=88 --extend-ignore=E203,W503
black app/ tests/ && isort app/ tests/

# Build the Lambda deployment package (what CI ships)
bash scripts/build_lambda.sh                       # -> backend/dist/function.zip
```

## Architecture

### Frontend

- **Pages**: `/` (portfolio), `/blog`, `/blog/:slug`, `/admin`
- **API layer**: All API calls go through `src/services/api.ts` (`apiService`)
- **Dev proxy**: Vite proxies `/api/*` → `http://localhost:8000` in local dev; a production build reads `VITE_API_BASE_URL` (set by `deploy-frontend.yml` from the `API_BASE_URL` environment variable) and falls back to `https://api.webbpulse.com/api/v1`

### Backend

- **Runtime**: one FastAPI app on a single Lambda (`webbpulse-<env>-api`, Python 3.13, arm64) via Mangum, behind an API Gateway HTTP API (`ANY /{proxy+}`). Handler is `app.lambda_handler.handler`
- **REST API**: All routes under `/api/v1/` prefix. OpenAPI docs at `/docs`. Ids stay integers and list endpoints keep `skip`/`limit` so the frontend contract is unchanged
- **Auth**: JWT tokens (HS256, python-jose/bcrypt). Users have an `is_admin` boolean flag. The admin user is seeded from SSM on cold start
- **Database**: DynamoDB, one table per entity (`webbpulse-<env>-<entity>`: users, categories, posts, projects, experience, skills, education, certifications, site-content, meta). Integer ids come from counter items in `meta`; uniqueness (username, email, slug) is enforced with lookup items inside `TransactWriteItems`. `posts` has `published-index` and `category-index` GSIs
- **Config**: env vars `DYNAMODB_TABLE_PREFIX`, `SSM_PARAMETER_PREFIX` (secret key + admin credentials are read from SSM), `ENVIRONMENT`, `CORS_ORIGINS`, `SITE_URL`, `LOG_LEVEL`; `DYNAMODB_ENDPOINT_URL` points at a local DynamoDB
- **Rate limiting**: API Gateway stage throttling (burst 200, rate 100). There is no in-process limiter
- **Observability**: aws-lambda-powertools logger, X-Ray active tracing, 30-day CloudWatch log groups for the function and the HTTP API access log

### Key files

| File | Purpose |
|---|---|
| `backend/app/main.py` | FastAPI app entrypoint — CORS, middleware, lifespan hooks |
| `backend/app/lambda_handler.py` | Mangum adapter — the Lambda entrypoint |
| `backend/app/config.py` | Pydantic Settings — env vars and SSM-backed secrets |
| `backend/app/api/v1/` | Route handlers by resource |
| `backend/scripts/build_lambda.sh` | Builds `dist/function.zip` for Lambda |
| `terraform/dynamodb.tf` | Table map — attributes, GSIs, TTL, PITR per entity |
| `terraform/lambda.tf` | Function, execution role, artifact bucket, placeholder package |
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
| `.github/workflows/test-backend.yml` | PR to `main`/`staging`, paths `backend/**` | pytest on moto (no database service), flake8, black, isort |
| `.github/workflows/test-frontend.yml` | PR to `main`/`staging`, paths `frontend/**` | lint, format check, build, Vitest with coverage |
| `.github/workflows/deploy-backend.yml` | push to `main`/`staging`, paths `backend/**` | builds `function.zip`, uploads it to the artifact bucket as `backend/<sha>.zip`, waits for any active TFC run, `aws lambda update-function-code --publish`, then curls `/health` |
| `.github/workflows/deploy-frontend.yml` | push to `main`/`staging`, paths `frontend/**` | `npm run build` with `VITE_API_BASE_URL`, waits for any active TFC run, `s3 sync --delete`, CloudFront invalidation |

Deploy workflows pick the `production` or `staging` GitHub Environment from the branch and assume `vars.AWS_DEPLOY_ROLE_ARN` via OIDC. The TFC-polling step keeps a code deploy from racing a Terraform apply that is touching the same function.

Environment-scoped inputs each GitHub Environment must define:

| Name | Kind | Used by |
|---|---|---|
| `AWS_DEPLOY_ROLE_ARN` | variable | both deploy workflows — terraform role `webbpulse-<env>-github-actions-deploy` |
| `LAMBDA_FUNCTION_NAME` | variable | `deploy-backend.yml` (terraform output `lambda_function_name`) |
| `LAMBDA_ARTIFACT_BUCKET` | variable | `deploy-backend.yml` (terraform output `lambda_artifact_bucket`) |
| `API_BASE_URL` | variable | backend smoke test and the frontend build (terraform output `backend_url`, no trailing slash) |
| `FRONTEND_S3_BUCKET` | variable | `deploy-frontend.yml` (terraform output `frontend_bucket`) |
| `CLOUDFRONT_DISTRIBUTION_ID` | variable | `deploy-frontend.yml` (terraform output `cloudfront_distribution_id`) |
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

