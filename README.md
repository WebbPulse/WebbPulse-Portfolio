# WebbPulse

A full-stack personal portfolio and blog. Every section, projects, experience,
skills, blog and site copy, is driven from the API through an admin panel rather
than hardcoded.

**Stack:** FastAPI (Python 3.13) on AWS Lambda, React (TypeScript), DynamoDB,
Terraform. **License:** MIT.

## Structure

```
backend/    Four per-domain FastAPI apps, DynamoDB repositories
frontend/   React + Vite + Tailwind CSS
terraform/  AWS infrastructure
docs/       The identity runbook, the migration retrospective, the resume PDF
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

uvicorn app.common.composition.app:app --reload    # all 44 routes on :8000, docs at /docs
PORT=8010 python -m app.domains.content.entrypoint # one domain, the way its image runs it

pytest tests/                               # moto-backed, no AWS or database
ruff check app tests
ruff format --check app tests
```

See `backend/README.md` for configuration, the data model and the container
images.

### Frontend

```bash
cd frontend
npm install            # needs a CodeArtifact token first, see frontend/README.md
npm run dev:local      # :5173, proxies /api to localhost:8000
npm run build
npm run lint
npm run test:run
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

Four FastAPI apps, one per domain (`content`, `resume`, `identity`, `public`),
each its own Lambda `webbpulse-<env>-<domain>` built as a container image from
one `backend/Dockerfile`. There is no Lambda handler and no Mangum: the Lambda
Web Adapter runs ahead of the process and turns each invoke into an HTTP request
against `127.0.0.1:8080`, so the same image runs on Lambda and under
`docker run`.

API Gateway routes with explicit route keys and no `$default`, so an unmatched
path is a gateway 404 rather than a fall-through. CORS is owned by the gateway,
not the functions: with only explicit method keys, an `OPTIONS` preflight
matches no route and gets a 404 with no CORS headers, so `module "api"` sets
`cors_configuration`.

DynamoDB holds one table per entity, `webbpulse-<env>-<entity>`. Integer ids
come from counter items in `meta`, and uniqueness is enforced with lookup items
inside `TransactWriteItems`.

## Infrastructure

`terraform/` is applied by HCP Terraform in org `WebbPulse`: workspace
`WebbPulse-Portfolio` tracks `main` (production, account 036807648992) and
`WebbPulse-Portfolio-staging` tracks `staging` (account 621554169154). Both are
`us-west-2`. AWS credentials come from TFC dynamic provider credentials.
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

Parts of the stack come from `app.terraform.io/WebbPulse/platform-modules/aws`:

| Module | What it owns here |
| --- | --- |
| `staging-dns` | The `staging.webbpulse.com` child zone and its NS delegation; a no-op in production (`route53.tf`) |
| `http-api` | The HTTP API, `$default` stage, integrations, routes, access log group, custom domain (`apigateway.tf`) |
| `staging-access-gate` | Cognito, the login Lambda, signed-cookie key group, viewer-request function, origin-verify secret, HTTP API authorizer (`staging_access_gate.tf`) |
| `identity` | The KMS signing key and alias, the identity tables, and the two IAM grants the identity function needs (`identity.tf`) |
| `ecr-repository` | The four domain image repositories (`ecr.tf`) |

The ACM certificates (`acm.tf`) and the `www`, apex and `api` alias records
(`route53.tf`) stay hand-written, because a module has one `aws` provider and
production writes DNS cross-account through the `aws.dns` alias.

`spa-frontend` and `github-actions-role` do not fit this stack and their
resources stay hand-written. `spa-frontend` applies its `cache_mode` to the
`/index.html` behavior as well as the default one, and this distribution splits
those. `github-actions-role` validates `policy_statements` with
`coalesce(s.sid, "")`, which errors on any statement without a `sid`, and none
here carry one.

### Identity

`terraform/identity.tf` calls the `identity` module, which owns the signing key,
its `alias/webbpulse-<env>-identity-signing` alias, the identity tables and the
`identity-signing` and `identity-tables` policies. The issuer, audience and
registrable domain are derived in `identity.tf` and passed in, because all three
are close to irreversible.

The module's `identity_environment` output is merged **last** into the identity
function's environment in `lambda_domains.tf`, so `IDENTITY_ISSUER`,
`IDENTITY_AUDIENCE`, `IDENTITY_SIGNING_KEY_ARNS`, `IDENTITY_COOKIE_DOMAIN` and
`IDENTITY_RP_ID` come from the same place the resources do.

`http_api_id` is deliberately not passed, so the module creates no JWT
authorizer: a route takes exactly one authorizer and the staging access gate
already occupies that slot.

Rotating a signing key is two applies against `signing_key_count` and
`active_signing_key`, never a mutation of one key. `kid` is derived from the key
material, so rotating material behind one key id strands every issued token.

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
  to `staging.webbpulse.com`.
- The frontend calls the API on the site origin and CloudFront proxies `/api/*`
  to `api.staging.webbpulse.com` with an `x-origin-verify` header, so staging's
  `API_BASE_URL` must be `https://www.staging.webbpulse.com`. The Terraform
  output `frontend_api_base_url` says which value is right.
- The HTTP API's `execute-api` endpoint is disabled and every route uses the
  module's REQUEST authorizer. The deploy workflow reads the header value from
  the SSM parameter `/webbpulse-staging/access-gate/origin-verify` at run time,
  masked.
- `/_auth/logout` ends a session. For sign-in problems check the pool named by
  the `staging_access_gate_user_pool_id` output.

The apex to www redirect lives in `cloudfront_functions/app_handler.js.tftpl`
and is shared by production's `apex_redirect` function and the gate's
viewer-request function.

## Documentation

- `docs/identity-cutover.md`: current identity state, the two pending steps, and
  the reference for MFA, OAuth and passkeys.
- `docs/migration/RETROSPECTIVE.md`: what the per-domain and identity migrations
  changed, when they landed, and what is still open.
