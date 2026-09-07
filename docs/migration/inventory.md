# Migration inventory and proposed layout: WebbPulse-Portfolio

This is a read-only inventory. Nothing in this pull request changes application
code, Terraform, or workflows. It records what exists today, proposes a layout
for the split, and lists what has to change to get there.

The design decisions below are settled and are not re-argued here. The backend
stays Python and FastAPI, restructured into per-domain packages, each with its
own router, service, repository and schemas, and none of that code knows how it
is hosted. There are two composition roots: one FastAPI app that mounts every
domain for local work and tests, and one entrypoint per domain for deploys. The
deploy unit is an OCI image per domain running on Lambda behind the AWS Lambda
Web Adapter with uvicorn, so the identical image would run on Fargate or App
Runner. Zips and the S3 artifacts bucket go away, replaced by ECR repositories,
one per domain per environment, each with a lifecycle rule, so a staging push
can never overwrite the tag a production function resolves. API Gateway routes
by path prefix, the public API contract does not change, and the frontend needs
no edits. The cut is a strangler, with the monolith holding the catch-all until
the last domain moves. Shared code moves to two new organisation repositories, a
Python package and TypeScript packages, framework-neutral at the core with
FastAPI and Lambda specifics confined to small adapter sub-modules, published to
CodeArtifact. Reusable `workflow_call` workflows in an organisation `.github`
repository replace the per-application copies. CloudWatch log retention is 7
days everywhere. The repository layer is the seam for the data store, and
DynamoDB stays. The staging access gate keeps working for every domain function.
A cross-domain operation, if one is ever introduced, goes async via an event
rather than an in-process import.

Two account facts frame the rest of this document. **Shared services live in the
WebbPulse Platform AWS account**, a new account being vended now, and that is
where CodeArtifact and the shared base image repository go; nothing
workload-facing moves there. **Production runs in the member account
`036807648992`**, not in Management.

Observability is also settled. OpenTelemetry is the only instrumentation in the
shared Python package, with AWS native backends by default. So is rate
limiting, which is layered across the gateway, the shared Python package and an
opt-in CloudFront and WAF tier; it has its own section below because Portfolio
owns the reference implementation.

**Summary of the state today.** The backend is 2345 lines across 44 Python
files, 37 of them excluding the seven `__init__.py` files, under `backend/app/`,
serving 44 application routes plus 4 documentation routes from a single Lambda
function. The Terraform root is 944 lines across 18 files,
almost entirely registry module calls. There are four GitHub Actions workflows,
two of which share a 35-line block character for character.

## 1. Backend inventory

Every module under `backend/app`, with the line count as it stands on
`origin/staging` at commit c3a2390. The classification says where the code
should live after the split.

- **Framework-neutral** means it has no FastAPI and no Lambda import and can be
  lifted into the shared Python package as-is.
- **FastAPI adapter** means it is generic in intent but binds to FastAPI types
  (`APIRouter`, `Depends`, `HTTPException`), so it belongs in a FastAPI
  sub-module of the shared package.
- **Lambda adapter** means it binds to the Lambda runtime and belongs in a
  Lambda sub-module of the shared package.
- **App-specific** means it stays in this repository.

Proposed shared package distribution name: `webbpulse-service-core`, imported
as `webbpulse.core`. Adapter sub-modules are `webbpulse.fastapi` and
`webbpulse.aws.lambda_`. The split is deliberate: importing
`webbpulse.core.repository` must never pull FastAPI or Mangum into the process.

| Module | Lines | What it does | Classification | Proposed shared path |
|---|---|---|---|---|
| `app/main.py` | 73 | Builds the FastAPI app, mounts the v1 router and the SEO router, declares `/` and `/health`, adds three middlewares and CORS | App-specific | Becomes the all-domains composition root; the CORS and middleware wiring is extracted to a builder |
| `app/lambda_handler.py` | 14 | Mangum adapter plus the Powertools `inject_lambda_context` decorator | Lambda adapter, then deleted | Superseded by the Web Adapter. No Mangum in the target |
| `app/config.py` | 84 | pydantic-settings `Settings`, the `SECRET_FIELDS` tuple, `LOCALHOST_ORIGINS`, the CORS comma parser, and the `resolve_secrets` model validator that fills missing secrets and fails fast | Shareable with extraction | `webbpulse.core.settings.BaseServiceSettings` carries the secret resolution, the CORS parser and the localhost origins; the Portfolio-specific fields stay here as a subclass |
| `app/secrets.py` | 89 | Reads the single `APP_SECRETS_ARN` JSON secret from Secrets Manager, caches it in module scope, validates that it is a JSON object, `reset_cache()` for tests | Framework-neutral | `webbpulse.core.secrets` verbatim. Highest-value extraction in the repository |
| `app/core/security.py` | 76 | bcrypt hash and verify with the 72-byte truncation, `python-jose` JWT encode and decode, `HTTPBearer`, the `get_current_user` dependency, `require_admin` | Split | Password and JWT primitives to `webbpulse.core.auth`; `get_current_user`, `require_admin` and the `HTTPBearer` instance to `webbpulse.fastapi.auth`. The current file mixes both |
| `app/core/logging.py` | 5 | Constructs the Powertools `Logger` from settings | Lambda adapter | `webbpulse.aws.logging`. Trivial but imported everywhere, so it must move with the rest |
| `app/core/middleware.py` | 68 | `TrailingSlashMiddleware` (re-matches a path with the slash flipped), `SeedMiddleware` (calls the two seeders on every HTTP scope), `RequestLoggingMiddleware` (method, path, status, duration) | Mostly shareable | `webbpulse.fastapi.middleware` takes the trailing-slash and request-logging classes, which are raw ASGI and generic. `SeedMiddleware` is app-specific because the seeders it calls are |
| `app/core/admin.py` | 56 | Seeds or reconciles the admin user from settings on first request, guarded by a module flag | App-specific | Stays. The pattern generalises but the reconciliation rules are Portfolio's |
| `app/core/login_limiter.py` | 86 | DynamoDB-backed login brute-force limiter: `LOGIN_FAIL#<ip>` items in the meta table with a TTL, conditional `ADD` update, and `client_ip()`, which tries the Lambda `aws.event` request context first, then the leftmost `X-Forwarded-For` hop, then `request.client.host` | Shareable with extraction, and the reference implementation for the org-wide limiter | `webbpulse.core.rate_limit`. `client_ip()` reaches first into `request.scope["aws.event"]`, a Mangum artifact the Web Adapter does not set, so under the adapter it silently falls through to its second branch, the leftmost `X-Forwarded-For` hop, which is caller-controlled and spoofable. Both branches have to be replaced by the API Gateway request context the adapter forwards. Flagged as a behaviour change, not a move |
| `app/core/site_content.py` | 33 | Seeds the singleton site-content row on first request | App-specific | Stays with the content domain |
| `app/core/site_content_defaults.py` | 54 | The literal default hero, about and values copy | App-specific | Stays with the content domain. Pure Portfolio content |
| `app/db/repository.py` | 372 | The generic DynamoDB repository: integer ids from atomic counters, uniqueness lookup items enforced inside `TransactWriteItems`, soft and hard delete, paginated `list_all` scan, `get_many` batch get, `UniqueViolation`, plus the `PostRepository` subclass with `list_published` and `has_posts_in_category` | Framework-neutral, split | The `Repository` base class is `webbpulse.core.repository`, the single biggest extraction. `PostRepository` is app-specific and stays. This module is the data-store seam |
| `app/db/client.py` | 32 | `lru_cache` boto3 resource and client factories honouring `DYNAMODB_ENDPOINT_URL`, plus `reset()` for tests | Framework-neutral | `webbpulse.core.dynamo.client` |
| `app/db/serializer.py` | 58 | Encode and decode between Python and DynamoDB: `Decimal` to int or float, datetimes to fixed-width UTC ISO-8601, dates to `YYYY-MM-DD`, `None` dropped rather than stored | Framework-neutral | `webbpulse.core.dynamo.serializer` verbatim |
| `app/db/tables.py` | 86 | Table and GSI definitions, the `COUNTER#`, `UNIQUE#` and `LOGIN_FAIL#` prefixes, `table_name(prefix, entity)` | Split | The prefixes and `table_name` go to `webbpulse.core.dynamo.tables`; the Portfolio entity list and the two posts GSIs stay |
| `app/db/ordering.py` | 54 | In-memory sort helpers reproducing the old SQL orderings; `order_by` with a null-last key and stable multi-key sorting | Split | The generic `order_by` and `_key` go to `webbpulse.core.ordering`; the per-entity functions stay |
| `app/db/entities.py` | 49 | Declares one `Repository` instance per table with its unique fields, soft-delete flag and defaults; `BY_ENTITY` | App-specific | Stays, and is what each domain package narrows to its own tables |
| `app/api/v1/api.py` | 27 | Includes the eight endpoint routers under their prefixes and tags | App-specific | Replaced by per-domain router assembly |
| `app/api/v1/crud_router.py` | 80 | The `CrudConfig` dataclass and `build_crud_router`, a factory producing the five-route CRUD router used by five resources | FastAPI adapter | `webbpulse.fastapi.crud`. Generic over repository and schemas already; the only change is importing the auth dependencies from the shared package |
| `app/api/seo.py` | 58 | `/sitemap.xml` built from published posts and `/robots.txt`, both `include_in_schema=False` | App-specific | Stays with the public domain |
| `app/api/v1/endpoints/posts.py` | 202 | Twelve decorators covering posts and categories: public list, by-slug, by-category, admin list, create, update, delete, publish, plus category create, update and delete with the has-posts guard; slug generation via `python-slugify` | App-specific | Content domain |
| `app/api/v1/endpoints/admin.py` | 57 | The login route: limiter check, constant-time dummy hash for unknown users, failure recording, 429 with `Retry-After`, token mint | App-specific | Identity domain. The dummy-hash timing equaliser is worth keeping intact |
| `app/api/v1/endpoints/projects.py` | 37 | A CRUD router with `include_list=False` plus a custom list honouring `featured_only` and the site-content `project_sort_mode` | App-specific | Resume domain. Note the cross-table read of site content |
| `app/api/v1/endpoints/site_content.py` | 29 | Singleton get and admin update | App-specific | Content domain |
| `app/api/v1/endpoints/skills.py` | 20 | CRUD router only, limits raised to 100 and 200 | App-specific | Resume domain |
| `app/api/v1/endpoints/experience.py` | 18 | CRUD router only | App-specific | Resume domain |
| `app/api/v1/endpoints/education.py` | 18 | CRUD router only | App-specific | Resume domain |
| `app/api/v1/endpoints/certifications.py` | 23 | CRUD router only | App-specific | Resume domain |
| `app/schemas/*.py` | 487 total | Pydantic request and response models, ten modules plus the re-exporting `__init__` | App-specific | Split per domain. They are the public contract, so they move but do not change |
| `app/utils/__init__.py` | 0 | Empty | App-specific | Delete |
| `scripts/build_lambda.sh` | 49 | Builds the deterministic `dist/function.zip` for manylinux2014 aarch64 | App-specific | Deleted. Replaced by the image build |
| `scripts/create_local_tables.py` | 59 | Creates every table against DynamoDB Local | App-specific | Stays, useful for the all-domains root |
| `scripts/migrate_postgres_to_dynamo.py` | 211 | The one-time Postgres copy with `--dry-run`, `--verify` and `--replace` | App-specific, dead | The cutover completed in September 2026. Propose deleting it in its own PR rather than carrying it into the new layout |

