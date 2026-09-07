# WebbPulse

A full-stack personal portfolio and blog. Every section — projects, experience, skills, blog, and site copy — is driven from the API through an admin panel rather than hardcoded.

**Stack:** FastAPI (Python 3.13) on AWS Lambda · React (TypeScript) · DynamoDB · AWS (Terraform)

**License:** MIT

---

## Structure

```
backend/    FastAPI app, DynamoDB repositories, Lambda handler
frontend/   React + Vite + Tailwind CSS
terraform/  AWS infrastructure
docs/        Static assets (resume, etc.)
```

---

## Development

**Prerequisites:** Python 3.13, Node 18+, Docker (for DynamoDB Local)

### Backend

```bash
cd backend
docker compose up -d              # start DynamoDB Local on :8001
export DYNAMODB_ENDPOINT_URL=http://localhost:8001
python scripts/create_local_tables.py
uvicorn app.main:app --reload     # http://localhost:8000 (docs at /docs)
```

```bash
# Tests (moto-backed, no database needed)
pytest tests/

# Linting
flake8 app/ tests/ --max-line-length=88 --extend-ignore=E203,W503
black --check app/ tests/ && isort --check-only app/ tests/
```

See `backend/README.md` for configuration, the data model, and the Lambda build.

### Frontend

```bash
cd frontend
npm install
npm run dev:local     # port 5173, proxies /api to localhost:8000
npm run build
npm run lint
npm run test:run
```

---

## Infrastructure

`terraform/` is applied by HCP Terraform: the `WebbPulse-Portfolio` workspace tracks `main` (production) and `WebbPulse-Portfolio-staging` tracks `staging`. Work lands on `staging` first, then a PR from `staging` into `main`.

### Shared platform modules

Most of the stack comes from `app.terraform.io/WebbPulse/platform-modules/aws`, the private registry copy of [WebbPulse/terraform-aws-platform-modules](https://github.com/WebbPulse/terraform-aws-platform-modules):

| Module | What it owns here |
| --- | --- |
| `github-actions-role` | The OIDC provider, the deploy role and its inline `deploy-permissions` policy (`iam_github_actions.tf`) |
| `staging-dns` | The `staging.webbpulse.com` child zone and its NS delegation in the parent zone; a no-op in production (`route53.tf`) |
| `http-api` | The HTTP API, `$default` stage, Lambda integration and permission, routes, access log group, custom domain and API mapping (`apigateway.tf`) |
| `spa-frontend` | The frontend bucket, its public access block and policy, the origin access control and the CloudFront distribution, including all staging access gate wiring (`frontend.tf`) |
| `staging-access-gate` | Cognito, the login Lambda, the signed-cookie key group, the viewer-request function, the origin-verify secret and the HTTP API authorizer (`staging_access_gate.tf`) |

Four things stay hand-written in this repository because a Terraform module has one `aws` provider and production writes DNS cross-account through the `aws.dns` alias: the ACM certificates and their validation records (`acm.tf`), and the `www`, apex and `api` alias records (`route53.tf`). They point at module outputs.

### Staging access gate

Staging sits behind the shared `staging-access-gate` module (`app.terraform.io/WebbPulse/platform-modules/aws//modules/staging-access-gate`) when the workspace variables `staging_access_gate = true` and `staging_access_users = [<emails>]` are set. WebbPulse-Platform sets them on the staging workspace only; production never receives them, so its plan is a no-op.

With the gate on:

- Every visit to `https://www.staging.webbpulse.com` (or the apex) without a live session is redirected to a Cognito hosted UI. Only the invited addresses can sign in; each receives an invitation email with a temporary password. Sessions are CloudFront signed cookies scoped to `staging.webbpulse.com`.
- The frontend calls the API on the site origin, `https://www.staging.webbpulse.com/api/v1/...`, and CloudFront proxies `/api/*` to `api.staging.webbpulse.com` with an `x-origin-verify` header. The staging GitHub environment variable `API_BASE_URL` must therefore be `https://www.staging.webbpulse.com` (the Terraform output `frontend_api_base_url` says which value is right).
- The HTTP API's `execute-api` endpoint is disabled and every route uses the module's REQUEST authorizer, so `api.staging.webbpulse.com` answers only requests carrying the header. The backend deploy workflow's smoke test reads the header value from the SSM parameter `/webbpulse-staging/access-gate/origin-verify` at run time (masked, never printed).
- `/_auth/logout` ends a session. Sign-in problems: check the Cognito user pool in the `staging_access_gate_user_pool_id` output.

The apex to www redirect lives in `terraform/cloudfront_functions/app_handler.js.tftpl` and is shared by the plain `apex_redirect` CloudFront Function (production) and the gate's viewer-request function (staging).
