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
# Start PostgreSQL locally
docker-compose up -d

# Run the server
uvicorn app.main:app --reload

# Tests
pytest tests/                                      # All tests
pytest tests/test_name.py::test_function_name -v   # Single test
python run_tests.py all                            # All tests
python run_tests.py unit|api|integration|auth      # By category
python run_tests.py coverage                       # With HTML coverage report
python run_tests.py lint                           # Flake8 + Black checks
python run_tests.py format                         # Black + isort formatting

# Database migrations
alembic revision --autogenerate -m "description"
alembic upgrade head
```

## Architecture

### Frontend

- **Pages**: `/` (portfolio), `/blog`, `/blog/:slug`, `/admin`
- **API layer**: All API calls go through `src/services/api.ts` (`apiService`)
- **Dev proxy**: Vite proxies `/api/*` → `http://localhost:8000` in local dev; production uses `VITE_API_URL` env var

### Backend

- **REST API**: All routes under `/api/v1/` prefix. OpenAPI docs at `/docs`
- **Auth**: JWT tokens (python-jose/bcrypt). Users have an `is_admin` boolean flag
- **Database**: PostgreSQL via SQLAlchemy 2.0 ORM + Alembic migrations. Local dev uses Docker Compose
- **Rate limiting**: Custom middleware in `app/core/` with per-minute/hour/day limits

### Key files

| File | Purpose |
|---|---|
| `backend/app/main.py` | FastAPI app entrypoint — CORS, middleware, lifespan hooks |
| `backend/app/config.py` | Pydantic Settings — env vars including `DATABASE_URL` |
| `backend/app/database.py` | SQLAlchemy engine, session factory |
| `backend/app/api/v1/` | Route handlers by resource |
| `frontend/src/services/api.ts` | Centralized API client |
| `frontend/vite.config.ts` | Vite config with dev proxy |

### Deployment

- **Infrastructure**: `terraform/` — all AWS resources are defined in code, including the App Runner service (`aws_apprunner_service.backend`), ECR repo, RDS instance, VPC, S3/CloudFront frontend and the Route 53 zone. Nothing is clicked in the console
- **Terraform Cloud**: org `WebbPulse`, workspace `WebbPulse`, pinned in `terraform/versions.tf`. AWS credentials come from TFC dynamic provider credentials — no static keys
- **Region**: `us-west-2` (ACM certs for CloudFront are provisioned in `us-east-1` via a second provider alias)
- **CI/CD**: GitHub Actions

| Workflow | Trigger | What it does |
|---|---|---|
| `.github/workflows/test-backend.yml` | PR to `main`, paths `backend/**` | pytest against a Postgres service container |
| `.github/workflows/test-frontend.yml` | PR to `main`, paths `frontend/**` | Vitest + build |
| `.github/workflows/deploy-backend.yml` | push to `main`, paths `backend/**` | builds the image, pushes to ECR, waits for any active TFC run and for App Runner to reach `RUNNING`, then `aws apprunner start-deployment` |
| `.github/workflows/deploy-frontend.yml` | push to `main`, paths `frontend/**` | `npm run build`, waits for any active TFC run, `s3 sync --delete`, CloudFront invalidation |

Both deploy workflows run in the `production` GitHub Environment and assume `vars.AWS_DEPLOY_ROLE_ARN` via OIDC. The TFC-polling step exists to avoid `OPERATION_IN_PROGRESS` when Terraform and a deploy touch App Runner at the same time.

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

**Protection is convention only.** The WebbPulse org is on GitHub Free, so every repo — public and private — runs the same configuration: no branch protection, no rulesets. The real gate is Terraform Cloud manual apply on the production workspace: a merge cannot change AWS, only an apply can. CI runs on every PR but is not blocking — you have to read it.

### Current state, and what must happen before `staging` exists

There is no `staging` branch here yet, no `staging` GitHub Environment (only `production`), and no staging TFC workspace — `terraform/versions.tf` hardcodes the single workspace `WebbPulse`, and `var.environment` defaults to `production`. Every workflow above triggers on `main` only.

Deploy inputs currently live at **repository** scope, and repo-level variables are single-valued. A `staging` branch reading a repo-level `AWS_DEPLOY_ROLE_ARN` deploys straight into the production account. Move these to environment scope (`staging` / `production`) before creating the branch:

| Name | Kind | Used by |
|---|---|---|
| `AWS_DEPLOY_ROLE_ARN` | variable | both deploy workflows — OIDC role, e.g. `webbpulse-production-github-actions-deploy` |
| `ECR_REPOSITORY_NAME` | variable | `deploy-backend.yml` (terraform output, `webbpulse-production-backend`) |
| `APP_RUNNER_SERVICE_ARN` | variable | `deploy-backend.yml` |
| `FRONTEND_S3_BUCKET` | variable | `deploy-frontend.yml` (terraform output `frontend_bucket`) |
| `CLOUDFRONT_DISTRIBUTION_ID` | variable | `deploy-frontend.yml` (terraform output `cloudfront_distribution_id`) |
| `TFC_API_TOKEN` | secret | both deploy workflows — HCP Terraform token for workspace polling |

The workflows' `TFC_WORKSPACE: WebbPulse` env value is also production-specific and would need to vary per environment.

### A staging branch does not imply staging infrastructure

The project declares a staging profile — `none`, `reduced`, or `full`. The TFC staging workspace is always wired to the staging AWS account, but it may provision nothing. Check the profile before assuming there is a staging environment to deploy to; staging is never auto-provisioned to mirror production. This project has not declared one yet.

## Conventions

- **Admin/management email**: Use `tyler@webbpulse.com` for all management addresses (DMARC reporting, contact forms, etc.)

### Test markers (backend)

pytest.ini defines markers: `unit`, `api`, `integration`, `auth`, `admin`. Run a category with `-m unit` etc., or use `python run_tests.py <category>`.

