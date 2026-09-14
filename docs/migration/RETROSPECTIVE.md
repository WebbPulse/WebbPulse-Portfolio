# Migration retrospective

The Portfolio backend moved from one Postgres-backed FastAPI Lambda to four
per-domain container-image Lambdas on DynamoDB, and from a bearer-token admin
login to the shared identity stack. Both are done in production. This file is
the short record; the working documents that drove the work were deleted once
each was closed, and git history holds them.

## What changed

| Area | Before | After |
| --- | --- | --- |
| Runtime | one zip Lambda, `webbpulse-<env>-api` | four container-image Lambdas, `webbpulse-<env>-{content,resume,identity,public}`, Python 3.13, arm64 |
| Handler | Mangum adapter | no handler; Lambda Web Adapter fronts uvicorn on `127.0.0.1:8080` |
| Datastore | Postgres (RDS) | DynamoDB, one on-demand table per entity plus a shared `meta` table |
| Gateway | HTTP API with a `$default` catch-all | explicit route keys per domain, no `$default`; an unmatched path is a gateway 404 |
| CORS | in-process middleware only | owned by API Gateway `cors_configuration`; the app middleware still runs and matches |
| Admin auth | HS256 bearer token in `localStorage` | identity access token, httpOnly refresh cookie, gateway JWT authorizer |
| CI | `test-backend.yml` and `test-frontend.yml` | one `ci.yml` calling the org `python-ci.yml@v2` and `typescript-ci.yml@v2` |
| Image build | none | org `container-image.yml@v2` matrix, digest-pinned, then `lambda-image-deploy.yml@v2` |
| Observability | aws-lambda-powertools | OpenTelemetry via `webbpulse.otel`, `webbpulse.logging` JSON formatter, 7-day log groups |

## When it landed

| Date | Milestone |
| --- | --- |
| 2026-09-07 | Org `container-image.yml` v1.2.0 closed the five build gaps; v1.2.1 added the `environment` input |
| 2026-09-08 to 09-10 | The four route cuts on staging, in order: `public`, `resume`, `content`, `identity`. The monolith retired and its Python removed |
| 2026-09-11 02:25Z | Staging flipped to `AUTH_MODE=identity`; credential migration applied and the legacy `hashed_password` column cleared (PR 174) |
| 2026-09-11 07:13Z | Production apply one: 24 admin route keys added inert, `domain_jwt_enforced` absent. Plan was 24 add, 0 change, 0 destroy |
| 2026-09-11 07:17Z | Production apply two: `domain_jwt_enforced = true`. Plan was 24 add, 0 change, 24 destroy, a replacement rather than an in-place update because production is in `native` mode |
| 2026-09-11 07:20Z | Production frontend flipped to identity mode, run `34573737408`. The admin-write window between the two was 2 minutes 34 seconds |

Release merge PR 193, merge commit `b9db85c02cbcdf134d6de5e4c469dd2b24f7b00c`.

`var.domain_jwt_enforced` still defaults to `false` in `terraform/variables.tf`
and that is not evidence the flip is pending. Enforcement is an HCP workspace
variable on `WebbPulse-Portfolio` (`terraform` category, `hcl = true`, value
`true`), so the code default is expected to stay `false`. Read the workspace
through the HCP API to confirm live state, never the repository default.

## What is still open

### Identity runbook steps 11 and 12

Both are pending and both are described in full in `docs/identity-cutover.md`.
Step 11 clears the legacy `hashed_password` column in production and is a
one-way door: it waits on the owner making one admin write through the identity
path in a browser. Until it runs, the legacy column is intact and the
enforcement rollback still works in full. Step 12 is the close-out checklist.

### Container image workflow gaps

Five of the seven gaps recorded against the org reusable workflow are closed and
verified in `.github/workflows/deploy-backend.yml`. Two are not:

- **No existing-tag guard is passed.** The caller sets no `skip-if-tag-exists`,
  so it relies on the org workflow's default. The four ECR repositories are
  IMMUTABLE-tagged by the `ecr-repository` module default and the workflow tags
  only `sha-<full git sha>`, so a rerun of a green commit whose rebuild is not
  byte-reproducible still fails with `ImageTagAlreadyExistsException` for a
  reason unrelated to the commit under test.
- **The build has never run unguarded.** `BACKEND_IMAGE_BUILD_ENABLED` gates
  `resolve-env` and `BACKEND_IMAGE_DEPLOY_ENABLED` gates `deploy-images`. Both
  repository variables survive, so the workflow still does not run as a plain
  consequence of a push.

Two smaller notes that are correct as built but worth knowing:

- `codeartifact-domain-owner` is passed as a `with:` input to
  `container-image.yml` and as a `secrets:` entry to `python-ci.yml`,
  `typescript-ci.yml` and `spa-deploy.yml`. That divergence is intentional. Do
  not copy a `secrets:` line from one caller to the other.
- `amazon-ecr-login` leaves its `registry` output unset whenever more than one
  registry is passed, which `additional-ecr-registries` always causes. The org
  workflow derives the host from `sts get-caller-identity` plus `aws-region`
  instead, so an `aws-region` that disagrees with where the repository lives
  yields a URI that resolves to nothing rather than an error at push time.

### Other

- SES DKIM is `PENDING` and sending is sandbox-limited. Neither blocks the admin
  path. Leaving the sandbox is an owner-driven support case.
- The legacy surface is still mounted: `POST /api/v1/admin/login`,
  `app/domains/identity/router.py`, `BearerTokenStore` and `authMode.ts` are
  removed together in a later PR, once both environments have run on identity
  long enough. Keeping them is what leaves the frontend flip reversible.