### What the numbers say

Of roughly 2345 lines under `app`, about 700 are genuinely shareable: the
repository base class, the serializer, the DynamoDB client, the secrets loader,
the settings base, the CRUD router factory, two of the three middlewares, and
the auth primitives. That is the case for the shared package. The rest is
Portfolio's own contract and content.

### Duplication with CarModPicker: convergence, not extraction

This is the finding most likely to change the plan, so it is stated plainly.
**There is no copy-pasted code between the two backends.** They solve the same
problems and were written independently. CarModPicker's backend is about 24,090
lines against Portfolio's 2,345, and its abstractions run the other way on
nearly every axis. A shared package therefore cannot be created by lifting a
file out of one repository. Every module needs a winner picked and the loser's
call sites rewritten.

| Portfolio module | Lines | CarModPicker equivalent | Lines | Verdict |
|---|---|---|---|---|
| `app/secrets.py` | 89 | `app/core/secrets.py` | 50 | Parallel |
| `app/config.py` | 84 | `app/core/config.py` | 318 | Parallel |
| `app/core/security.py` | 76 | `app/api/dependencies/auth.py` | 197 | Parallel |
| `app/core/logging.py` | 5 | `app/core/logging.py`, `log_context.py` | 138 | Parallel, only the filename matches |
| `app/core/middleware.py` | 68 | `app/api/middleware/request_context.py` | 18 | Parallel, mostly no equivalent |
| `app/core/login_limiter.py` | 86 | `app/api/middleware/rate_limiter.py` | 282 | Parallel, different mechanism |
| `app/db/repository.py` | 372 | `app/db/dynamo/repository.py` | 507 | Parallel, deepest divergence |
| `app/db/client.py` | 32 | `app/db/dynamo/client.py` | 62 | Near-identical in intent, the closest pair in either repository |
| `app/db/serializer.py` | 58 | `app/db/dynamo/serialization.py` | 123 | Parallel |
| `app/db/tables.py` | 86 | `app/db/dynamo/tables.py` | 320 | Parallel |
| `app/db/ordering.py` | 54 | none | | No equivalent |
| `app/api/v1/crud_router.py` | 80 | `app/api/utils/base_dynamo_endpoint_router.py` | 159 | Parallel |
| `app/lambda_handler.py` | 14 | `app/lambda_handler.py` | 5 | Parallel |
| pagination, inline `skip`/`limit` | | `pagination_utils.py`, `cursor_pagination.py` | 175 | CarModPicker has shared helpers, Portfolio has none |
| error handling, inline `HTTPException` | | `error_handler.py`, `response_patterns.py`, `dynamo/errors.py` | 750 | CarModPicker has a shared layer, Portfolio has none |

The divergences that matter:

- **Ids and models.** Portfolio uses integer ids from a counter and passes plain
  dicts. CarModPicker uses UUIDv7 strings and is generic over pydantic models.
- **Pagination.** Portfolio is `skip`/`limit`, CarModPicker is cursor-based.
  Adopting CarModPicker's repository would change Portfolio's public API
  contract, which this migration has explicitly ruled out.
- **JWT library.** Portfolio uses `python-jose`, CarModPicker uses `PyJWT`, a
  deliberate documented migration guarded by a regression test. A shared
  security module cannot exist until one is chosen.
- **bcrypt major version.** 4.3.0 against 5.0.0. Portfolio truncates passwords
  to 72 bytes and uses default rounds; CarModPicker does not truncate and pins
  12 rounds.
- **Logging stack.** Five lines of Powertools against 138 lines of stdlib
  logging with a JSON formatter and a `ContextVar` request filter.
- **Target architecture.** Portfolio builds `aarch64`, CarModPicker `x86_64`.
  This constrains any shared build tooling and any shared base image.
- **Every shared dependency is version-skewed**, including FastAPI 0.115.12
  against 0.141.1.

Ordered by value against effort, the convergence sequence is: the secrets loader
and the settings secret resolution first, since they are the smallest, the most
similar, security-relevant, and both already assume the one-JSON-secret-per-service
convention; then `db/client`, which is nearly unified already; then error
handling and pagination, where adoption is one-directional because Portfolio has
nothing; then the repository, serializer and tables DSL, which is a project of
its own and a breaking change for Portfolio; and separately the build and test
tooling presets, which are genuine quick wins independent of everything else.

