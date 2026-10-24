# WebbPulse

A full-stack personal portfolio and blog, served at
[portfolio.webbpulse.com](https://portfolio.webbpulse.com). Every section, projects, experience,
skills, blog and site copy, lives in typed content files under
`frontend/src/content/` and changes through a pull request.

**Stack:** FastAPI (Python 3.13) on AWS Lambda, React (TypeScript), DynamoDB,
Terraform. **License:** [PolyForm Strict License 1.0.0](LICENSE).

## Structure

```
backend/    The public FastAPI app serving the live figures
frontend/   React + Vite + Tailwind CSS
terraform/  AWS infrastructure
docs/       The migration retrospective, the resume PDF
```

## Development

Prerequisites: Python 3.13, Node 22, Docker for DynamoDB Local, and an AWS login
for the shared CodeArtifact packages.

### Backend

```bash
cd backend
docker compose up -d                        # DynamoDB Local on :8001
export DYNAMODB_ENDPOINT_URL=http://localhost:8001
python scripts/create_local_tables.py

uvicorn app.common.composition.app:app --reload    # every route on :8000, docs at /docs
PORT=8013 python -m app.domains.public.entrypoint  # the way the image runs it

pytest tests/                               # moto-backed, no AWS or database
ruff check app tests
ruff format --check app tests
```

See `backend/README.md` for configuration, the data model and the container
image.

### Frontend

```bash
cd frontend
npm install            # needs a CodeArtifact token first, see frontend/README.md
npm run dev:local      # :5173, proxies /api to localhost:8000
npm run build
npm run lint
npm run test:run
```

### End to end tests

The suite in `backend/e2e/` runs against a whole stack rather than a process, so
it needs a backend, a built frontend and a DynamoDB endpoint all answering. Two
workflows run it: `e2e (staging)` after a deploy, against the deployed
environment, and `e2e (local)` on a pull request, against a stack the runner
builds from the commit under test. The local check is advisory, so it reports a
result without gating the merge.

Both runs are anonymous and read only. Nothing on the site signs in, so there
are no e2e login users.

To run it locally, start DynamoDB Local and the backend as above, build and
serve the frontend, then point the suite at both:

```bash
cd backend
export E2E_ENVIRONMENT=local E2E_READ_ONLY=true E2E_AWS_REGION=us-west-2
export E2E_API_BASE_URL=http://127.0.0.1:8000 E2E_WEB_BASE_URL=http://127.0.0.1:5173
export E2E_RUN_ID=local E2E_BROWSER=chromium E2E_HEADLESS=true
uv run python -m pytest e2e -o addopts=
```

### Shared package versions

The shared `webbpulse` Python distribution and the `@webbpulse/*` npm packages
float to the newest compatible release at build time rather than sitting on an
exact pin. The version recorded in `backend/pyproject.toml` and
`frontend/package.json` is a floor, the minimum the code needs, with the major
bound as the ceiling. An exact pin is the explicit exception, used only to hold
a known good version while something is investigated. Every build log prints the
versions it resolved, so the image and the bundle each say what they were built
against.

## Architecture

One FastAPI app, the `public` domain, runs as the Lambda
`webbpulse-<env>-public`, built as a container image from `backend/Dockerfile`.
It serves `/`, `/health` and the live figures at `/api/v1/public/figures`.
There is no Lambda handler and no Mangum: the Lambda Web Adapter runs ahead of
the process and turns each invoke into an HTTP request against
`127.0.0.1:8080`, so the same image runs on Lambda and under `docker run`.

API Gateway routes with explicit route keys and no `$default`, so an unmatched
path is a gateway 404 rather than a fall-through. CORS is owned by the gateway,
not the functions: with only explicit method keys, an `OPTIONS` preflight
matches no route and gets a 404 with no CORS headers, so `module "api"` sets
`cors_configuration`.

DynamoDB holds one table, `webbpulse-<env>-public-cache`, where the figures are
cached with a TTL.

## Infrastructure

`terraform/` is applied by the WebbPulse control plane at `terraform.webbpulse.com`:
workspace `WebbPulse-Portfolio` tracks `main` (production, account 036807648992) and
`WebbPulse-Portfolio-staging` tracks `staging` (account 621554169154). Both are
`us-west-2`. There is no backend block: the plane's runner writes an S3 backend per
run, and AWS credentials come from the workspace's run role. `required_version` is a
range that admits both workspaces' exact engine versions.
Terraform never ships application code: functions are created with a placeholder
and `ignore_changes` on the code attributes, and CI updates the code.

### Branching

```
feature/* ──PR──▶ staging ──PR──▶ main
```

Branch new work from `staging` and PR into `staging`. Releasing is a PR from
`staging` into `main`, and that PR is the release boundary. Hotfixes branch from
`main`, PR into `main`, and are immediately back-merged into `staging`.

A staging branch does not imply staging infrastructure: `staging_profile` is
`none`, `reduced` or `full`. With `none` the workspace refuses to plan and
provisions nothing. `reduced` provisions Lambda, DynamoDB, the HTTP API and
S3/CloudFront on default AWS hostnames; `full` adds the custom domains.

### Shared platform modules

Parts of the stack come from `terraform.webbpulse.com/WebbPulse/platform-modules/aws`:

| Module | What it owns here |
| --- | --- |
| `staging-dns` | The `staging.portfolio.webbpulse.com` child zone and its NS delegation; a no-op in production (`route53.tf`) |
| `http-api` | The HTTP API, `$default` stage, integrations, routes, access log group, custom domain (`apigateway.tf`) |
| `staging-access-gate` | Cognito, the login Lambda, signed-cookie key group, viewer-request function, origin-verify secret, HTTP API authorizer (`staging_access_gate.tf`) |
| `ecr-repository` | The public image repository (`ecr.tf`) |

The ACM certificates (`acm.tf`) and the site and `api` alias records
(`route53.tf`) stay hand-written, because a module has one `aws` provider and
production writes DNS cross-account through the `aws.dns` alias.

`spa-frontend` and `github-actions-role` do not fit this stack and their
resources stay hand-written. `spa-frontend` applies its `cache_mode` to the
`/index.html` behavior as well as the default one, and this distribution splits
those. `github-actions-role` validates `policy_statements` with
`coalesce(s.sid, "")`, which errors on any statement without a `sid`, and none
here carry one.

### Transaction Search and the `aws/spans` log group

`transaction_search.tf` switches X-Ray trace storage to CloudWatch Logs, which
the X-Ray OTLP endpoint requires. It is account-wide for the region, and
removing the resources does not revert it: reverting is an explicit change of
`destination` back to `"XRay"`.

Standing it up takes **two applies**, because X-Ray creates `aws/spans` itself
on the first span and CloudWatch reserves the `aws/` prefix so Terraform cannot
pre-create it. Leave `manage_spans_log_group` unset for the first apply; set it
`true` after the first span so the existing group is imported and its retention
set to 7 days. Setting it before the group exists fails the plan on the import.

### Staging access gate

Staging sits behind the `staging-access-gate` module when `staging_access_gate`
and `staging_access_users` are set on the workspace. Production never receives
them, so its plan is a no-op.

- Any visit without a live session is redirected to a Cognito hosted UI. Only
  invited addresses can sign in. Sessions are CloudFront signed cookies scoped
  to `staging.portfolio.webbpulse.com`.
- The frontend calls the API on the site origin and CloudFront proxies `/api/*`
  to `api.staging.portfolio.webbpulse.com` with an `x-origin-verify` header, so
  staging's `API_BASE_URL` must be `https://staging.portfolio.webbpulse.com`. The Terraform
  output `frontend_api_base_url` says which value is right.
- The HTTP API's `execute-api` endpoint is disabled and every route uses the
  module's REQUEST authorizer. The deploy workflow reads the header value from
  the SSM parameter `/webbpulse-staging/access-gate/origin-verify` at run time,
  masked.
- `/_auth/logout` ends a session. For sign-in problems check the pool named by
  the `staging_access_gate_user_pool_id` output.

### Company site

The webbpulse.com company site moved to
[WebbPulse-Site](https://github.com/WebbPulse/WebbPulse-Site). Its resources were
forgotten here with `removed` blocks in `terraform/company_site_removed.tf`, not
destroyed, and are now managed by that repo's workspaces.

## Documentation

- `docs/migration/RETROSPECTIVE.md`: what the per-domain and identity migrations
  changed, when they landed, and what is still open.
