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

# Every domain's routes in one process, on :8000 (docs at /docs)
uvicorn app.composition.app:app --reload

# Or one domain, exactly as its image runs it
PORT=8010 python -m app.entrypoints.content
```

```bash
# Tests (moto-backed, no database needed)
pytest tests/

# Linting
ruff check app tests
ruff format --check app tests
```

See `backend/README.md` for configuration, the data model, and the container images.

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

Parts of the stack come from `app.terraform.io/WebbPulse/platform-modules/aws`, the private registry copy of [WebbPulse/terraform-aws-platform-modules](https://github.com/WebbPulse/terraform-aws-platform-modules):

| Module | What it owns here |
| --- | --- |
| `staging-dns` | The `staging.webbpulse.com` child zone and its NS delegation in the parent zone; a no-op in production (`route53.tf`) |
| `http-api` | The HTTP API, `$default` stage, Lambda integration and permission, routes, access log group, custom domain and API mapping (`apigateway.tf`) |
| `staging-access-gate` | Cognito, the login Lambda, the signed-cookie key group, the viewer-request function, the origin-verify secret and the HTTP API authorizer (`staging_access_gate.tf`) |
| `identity` | The KMS signing key, its alias, the four identity tables (`credentials`, `refresh-tokens`, `login-attempts`, `identity-tokens`) and the two IAM grants the identity function needs on them (`identity.tf`) |

### Identity

`terraform/identity.tf` calls the `identity` platform module, which owns the whole
identity layer: the RSA_2048 signing key the access tokens are signed with, the
`alias/webbpulse-<env>-identity-signing` alias pointing at it, the four DynamoDB
tables the identity flows read and write, and the `identity-signing` and
`identity-tables` policies on the identity Lambda's role. The issuer, the
audience and the registrable domain are still derived in `identity.tf` and passed
in, because all three are close to irreversible and belong where they can be
reviewed.

The module's `identity_environment` output is merged **last** into the identity
function's environment in `lambda_domains.tf`, so `IDENTITY_ISSUER`,
`IDENTITY_AUDIENCE`, `IDENTITY_SIGNING_KEY_ARNS`, `IDENTITY_COOKIE_DOMAIN` and
`IDENTITY_RP_ID` come from the same place the resources do. The product strings
around it, the SES pair and the registration switch stay in `lambda_domains.tf`.

The four identity tables are **not** in `dynamodb.tf`. They moved into the module
with `moved` blocks; the physical names are unchanged because both modules build
`"<name_prefix>-<key>"` from the same `local.prefix`.

`http_api_id` is deliberately not passed, so the module creates no JWT
authorizer. The M0 spike in `identity_spike.tf` still owns the only JWT
authorizer on this API, and an HTTP API route takes one authorizer while the
staging access gate already occupies that slot on every route.

Rotating a signing key is two applies against the module's `signing_key_count`
and `active_signing_key` inputs, never a mutation of one key: `kid` is derived
from the key material, so rotating material behind one key id strands every
already-issued token.

The ACM certificates and their validation records (`acm.tf`) and the `www`, apex and `api` alias records (`route53.tf`) stay hand-written because a Terraform module has one `aws` provider and production writes DNS cross-account through the `aws.dns` alias. They point at module outputs.

Two of the registry modules do not fit this stack yet and their resources stay hand-written:

- `spa-frontend` (`frontend.tf`) applies its `cache_mode` to the `/index.html` SPA-shell behavior as well as the default behavior. This distribution serves the shell from the managed CachingOptimized policy while the default behavior uses legacy forwarded values, and the module has no input for that split, so adopting it would rewrite the live behavior.
- `github-actions-role` (`iam_github_actions.tf`) validates `policy_statements` with `coalesce(s.sid, "")`, which errors on any statement without a `sid`. None of the statements here carry one, and adding sids would change the rendered policy document.

### Transaction Search and the `aws/spans` log group

`terraform/transaction_search.tf` switches X-Ray trace storage to CloudWatch
Logs, which is what the X-Ray OTLP endpoint requires. It is account-wide for the
region rather than per environment, and removing the resources does not revert
it: reverting is an explicit change of `destination` back to `"XRay"`.

Standing it up in a new environment takes **two applies**. X-Ray creates the
`aws/spans` log group itself on the first span, and Terraform cannot create it
ahead of time because CloudWatch reserves the `aws/` prefix. So the import and
the log group resource are gated on `manage_spans_log_group`:

| Apply | `manage_spans_log_group` | What happens |
| --- | --- | --- |
| First | `false` (the default, leave it unset) | The resource policy, the trace segment destination and the `Default` indexing rule are created. `aws/spans` is untouched |
| Second, after the first span | `true` on the workspace | The existing `aws/spans` group is imported and its retention set to the platform's 7 days, replacing X-Ray's 30 day default |

Setting the variable before the group exists fails the plan on the import.
Staging adopted the group before the gate existed; a `moved` block migrates its
state onto the `for_each` address, so it plans no change.

### Staging access gate

Staging sits behind the shared `staging-access-gate` module (`app.terraform.io/WebbPulse/platform-modules/aws//modules/staging-access-gate`) when the workspace variables `staging_access_gate = true` and `staging_access_users = [<emails>]` are set. WebbPulse-Platform sets them on the staging workspace only; production never receives them, so its plan is a no-op.

With the gate on:

- Every visit to `https://www.staging.webbpulse.com` (or the apex) without a live session is redirected to a Cognito hosted UI. Only the invited addresses can sign in; each receives an invitation email with a temporary password. Sessions are CloudFront signed cookies scoped to `staging.webbpulse.com`.
- The frontend calls the API on the site origin, `https://www.staging.webbpulse.com/api/v1/...`, and CloudFront proxies `/api/*` to `api.staging.webbpulse.com` with an `x-origin-verify` header. The staging GitHub environment variable `API_BASE_URL` must therefore be `https://www.staging.webbpulse.com` (the Terraform output `frontend_api_base_url` says which value is right).
- The HTTP API's `execute-api` endpoint is disabled and every route uses the module's REQUEST authorizer, so `api.staging.webbpulse.com` answers only requests carrying the header. The backend deploy workflow's smoke test reads the header value from the SSM parameter `/webbpulse-staging/access-gate/origin-verify` at run time (masked, never printed).
- `/_auth/logout` ends a session. Sign-in problems: check the Cognito user pool in the `staging_access_gate_user_pool_id` output.

The apex to www redirect lives in `terraform/cloudfront_functions/app_handler.js.tftpl` and is shared by the plain `apex_redirect` CloudFront Function (production) and the gate's viewer-request function (staging).