Also duplicated but not on the original list: the idempotent seed-on-startup
pattern, the local-table creation scripts, the dead Postgres migration scripts
in both repositories, the `pytest.ini` skeleton, and the DynamoDB Local
`docker-compose` service, which uses the same image and the same port 8001 in
both. A shared pytest base and a shared tsconfig base are the two cheapest
wins in the whole programme.

## 2. Proposed domain boundaries

Route counts below are exact, produced by walking `app.routes` on the built
FastAPI app and counting method-path pairs, excluding `HEAD` and `OPTIONS`.
The app exposes 48 such pairs: 44 application routes and 4 documentation routes
(`/docs`, `/docs/oauth2-redirect`, `/redoc`, `/openapi.json`).

Four domains. The split follows the tables, not the URL tree, which is why
categories stay with posts and why the singleton site content sits with content
rather than with the resume material.

| Domain | Endpoint modules absorbed | Routes | Tables read | Tables written | AWS services | Minimum IAM | Cross-domain calls |
|---|---|---|---|---|---|---|---|
| `content` | `posts.py` (12 decorators), `site_content.py` (2), plus `core/site_content.py` and `site_content_defaults.py` | 14 | posts, categories, site-content, users, meta | posts, categories, site-content, meta | DynamoDB, Secrets Manager, CloudWatch Logs, X-Ray | `dynamodb:GetItem,PutItem,UpdateItem,DeleteItem,Query,Scan,BatchGetItem,TransactWriteItems` on the posts, categories, site-content, users and meta tables plus the two posts GSIs; `secretsmanager:GetSecretValue` on the one app secret | Reads `users` to authorise admin writes. No call to another function |
| `resume` | `projects.py` (1 custom plus 4 CRUD), `experience.py` (5), `skills.py` (5), `education.py` (5), `certifications.py` (5) | 25 | projects, experience, skills, education, certifications, site-content, users, meta | projects, experience, skills, education, certifications, meta | DynamoDB, Secrets Manager, CloudWatch Logs, X-Ray | The same DynamoDB verbs on the five resume tables plus meta, read-only on site-content and users, and the app secret | Reads `site-content` for `project_sort_mode` and `users` for admin checks. Both are table reads, not function calls |
| `identity` | `admin.py` | 1 | users, meta | users, meta | DynamoDB, Secrets Manager, CloudWatch Logs, X-Ray | Read and write on users and meta (the meta write is the `LOGIN_FAIL#` limiter item); the app secret | None. It is the only writer of login-failure items |
| `public` | `api/seo.py` (2), plus `/` and `/health` from `main.py` | 4 | posts, site-content | none | DynamoDB, CloudWatch Logs, X-Ray | Read-only: `dynamodb:GetItem,Query,Scan` on posts and site-content plus the published GSI. **No Secrets Manager at all** | Reads posts for the sitemap. No writes anywhere |

Two things fall out of this table that are worth the owner's attention.

**`public` needs no secrets.** It has no authenticated route, so it should not
be granted `secretsmanager:GetSecretValue` and should not construct the JWT
signing key. The app now reads one JSON secret named by `APP_SECRETS_ARN`, and
`config.py` still ends in a module level `settings = Settings()`, whose
`resolve_secrets` validator raises whenever `SECRET_KEY`, `ADMIN_USERNAME`,
`ADMIN_PASSWORD` or `ADMIN_EMAIL` is still `None` after the blob is read.
Importing anything under `app/` therefore fails in a process with no secret and
no matching environment variables, so the `public` entrypoint needs a settings
variant that declares none of the four as required. That is a small change to
the settings base class, since the four field names are already a single
`SECRET_FIELDS` tuple, and it is the clearest single win in least-privilege
terms from the whole split.

**`identity` is one route but its own function.** Keeping it separate is
defensible on blast radius rather than on volume: it is the only component that
verifies passwords, mints tokens and writes the brute-force limiter items, and
isolating it means the signing key is reachable from exactly one function.
Alternatively it folds into `content`, which already reads `users`. The
four-function shape is recommended, with the caveat that a one-route function
carries its own cold starts and its own image.

**`public` is not read-free.** `/health` calls `database_status()`, which reads
the site-content singleton, and the sitemap queries the posts published GSI, so
`public` still needs DynamoDB read access even though it needs no secret. It
also inherits `SeedMiddleware` today, which writes both the admin user and the
site-content row on the first HTTP request in a process. That middleware must
not be wired into the `public` entrypoint, or the domain with the narrowest IAM
policy will fail on its first request trying to write two tables it should not
be able to touch. This is the single sharpest edge in the split.

**Every domain still reads `users`.** Admin authorisation is a table read, not a
service call, so no domain has to call another domain synchronously. That is
what makes the split safe. It does mean the `users` table is shared read state
across three of the four functions, so the repository layer for `users` is
shared code even though the table has a single writer.

**No cross-domain operation exists here, and none may be added in-process.**
The standard is that a cross-domain operation goes async via events rather than
through an in-process import, and Portfolio has nothing to convert: the two
couplings the table above records, `resume` reading `site-content` for
`project_sort_mode` and every authenticated domain reading `users`, are both
shared reads of a table, not one domain invoking another. The rule therefore
binds forward rather than backward. It is a lint on the new layout, and it is
already expressed structurally: no file under `domains/<name>/` may import from
`domains/<other>/`, and the `tests/entrypoints/` suite is where that gets
asserted. If a future write ever has to span two domains, it is published as an
event and consumed asynchronously, never resolved by importing the other
domain's service, which is exactly the coupling the split exists to remove.

### Route ordering hazard

`/posts/categories` and `/posts/admin` are literal siblings of the
`/posts/{slug}` catch-all inside the same domain. Because both stay inside
`content`, FastAPI's own declaration order continues to resolve them and the
API Gateway routing layer never has to disambiguate. Splitting categories into
its own function would force the gateway to match `/api/v1/posts/categories`
ahead of `/api/v1/posts/{proxy+}`, which HTTP API does support by specificity
but which adds a failure mode for no benefit. This is the main reason the
domain count is four and not five.

## 3. Proposed source layout

The rule the tree encodes: `domains/<name>/{router,service,repository,schemas}.py`
knows nothing about FastAPI hosting or Lambda. `router.py` is the only file in a
domain that imports FastAPI, and no file in a domain imports anything from
`entrypoints/`. The two composition roots are the only places that assemble an
application.

```
backend/
├── pyproject.toml                 replaces requirements*.txt, pins webbpulse-service-core
├── Dockerfile                     one image, the domain chosen at runtime
├── docker-compose.yml             DynamoDB Local, unchanged
├── app/
│   ├── domains/
│   │   ├── content/
│   │   │   ├── router.py          posts and site-content routes, FastAPI only here
│   │   │   ├── service.py         slug generation, publish rules, category guard
│   │   │   ├── repository.py      PostRepository, categories, site-content
│   │   │   ├── schemas.py         post, category, site_content models
│   │   │   └── defaults.py        SITE_CONTENT_DEFAULTS
│   │   ├── resume/
│   │   │   ├── router.py          five CRUD routers plus the projects list override
│   │   │   ├── service.py         project sort mode resolution, ordering
│   │   │   ├── repository.py      the five resume repositories
│   │   │   └── schemas.py
│   │   ├── identity/
│   │   │   ├── router.py          the login route
│   │   │   ├── service.py         credential check, limiter, token mint, admin seed
│   │   │   ├── repository.py      users, login-failure items
│   │   │   └── schemas.py         User, Token, UserLogin
│   │   └── public/
│   │       ├── router.py          sitemap, robots, root, health
│   │       ├── service.py         sitemap construction
│   │       └── repository.py      read-only posts and site-content
│   ├── composition/
│   │   ├── settings.py            the Portfolio Settings subclass
│   │   ├── wiring.py              builds a FastAPI app from a list of domains
│   │   └── app.py                 ROOT A: every domain mounted, for local dev,
│   │                              the test suite, and a future container
│   └── entrypoints/               ROOT B: one per domain, each the image CMD
│       ├── content.py
│       ├── resume.py
│       ├── identity.py
│       └── public.py
├── scripts/
│   └── create_local_tables.py
└── tests/
    ├── conftest.py                shared moto fixtures, table creation
    ├── domains/
    │   ├── content/               unit tests against the service, no HTTP
    │   ├── resume/
    │   ├── identity/
    │   └── public/
    ├── api/                       contract tests through ROOT A, the whole surface
    └── entrypoints/               one smoke test per entrypoint: it imports,
                                   builds, and serves only its own routes
```

`composition/wiring.py` is the piece that makes both roots the same code:

```python
def build_app(domains, *, settings, docs=True):
    app = FastAPI(..., redirect_slashes=False)
    for domain in domains:
        app.include_router(domain.router, prefix=domain.prefix, tags=domain.tags)
    add_middleware(app, settings)   # trailing slash, request logging, CORS
    return app
```

`composition/app.py` calls it with all four domains. `entrypoints/content.py`
calls it with one. The middleware stack, the CORS configuration and the
trailing-slash behaviour are therefore identical in local dev, in tests and in
each deployed function, which is the property that makes the existing test suite
still meaningful after the split.

### Test organisation

The 3,914 lines of existing tests split three ways. Tests that drive HTTP
through `TestClient` move to `tests/api/` and keep running against root A, so
they continue to prove the whole public contract in one process. Tests that
exercise `Repository`, the serializer, the settings and security move to the
shared package's own suite. What is left becomes per-domain service tests. The
new `tests/entrypoints/` suite is small but load-bearing: it asserts that each
entrypoint exposes exactly its own routes and no others, which is what stops a
domain quietly re-acquiring the whole router after a refactor.

### Dockerfile sketch

One Dockerfile and one build, pushed to four repositories. ECR is one repository
per domain per environment, so the build produces a single artifact and tags it
into `webbpulse-<env>-content`, `-resume`, `-identity` and `-public`. The domain
stays a runtime argument, so the four functions run identical bytes and differ
only in the `DOMAIN` variable Terraform sets and in which repository they pull
from. That keeps the build cheap while giving each domain its own lifecycle
policy, its own tag history and its own rollback, and it keeps a staging push
from ever landing in a repository a production function reads.

```dockerfile
FROM public.ecr.aws/docker/library/python:3.13-slim AS base
COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:0.9.1 \
     /lambda-adapter /opt/extensions/lambda-adapter

ENV PORT=8080 \
    AWS_LWA_INVOKE_MODE=buffered \
    AWS_LWA_READINESS_CHECK_PATH=/health \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir . --target /app/deps
ENV PYTHONPATH=/app/deps

COPY app/ ./app/

# DOMAIN is set per function in Terraform. One image, four functions.
ENV DOMAIN=content
CMD ["sh", "-c", "exec uvicorn app.entrypoints.${DOMAIN}:app --host 0.0.0.0 --port ${PORT}"]
```

The adapter runs as a Lambda extension, translates the API Gateway event into an
HTTP request against uvicorn on `$PORT`, and returns the response. Nothing in
`app/` imports `mangum`, `boto3` Lambda types or the adapter itself, which is
the property that lets the identical image run on Fargate or App Runner with no
change beyond dropping the extension layer. `AWS_LWA_READINESS_CHECK_PATH` is
pointed at `/health`, which every entrypoint must therefore serve, so the health
route moves into `composition/wiring.py` rather than living only in the `public`
domain.

**Shared base image.** The install step is the slow half of the build and is
identical across every Python service in the organisation. The proposal is a
`webbpulse-python-base` image in an ECR repository in the WebbPulse Platform
account, built from the shared package's pinned dependency set and pulled
through to each app account behind a repository policy. It is the one ECR
repository that is deliberately not per domain per environment, because it is a
shared service rather than a workload artifact. App images then start `FROM` it
and add only their own source, which turns a two-minute build into a ten-second
one and gives a single place to patch
a CVE in FastAPI or boto3. The blocker is that Portfolio targets `arm64` and
CarModPicker targets `x86_64`, so the base image has to be a multi-architecture
manifest or the two repositories cannot share it. That is a decision to take
before the base image is built, not after.

### Observability: what the code does today, and the standard it moves to

What exists today, as an inventory:

| Concern | Today | Where |
|---|---|---|
| Logging | `aws_lambda_powertools.Logger`, five lines, service name and level from settings | `app/core/logging.py` |
| Request logs | A raw ASGI middleware emitting method, path, status and duration in milliseconds | `app/core/middleware.py` |
| Correlation | Powertools `inject_lambda_context` with the API Gateway HTTP correlation path, `log_event=False` | `app/lambda_handler.py` |
| Tracing | X-Ray active tracing on the function. No manual spans, no instrumented boto3 or HTTP clients | Terraform, `lambda.tf` |
| Metrics | None emitted. `POWERTOOLS_METRICS_NAMESPACE` is set to `WebbPulse/Portfolio` but nothing writes to it | `config.py` |
| Log retention | 30 days on the function log group and the HTTP API access log | Terraform |

The locked standard for the target:

- **OpenTelemetry is the only instrumentation** in the shared Python package.
  Application code calls the OpenTelemetry API and never a vendor SDK, so the
  backend is chosen by configuration rather than by import.
- **AWS native backends by default.** Traces go to X-Ray, structured JSON logs
  go to CloudWatch, and errors are surfaced by a CloudWatch metric filter that
  feeds the existing api-alarms module rather than by a new alarm mechanism.
- **CloudWatch log retention is 7 days everywhere**, down from the 30 currently
  set on both the function log group and the access log.
- **SaaS user interfaces are optional per-project OpenTelemetry exporters and
  never the default.** Adding one is an exporter configuration change in a
  single project, not a change to the shared package or to any application code.

This replaces Powertools as the logging entry point. The Powertools logger and
its `inject_lambda_context` decorator go away with Mangum, and the correlation
id becomes an OpenTelemetry span attribute carried into the structured log
record, which preserves the log-to-trace join without the Powertools dependency.

**Cold start, and why initialisation must be lazy.** Initialising the
OpenTelemetry SDK eagerly at module import is the wrong default in a Lambda
image. The SDK's provider construction, resource detection and exporter setup
run inside the init phase of every cold start, and the AWS resource detectors
in particular can attempt network calls that add latency under a cold container.
On four functions instead of one, every cold start pays that cost, and the
`public` and `identity` functions are small enough that the telemetry setup
could plausibly dominate their init time.

The proposal is that `webbpulse.aws.otel` exposes a lazily initialised provider:
the tracer and the logging handler are constructed on first use behind a module
level guard, not at import, and the exporter is configured from environment
variables so that an unconfigured process pays nothing beyond the guard check.
Under the Web Adapter this is a natural fit, because the adapter's readiness
check against `/health` gives a defined first request during which the provider
can warm rather than blocking the handler path. The shared package should also
default to the batch span processor rather than the simple one, so exports do
not sit on the response path. This is a concrete performance requirement on the
Lambda adapter sub-module and should be measured in the pilot rather than
assumed.

### Rate limiting: the layered standard

Rate limiting is now a locked standard rather than an open question, and it is
layered. Each layer catches what the one below it cannot see, and no layer is
asked to do the job alone.

**Layer 1, the HTTP API stage and per-route throttling.** Free, enforced before
a request reaches a function, and therefore the only layer that protects against
paying for the traffic. `modules/http-api` already sets `default_route_settings`
from `throttling_burst_limit` and `throttling_rate_limit`, which Portfolio calls
with 200 and 100. What it does not have is a per-route `route_settings` block,
so a login route cannot yet be throttled harder than a blog read. Adding
`route_settings` keyed by route is new module work, and it belongs in the same
change as the `integrations` map rather than in a change of its own.

**Layer 2, a per-identity fixed-window limiter in the shared Python package.**
This is the layer that knows who is calling, which the gateway does not. It is
applied to authentication routes and to every mutating route, and it fails
open: if the limiter's own read or write fails, the request proceeds and the
failure is logged, because a limiter outage must never become an availability
outage. It is backed by one `<prefix>-rate-limits` DynamoDB table per
environment with a TTL attribute, separate from the `meta` table the login
limiter shares today, so the limiter's write path can be reasoned about and
its IAM narrowed on its own.

**Layer 3, CloudFront plus WAF, opt-in per project.** Not on by default, and
not part of this migration. It is the answer for volumetric abuse and for
managed rule sets, and it is a per-project decision because it carries real
cost.

**Portfolio's existing limiter is the reference implementation.**
`app/core/login_limiter.py` is 86 lines and already has the shape the standard
wants: a fixed window carried as a TTL, a conditional `ADD` that increments and
sets the expiry in one call, and a fall back to `put_item` when the condition
fails because the window has rolled. Generalising it means parameterising the
key prefix, the window and the ceiling, moving the item from `meta` to the new
`<prefix>-rate-limits` table, adding the fail-open wrapper it does not have
today, and widening the identity from an IP to a caller key so an authenticated
subject can be limited as itself. CarModPicker's `rate_limiter.py` is 282 lines
and in-memory, keyed on `defaultdict` state inside one process, so it cannot
survive a cold start or span concurrent execution environments. It is not a
candidate to generalise; it is a consumer to migrate onto the shared limiter.

**Client IP comes from the API Gateway request context**, forwarded by the
Lambda Web Adapter, and never from the leftmost `X-Forwarded-For` hop. The
leftmost hop is written by the caller and is spoofable, so a limiter keyed on it
is a limiter that any attacker can step around by rotating one header. Where the
request context is absent, as it is in local development and in the test suite,
the limiter treats the identity as unknown and fails open rather than collapsing
every caller into one shared bucket. That last point matters more after the
split than before it: `identity` is its own function, so a single shared bucket
there would rate limit the whole world against one counter.

## 4. Frontend inventory

`frontend/src` is 60 files, 58 of them source once the bundled SVG and README
are set aside, and 7,726 lines: React 19, Vite 7, TypeScript 5.8, Tailwind 3,
react-router-dom 6. Proposed packages live in the TypeScript
packages repo under the `@webbpulse` npm scope, published to CodeArtifact.

| Area | Lines | What it does | Classification | Proposed package |
|---|---|---|---|---|
| `src/services/api.ts` | 500 | The whole API client: base-URL resolution, bearer token, `request<T>`, 38 endpoint methods over 9 resources, 12 exported interfaces | Shareable with extraction | About 95 lines are genuinely generic (`getApiBaseUrl`, `request<T>`, the three auth methods) and become `@webbpulse/api-client`. The 250 lines of interfaces and 155 lines of endpoint methods are Portfolio's contract and stay |
| Auth handling | n/a | There is no auth context. The token lives as a private field on `ApiService`, hydrated from `localStorage` in the constructor, and `AdminPanel` holds a local `useState(false)` that a mount effect flips using `apiService.isAuthenticated()`, so there is one render pass showing signed out before the effect runs | Shareable once written | `@webbpulse/auth-react` does not exist yet. It has to be built, not moved. See the risks section |
| `src/hooks/useApiData.ts` | 278 | Eight resource hooks, each repeating the same `{data, loading, error, refetch}` shape | Shareable with extraction | A generic `useApiResource<T>` goes to `@webbpulse/react-hooks`; the eight named wrappers stay |
| `src/hooks/` others (7 files) | 207 | `useInViewReveal`, `useScrollParallax`, `useCountUp`, `useLocalStorage`, `useReducedMotion`, `useScrollPosition` | Shareable | `@webbpulse/react-hooks`. All are free of app coupling |
| `src/utils/validation.ts` | 67 | Email, URL and length checks plus `getValidationError` | Shareable | `@webbpulse/utils` |
| `src/utils/formatting.ts` | 72 | Date, relative time, truncate, slugify | Shareable | `@webbpulse/utils`. Hardcodes the `en-US` locale, worth parameterising on the way out |
| `src/utils/markdown.ts` (+ test, 305) | 224 | `marked` plus DOMPurify, heading extraction, reading time, and Tailwind class injection | Shareable with extraction | Parse, sanitise, `extractHeadings` and `calculateReadingTime` go to `@webbpulse/markdown`; `addCustomStyling` injects this site's classes and stays. Its test file is the only test in the frontend |
| `src/utils/socialIcons.tsx`, `socialPlatforms.ts` | 82 | An 18-platform icon map and the supported-platform list | Shareable | `@webbpulse/ui`, and it brings `react-icons` as a dependency |
| `src/types/index.ts` | 32 | `BaseComponentProps`, `ButtonProps`, `NavigationItem`, `SocialLink`, `ContactFormData` | Shareable | `@webbpulse/ui` types, despite the file's Portfolio header comment |
| `src/components/common/Button.tsx` | 49 | Four variants and three sizes on stock Tailwind colours | Shareable | `@webbpulse/ui`. The only genuinely generic component in the repository |
| `src/components/common/` others | 99 | `AnimatedOrb`, `GradientText`, `GradientPanel` | Shareable with extraction | Generic mechanisms, but each depends on brand tokens or classes from `globals.css`. They move only if the brand preset moves with them |
| `src/components/admin/MarkdownPreview.tsx`, `MarkdownCheatsheet.tsx` | 230 | Renders processed markdown, and static syntax help | Shareable | `@webbpulse/markdown` |
| `src/components/admin/` remainder (12 files) | 3,210 | `AdminPanel` at 1,274 lines, eight per-resource forms, `LoginForm`, `types.ts` | App-specific | Stays. `types.ts` duplicates the entity interfaces already in `api.ts`, which is worth collapsing while the contract is being touched anyway |
| `src/components/sections/` (10 files) | 2,013 | Hero, About, Skills, Projects, Experience, Blog, BlogList, BlogPost, Contact | App-specific | Stays. Seven of the nine re-implement their own loading and error markup, which is the argument for a shared state component later |
| `src/components/layout/` | 230 | Header and Footer | App-specific | Stays. Both hardcode the owner's name |
| `src/pages/`, `App.tsx`, `main.tsx` | 116 | Route composition and the under-construction flag | App-specific | Stays |
| `src/styles/globals.css` | 97 | Base styles plus `.surface-glass`, `.text-gradient`, `.gradient-border` | App-specific (brand) | Ships next to the Tailwind brand preset |
| `src/test-setup.ts` | 11 | jest-dom matchers and `cleanup()` | Shareable | `@webbpulse/vitest-preset`. There are no mocks, no MSW and no custom render helper to move |

### Tooling presets

| File | Size | Generic share | Proposed package |
|---|---|---|---|
| `eslint.config.js` | 30 lines | 100 percent. Flat config, no project references | `@webbpulse/eslint-config` |
| `tsconfig.json`, `tsconfig.app.json`, `tsconfig.node.json` | 62 lines | Effectively 100 percent. No path aliases exist at all; every import is relative | `@webbpulse/tsconfig` |
| `.prettierrc`, `.prettierignore` | 21 lines | 100 percent | `@webbpulse/prettier-config` |
| `postcss.config.js` | 6 lines | 100 percent | Folded into the Tailwind preset |
| `vitest.config.ts` | 22 lines | About 95 percent. Only `setupFiles` is local. No coverage thresholds are configured, so there is nothing to preserve there | `@webbpulse/vitest-preset` |
| `vite.config.ts` | 22 lines | About 60 percent. The dev proxy target, port 5173 and `host: true` are local | `@webbpulse/vite-preset` with the proxy target as an input |
| `tailwind.config.js` | 232 lines | About 15 percent | Split in two: `@webbpulse/tailwind-preset` for the structural layer (keyframes, animations, shadows, typography scaffolding) and a Portfolio brand token layer that stays. Shipping it whole would push WebbPulse navy and cyan onto every future consumer |

### The API contract survives the split

This is the load-bearing finding for the backend work. Every network call goes
through `ApiService.request()`, which holds the single `fetch` in the whole
application. A grep for `fetch(`, `/api/v1`, `localhost:8000`, `skip=` and
`limit=` across all of `src/` outside `services/api.ts` returns nothing. No
component, hook or page builds a URL. The one hit outside `src/` is
`vite.config.ts`, which hardcodes `http://localhost:8000` as the dev server
proxy target, so that file is a second place the backend origin is written down
and it has to move with any host change. So path-prefix routing to
several functions needs no frontend edit, as long as every prefix stays behind
the single `api.webbpulse.com` host.

Three caveats the routing design has to respect:

1. `/posts/categories` and `/posts/admin` are literal siblings of the
   `/posts/{slug}` catch-all, and `getBlogPost(id)` and `getBlogPostBySlug(slug)`
   hit the same template. Any path-prefix router must match `/posts/admin` and
   `/posts/categories` before `/posts/{param}`. This is the single strongest
   argument for keeping posts and categories inside one domain function rather
   than splitting categories out.
2. Trailing slashes are inconsistent and load-bearing. Collection GETs carry a
   trailing slash, item routes do not, and `getProjects(true)` emits the
   malformed `/projects?featured_only=true/` with the query string before the
   slash. `TrailingSlashMiddleware` currently absorbs this. If the routing layer
   normalises or redirects on trailing slashes, that URL is where it breaks
   first. It deserves an explicit test in the pilot.
3. `credentials: 'include'` is set on every request, for the access gate's
   signed cookies. That forbids a wildcard `Access-Control-Allow-Origin`, so if
   any prefix ever moves to a different hostname, every new function needs
   per-origin CORS with `Allow-Credentials`. Staying on one host avoids it.

There is no pagination coupling at all: no `skip`, `limit`, `page`, `offset` or
cursor anywhere in the frontend, even though the backend accepts them. Adding
pagination later is an additive change, not a migration blocker.

## 5. Terraform and CI impact

The Terraform root is 944 lines across 18 files, and almost all of it is
registry module calls. There are only six bare resource blocks in the whole
root, which is why most of the work below lands in the platform modules rather
than in this repository.

### Files in `terraform/` that change

| File | Lines | Change |
|---|---|---|
| `lambda.tf` | 143 | The largest change. `module.lambda_artifacts` and `data.archive_file.lambda_placeholder` are deleted outright. `module.lambda_api` becomes a `for_each` over the four domains with `package_type = "Image"` and `code = { image_uri = ... }`. `log_retention_days` goes 30 to 7. The `POWERTOOLS_*` variables are replaced by the OpenTelemetry exporter configuration. `aws_iam_role_policy.lambda_api` splits: one shared customer managed policy for the DynamoDB and secrets statements attached N times, plus a small per function inline policy for its own log group. `public` gets a narrower policy with no Secrets Manager statement |
| `apigateway.tf` | 49 | `route_keys` gives way to an `integrations` map, one entry per domain with its path prefixes. The monolith keeps a catch-all during the strangler. `access_log_retention_days` goes 30 to 7 |
| `staging_access_gate.tf` | 33 | One added argument, `log_retention_days = 7`. Nothing else. The gate is orthogonal to the function count |
| `monitoring.tf` | 30 | `lambda_function_name` gives way to the new aggregate inputs, so the two per function Lambda alarms become two aggregate alarms covering all N |
| `outputs.tf` | 79 | `lambda_artifact_bucket` is deleted. `lambda_function_name` becomes a map. A new `ecr_repository_url` output is added |
| `iam_github_actions.tf` | 80 | The S3 artifact statement is deleted. The Lambda statement's resource becomes the list of N function ARNs. ECR push actions are added, with `ecr:GetAuthorizationToken` on `"*"` because it takes no resource |
| `versions.tf` | 26 | `hashicorp/archive` leaves `required_providers`; it existed only for the placeholder zip |
| `s3.tf` | 6 | Already only a comment. Unaffected |

`dynamodb.tf` gains one table. The rate limiting standard puts the per-identity
limiter on its own `<prefix>-rate-limits` table with `ttl_attribute = "ttl"` and
`point_in_time_recovery = false`, exactly the shape `meta` already uses, so it is
one entry added to `local.dynamodb_tables` and no module change at all.

`db.tf`, `frontend.tf`, `acm.tf`, `route53.tf`, `management.tf`, `locals.tf`,
`providers.tf`, `data.tf` and `variables.tf` are untouched.

### Platform module work

| Module | Change | Kind |
|---|---|---|
| `lambda-function` | **Cannot deploy an image today, despite appearances.** `code.image_uri` is already plumbed, but `package_type` is never set so the provider defaults to `Zip` and the Lambda API rejects the pair; `runtime` and `handler` are required and validated non-empty, which an image call cannot satisfy; and `image_uri` is missing from the hardcoded `ignore_changes` list, so the next plan after any CI deploy would revert the function to its seed image. The `code` variable's own description already promises an `ignore_code_changes` input that was never implemented | New inputs, one of them a correctness fix |
| `http-api` | **Architecturally one Lambda to one API.** A single `lambda_invoke_arn` variable, a single `aws_apigatewayv2_integration.lambda`, a single `aws_lambda_permission`, and every route targets that one integration. Per prefix routing needs a new `integrations` map and `for_each` on all three resources, with `moved` blocks. The existing trio stays as the single integration path so CarModPicker does not break. `lambda_permission_statement_id` has to become per integration. Separately the stage sets only `default_route_settings`, so **per-route throttling does not exist yet**; layer 1 of the rate limiting standard needs a `route_settings` input, and it belongs in this same change | New inputs, the largest single piece of module work |
| `api-alarms` | New `lambda_aggregate_alarm`, `lambda_aggregate_name_pattern` and the matching threshold, period and evaluation inputs, mirroring the `dynamodb_aggregate_*` set added two commits ago | New inputs |
| `ecr-repository` | Does not exist. `aws_ecr` and `package_type` return zero hits across the whole platform repository on `main`, though a `tw/ecr-repository` branch and an `ecr-module` worktree exist locally with no pull request open. Needs the repository, a lifecycle policy, and a repository policy so the Platform account's base image can be pulled cross account. Called once per domain per environment | **The only genuinely new module** |
| `lambda-artifacts-bucket` | Dropped from the Portfolio call but kept in the repository while CarModPicker still ships zips | No change |
| `staging-access-gate` | None. Pass `log_retention_days = 7` | No change |
| `github-actions-role` | None. `policy_statements` is already a free-form list, so the ECR statements are a pure input change | No change |

Seven-day retention needs no module work at all. All three modules already
validate 7 against the CloudWatch enum, so it is three argument edits.

### The access gate keeps working, by construction

This is the reassuring part. The authorizer attaches at the **route** level, not
the integration level, and `modules/http-api` already applies `var.authorizer_id`
uniformly to every route it creates. So every new per prefix route inherits the
same REQUEST authorizer, and all four functions share one Cognito pool, one
signing key pair, one origin verify secret and one authorizer Lambda. The
authorizer admits a request on an OPTIONS preflight, a matching `x-origin-verify`
header, or valid CloudFront signed cookies, and it returns a simple
`{isAuthorized: true}` with no context.

Three conditions must hold, and they are the real risks:

1. **Every route must be created by the module.** A route added inline for a new
   domain defaults to `authorization_type = NONE`, which is an open bypass
   straight past the gate. The `integrations` input must apply the authorizer
   unconditionally rather than per integration opt-in.
2. `disable_execute_api_endpoint` must stay `true`. It is the only thing forcing
   traffic through the authorized custom domain.
3. The functions must not start making their own auth decisions from headers the
   gate does not strip, because the authorizer passes them no identity.

### How the workflows collapse

The four workflows become consumers of reusable `workflow_call` workflows in an
org `.github` repository. The concrete duplication available to lift today:

- **The TFC wait step is a character-for-character 35-line duplicate** between
  `deploy-backend.yml` and `deploy-frontend.yml`, including the embedded Python
  heredoc and its indentation. The strongest single candidate.
- The deploy job preamble: the `permissions` block, the `concurrency` group, the
  `STAGING_DEPLOY_ENABLED` job gate, the environment ternary and the three TFC
  environment variables, all identical.
- The OIDC credential step, identical in both deploy workflows.
- Node setup plus `npm ci`, identical between `deploy-frontend` and
  `test-frontend`.
- Python setup in both backend workflows, where the test workflow caches pip and
  the deploy workflow does not, an inconsistency worth folding in.
- The action version pins repeated in all four, so a bump is currently a four
  file edit per repository.

The image build, ECR push and `update-function-code` loop will be identical
between Portfolio and CarModPicker, so it should be authored as a reusable
workflow from the start rather than copied once and diverged.

### The HCP run poll, and what N functions do to it

The poll resolves the workspace id, then reads the single most recent run and
waits while its status is not one of `applied planned_and_finished discarded
errored canceled force_canceled`, treating `no_runs` as idle. Forty attempts at
fifteen seconds is a ten minute ceiling, then a hard failure. The whole step is
skipped when `TFC_API_TOKEN` is empty.

It **generalises to N functions for free**, because it polls the workspace and
not any resource. But the race it exists to prevent gets worse. Today the window
between the poll and the single `update-function-code` is short. With four
functions the window stretches across four updates, and a Terraform run that
starts mid-loop can revert some functions and not others, leaving the API
serving a mixture of old and new code behind one hostname. Two consequences:

1. Fixing the `image_uri` ignore list in `lambda-function` is a **prerequisite**,
   not a nicety. Without it an apply during that window resets functions to the
   seed image.
2. The deploy should fire all N `update-function-code` calls first and then wait
   on all N, rather than serialising wait, update, wait per function. Image
   updates settle more slowly than zip updates, so the serial shape would widen
   the very window that is the problem.

One more CI caveat: the smoke test today probes only `/health`, in a ten
attempt retry loop at six second intervals, and asserts the body reports
`"database": "healthy"` rather than merely returning 200. `deploy-frontend.yml`
has no smoke test at all. During the strangler the monolith answers `$default`,
so `/health` will pass whether or not a newly split domain works. The smoke
test must probe one path per domain or it will give false confidence at exactly
the moment it matters.

### A docs-only pull request deploys nothing

Verified from both gates.

**GitHub Actions.** All four workflows use `paths:`, which is an allow list, and
the union of every filter across all four is exactly `backend/**`, `frontend/**`
and the four workflow files' own paths. The two deploy workflows trigger on
`push` to `main` and `staging`; the two test workflows trigger on `pull_request`
against the same branches. A change touching only `docs/**` matches none of the
four filters, so zero workflows run on push or on the pull request. Both deploy
workflows also declare a bare `workflow_dispatch:` with no path filter, which is
the one way this content could be deployed, and only by someone starting a run
by hand. The same is true of `terraform/**`, which is
deliberate, since Terraform is driven by HCP's own VCS trigger rather than by
Actions.

**HCP Terraform.** The trigger patterns are not committed anywhere in the
repository; they are workspace-side settings. Queried against the API directly,
both workspaces report:

| Workspace | trigger-patterns | working-directory | branch |
|---|---|---|---|
| `WebbPulse-Portfolio` | `/terraform/**/*` | `terraform` | `main` |
| `WebbPulse-Portfolio-staging` | `/terraform/**/*` | `terraform` | `staging` |

So a pull request that only adds `docs/migration/inventory.md` triggers no
GitHub Actions workflow and queues no HCP Terraform run. **This pull request
deploys nothing and changes no AWS resource.**

## 6. Risks and open questions

### Risks

| Risk | One-line statement |
|---|---|
| Mangum coupling in the rate limiter | `client_ip()` reads `request.scope["aws.event"]` first, which the Lambda Web Adapter does not set, so under the adapter it falls through to its `X-Forwarded-For` branch without failing, which is the worse outcome because nothing signals the change |
| Trusting `X-Forwarded-For` naively | The existing fallback already takes the leftmost hop, which is caller-controlled, so any client can spoof an address and evade the limiter today the moment the `aws.event` branch stops matching. The fix is to read the API Gateway request context the adapter forwards, and to treat a missing context as fail open rather than as a usable address |
| `image_uri` missing from the module's ignore list | Every plan after a CI deploy would revert functions to their seed image, so this must be fixed in `lambda-function` before any image deploy is wired up |
| Settings fail fast at import | `resolve_secrets` raises when `SECRET_KEY`, `ADMIN_USERNAME`, `ADMIN_PASSWORD` or `ADMIN_EMAIL` are absent, so a secret-free `public` entrypoint cannot import today's `Settings` unchanged |
| Route created outside the `http-api` module | Any route added inline defaults to `authorization_type = NONE` and is an open hole straight past the staging gate |
| Cold start regression from eager OpenTelemetry init | Importing and configuring the SDK at module scope adds meaningful init time per cold start in an image based function, which is why initialisation belongs in the Lambda adapter, deferred to first use |
| Cold start regression from image size | An OCI image cold starts more slowly than a small zip, and four functions mean four independently cold paths where there is one today |
| Deploy versus apply race widens with N | The window between the HCP poll and the last `update-function-code` grows with the function count, so a mid-loop apply can leave a mixture of old and new code behind one hostname |
| Smoke test gives false confidence | Probing a single `/health` will pass while the monolith holds `$default`, whether or not the newly split domain works |
| Path prefix collision at the gateway | `/posts/categories` and `/posts/admin` are siblings of the `/posts/{slug}` catch-all, so splitting them across functions moves resolution from FastAPI's ordered matcher to API Gateway's, where the more specific literal must be routed explicitly |
| Shared package convergence is not a lift and shift | Portfolio and CarModPicker have parallel implementations rather than copied code, so every shared module needs a winner picked and the loser migrated, which is design work and not a move |
| CodeArtifact in the deploy path | Every build now depends on the Platform account's repository and a token that expires, so an outage or an expired token blocks all deploys across both applications |
| Cross repository version skew | Once shared code lives elsewhere, a breaking change ships on someone else's schedule, so pinning and a deprecation window matter more than they do today |
| Manual GitHub Environment variables | Terraform outputs are hand copied into environment variables, so an apply that renames or splits an output silently breaks deploys until a human catches up |
| Four IAM policies instead of one | Least privilege per domain is the point, but it multiplies the surfaces where a missing action shows up only at runtime |
| Log group ownership | Image based functions still create their own log groups on first invoke, so retention must be set on a Terraform managed group or the 7-day rule quietly does not apply |
| Fail open is a deliberate hole | The limiter proceeds when its own read or write fails, which is right for availability and wrong for an attacker who can induce that failure, so the fail-open path must emit a metric and alarm rather than passing silently |
| `SeedMiddleware` on a read-only domain | The seeders write the admin user and the site-content row on the first HTTP request in a process, so wiring the existing middleware stack into the `public` entrypoint would make the least-privileged function attempt two writes it has no IAM for |

### Open questions

| Question | One-line statement |
|---|---|
| Shared base image contents | Whether the base carries only the adapter and the runtime, or also the shared package, which speeds builds but couples releases |
| Monolith retirement criterion | What has to be true before the `$default` catch-all is removed, and whether it is removed at all or kept as a deliberate fallback |
| Repository interface shape | Whether the shared package exports the generic `Repository` as a base class or as a protocol with a DynamoDB implementation, which decides how hard the data store seam actually is |
| `public` domain necessity | Whether four health and metadata routes justify their own function, or whether they belong with identity and the answer is three domains |
| Test layout across composition roots | Whether the moto suite runs once against the all-domains app or once per entrypoint, which changes runtime and what the tests actually prove |
| Trace sampling rate | What X-Ray sampling to run at, given that a low rate on low traffic staging can leave an incident with no trace at all |
| Metric filter versus native error metrics | Whether errors reach the alarms through a log metric filter or through the OpenTelemetry metrics pipeline, which decides whether the filter pattern becomes a second contract on log shape |
| CodeArtifact package naming | The namespace and version policy for the Python and TypeScript packages, which is hard to change once two applications depend on it |
| Reusable workflow versioning | Whether consumers pin the org workflows by tag or track a branch, which trades a bump chore against unannounced breakage |
| Frontend split | Whether the frontend is decomposed alongside the backend or deliberately left whole, since nothing in the locked decisions requires splitting it |
| Rate limit identity for anonymous callers | What the per-identity limiter keys on before a caller authenticates, given that the source IP behind CloudFront is coarse and that fail open on a missing request context is a deliberate hole an attacker can aim for |
| Per-route throttle values | What burst and rate the login route and the mutating routes actually get, since the stage default of 200 and 100 is far too generous for `/admin/login` and far too tight to apply uniformly to reads |

## 7. Suggested pull request sequence

Portfolio goes first as the pilot. It is the smaller of the two applications, its
domains separate cleanly, and everything learned here becomes the template for
CarModPicker. Sizes are rough and count changed lines, not files.

| # | Pull request | Repository | Size | Depends on | What it proves |
|---|---|---|---|---|---|
| 1 | This inventory and proposed layout | Portfolio | 400, docs only | none | Agreement on the four domains and the target layout before any code moves |
| 2 | Fix `lambda-function` for images: set `package_type`, relax the `runtime` and `handler` validations, add `image_uri` to `ignore_changes`, implement the promised `ignore_code_changes` | platform-modules | 80 | 1 | An image can be deployed at all, and CI updates survive the next plan |
| 3 | New `ecr-repository` module with a lifecycle rule and a cross account pull policy, called once per domain per environment | platform-modules | 120 | none | Somewhere to push to, with staging and production separated at the repository |
| 4 | Add `lambda_aggregate_alarm` and its inputs to `api-alarms` | platform-modules | 90 | none | Alarms stop being per function before there are four of them |
| 5 | Add the `integrations` map and `for_each` to `http-api`, with `moved` blocks, keeping the single integration path intact, plus the `route_settings` input for per-route throttling | platform-modules | 300 | none | The largest module change, merged and tagged well before anything depends on it. Layer 1 of the rate limiting standard lands with it |
| 6 | Rewrite `client_ip()` against the API Gateway request context the Web Adapter forwards, remove both the `aws.event` read and the spoofable leftmost `X-Forwarded-For` fallback, move the limiter items to a new `<prefix>-rate-limits` table, add the fail-open wrapper, add tests | Portfolio backend | 200 | none | The one real behaviour change, landed alone where it can be reviewed on its merits. It is also the prototype of the shared limiter, so it is written to be generalised in PR 10 |
| 7 | Restructure `app/` into four domain packages behind the existing app, no behaviour change, no infrastructure change | Portfolio backend | 900, mostly moves | 6 | The seams hold and the full route list is unchanged |
| 8 | Add the two composition roots: the all-domains app and four per-domain entrypoints, plus a `Settings` variant that does not require secrets | Portfolio backend | 250 | 7 | Each domain starts on its own, and `public` starts without Secrets Manager |
| 9 | Dockerfile, shared base image, Lambda Web Adapter, uvicorn, local compose | Portfolio backend | 200 | 8 | The identical image runs locally, and would run on Fargate or App Runner |
| 10 | Shared Python package: extract the framework-neutral core, generalise Portfolio's limiter from PR 6 into `webbpulse.core.rate_limit`, publish to CodeArtifact in the Platform account | new org repo | 800 | 6, 7 | Something to depend on, versioned, before either application depends on it. The limiter arrives already proven in one production service |
| 11 | OpenTelemetry in the shared package with lazy init in the Lambda adapter, X-Ray traces, JSON logs | new org repo | 350 | 10 | Instrumentation exists once, and cold start cost is measured rather than assumed |
| 12 | Portfolio consumes the shared package, CodeArtifact auth in CI | Portfolio | 300 | 10, 11 | The dependency direction is real and the build works against it |
| 13 | Reusable `workflow_call` workflows in the org `.github` repo, starting with the duplicated TFC wait step | org .github | 400 | none | One copy of the 35 lines that are currently duplicated character for character |
| 14 | Portfolio workflows become consumers, add image build and ECR push, per-domain smoke tests | Portfolio | 300, mostly deletions | 9, 12, 13 | CI can build and push an image |
| 15 | Terraform: four ECR repositories, `for_each` Lambda functions on images, drop the artifacts bucket and the archive provider, 7-day retention, per-domain IAM, ECR permissions on the CI role, per-route throttling on the auth and mutating routes | Portfolio terraform | 400 | 2, 3, 4, 5 | The infrastructure exists, with the monolith still holding `$default` |
| 16 | Route `/health` and the metadata routes to the `public` function | Portfolio terraform | 40 | 15 | The first live prefix cut, on the domain with the least to lose |
| 17 | Route the resume prefixes | Portfolio terraform | 40 | 16 | The largest domain by route count, cut once the pattern is proven |
| 18 | Route the content prefixes, including the `/posts` literal siblings | Portfolio terraform | 60 | 17 | The only genuinely tricky routing, cut last among the reads |
| 19 | Route the identity prefix | Portfolio terraform | 40 | 18 | Auth moves last, when rollback is still one revert |
| 20 | Remove the `$default` catch-all and the monolith entrypoint | Portfolio | 150, mostly deletions | 19 | The strangler completes |
| 21 | Shared TypeScript packages, published to CodeArtifact | new org repo | 500 | none | Frontend sharing starts, independent of the backend work |
| 22 | Portfolio frontend consumes the shared packages | Portfolio frontend | 200 | 21 | Confirms the package boundaries before CarModPicker adopts them |
| 23 onward | Repeat 6 through 20 for CarModPicker, reusing every module and workflow | CarModPicker | | 20 | The pilot pays off, or shows where the template was wrong |

Pull requests 2 through 5 are independent of each other and can run in parallel.
So can 13 and 21. The serial spine is 6, 7, 8, 9, then 15, then the routing cuts
16 through 20, one domain at a time so that any regression is one revert away.
PR 6 now sits on that spine twice over: it is the prerequisite for the split and
the prototype the shared limiter in PR 10 is generalised from, which is the
argument for landing it first and alone.

**One prerequisite sits outside this table.** PRs 10, 11, 12 and 21 all publish
to or consume CodeArtifact in the WebbPulse Platform account, which is being
vended now. Nothing before PR 10 depends on it, so the account's arrival is not
on the critical path for the pilot: everything from PR 2 through PR 9 lands in
Portfolio and in platform-modules against accounts that already exist, with
production in member account `036807648992`. If the Platform account slips, the
split still completes through PR 9 and stalls only at the shared package, which
is the correct place for it to stall.
