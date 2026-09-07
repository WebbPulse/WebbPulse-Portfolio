# Pilot split plan: WebbPulse Portfolio into per-domain Lambdas

This is the concrete implementation plan for the pilot. It follows
`docs/migration/inventory.md`, which recorded what exists and proposed a shape,
and the locked decisions in
`WebbPulse-Platform/docs/design/2026-09-07-platform-migration-design.md`. Where
this plan disagrees with the inventory it says so and gives the reason; the
inventory was written before three of the four dependencies existed, and several
of the things it lists as work to do are already done.

Nothing here changes application code, Terraform, or workflows. This document is
the plan the pull requests in section 8 execute.

## 0. What changed since the inventory was written

The inventory is one day old and four of its load-bearing claims are now stale.
Verified by reading the repositories on `main` on 2026-09-07.

| Inventory said | Reality now |
| --- | --- |
| `lambda-function` "cannot deploy an image today": `package_type` never set, `runtime` and `handler` required, `image_uri` missing from `ignore_changes` | All three are fixed. `package_type` is an input validated to `Zip` or `Image`; `runtime` and `handler` are validated to be null when `package_type = "Image"`; `image_uri` is in the `ignore_changes` list in `modules/lambda-function/function.tf`. There is also an `image_config` input. **No module work needed** |
| `http-api` is "architecturally one Lambda to one API" and needs a new `integrations` map, `for_each`, and `moved` blocks, "the largest single piece of module work" | Already shipped and already in use. Portfolio's `terraform/apigateway.tf` calls it today with an `integrations` map (`legacy`), a `routes` map, and `default_integration = null`. The module's own variable descriptions are written for exactly this strangler migration. **No module work needed** |
| `ecr-repository` "does not exist. The only genuinely new module" | Exists on `main`, ships from 1.8.0, with lifecycle rules, immutable tags, and a documented cross-account Lambda pull policy. **No module work needed** |
| Shared package is `webbpulse-service-core`, imported as `webbpulse.core` | The package is `webbpulse`, imported as `webbpulse`. There is no `webbpulse.core` subpackage. Anything written against the old name fails at both install and import |
| Reusable workflows are PR 13, "none exist yet" | `container-image.yml`, `lambda-image-deploy.yml` and `python-ci.yml` all exist in `WebbPulse/.github` and are tagged `v1`. `lambda-image-deploy.yml` already accepts a `function-image-map` for the N-function case |

Two things the inventory expected to be ready are not:

- **The `webbpulse` package has no git tags and has never been published.**
  `__version__` is `0.1.0` in `src/webbpulse/_version.py`, but `v0.1.0` was never
  tagged and `publish.yml` triggers on `tags: ["v*"]`. Nothing can `pip install
  webbpulse` today. This is a hard prerequisite, tracked in section 8.
- **`api-alarms` is still single-function.** `lambda_function_name` is one string
  feeding the `FunctionName` dimension of the errors and throttles alarms. Its
  `error_log_groups` input is already a map, so the log-based alarm generalises
  for free, but the two metric alarms do not. This is the one genuine remaining
  module gap, and section 3 proposes the narrowest fix.

The practical consequence is that the module work the inventory put on the
critical path is done. What is left is application code, Terraform in this
repository, CI wiring, and publishing the shared package.

**One pinning note that affects every module call below.** The modules repository
tags the whole repository, not each module, and the latest tag is `v2.0.0`. The
individual module READMEs still show `~> 1.6`, `~> 1.7` and `~> 1.8`, which is
what they said when they were written. Those constraints are valid but they float
across 1.x only, so a new call written against the current registry release wants
`version = "~> 2.0"` on all five modules. The version numbers in the HCL below
are written that way. The root README's own rule: a two-segment constraint such
as `~> 1.1` floats across all of 1.x, and `~> 1.3.0` is how you hold a minor.

## 1. Domain map

Route counts below were produced by building the app and walking `app.routes`,
counting method-path pairs and excluding `HEAD` and `OPTIONS`. The app exposes
**48** such pairs: 44 application routes and 4 documentation routes
(`/docs`, `/docs/oauth2-redirect`, `/redoc`, `/openapi.json`).

The four domains from the design hold up against the actual routers. The split
follows the tables rather than the URL tree, which is why categories stay with
posts and why the site-content singleton sits with `content` rather than with
the resume material.

### content, 14 routes

From `backend/app/api/v1/endpoints/posts.py` (12 decorators) and
`backend/app/api/v1/endpoints/site_content.py` (2), plus
`backend/app/core/site_content.py` and `backend/app/core/site_content_defaults.py`.

```
GET    /api/v1/posts/
GET    /api/v1/posts/admin
POST   /api/v1/posts/admin
PUT    /api/v1/posts/admin/{post_id}
DELETE /api/v1/posts/admin/{post_id}
POST   /api/v1/posts/admin/{post_id}/publish
GET    /api/v1/posts/categories
POST   /api/v1/posts/categories
PUT    /api/v1/posts/categories/{category_id}
DELETE /api/v1/posts/categories/{category_id}
GET    /api/v1/posts/category/{category_slug}
GET    /api/v1/posts/{slug}
GET    /api/v1/site-content/
PUT    /api/v1/site-content/
```

Owns `posts`, `categories`, `site-content`. Reads `users` for admin
authorisation. Writes `meta` for the `COUNTER#` and `UNIQUE#` items every create
goes through.

### resume, 25 routes

From `projects.py` (1 custom list plus 4 CRUD), `experience.py`, `skills.py`,
`education.py`, `certifications.py` (5 each). The CRUD shape comes from
`build_crud_router` in `backend/app/api/v1/crud_router.py`: `GET /`,
`GET /{item_id}`, `POST /`, `PUT /{item_id}`, `DELETE /{item_id}`.

```
GET    /api/v1/projects/            (custom, honours featured_only and project_sort_mode)
GET    /api/v1/projects/{item_id}
POST   /api/v1/projects/
PUT    /api/v1/projects/{item_id}
DELETE /api/v1/projects/{item_id}
... and the same five for experience, skills, education, certifications
```

`projects.py` is built with `include_list=False` and declares its own `GET /`,
so it is 5 routes like the rest. `skills` raises the CRUD limits to
`default_limit=100, max_limit=200`; nothing else differs.

Owns `projects`, `experience`, `skills`, `education`, `certifications`. Reads
`site-content` for `project_sort_mode` and `users` for admin checks. Writes
`meta` for counters.

### identity, 1 route

From `backend/app/api/v1/endpoints/admin.py`.

```
POST   /api/v1/admin/login
```

Owns `users`. Writes the `LOGIN_FAIL#` limiter items, which move to the new
`<prefix>-rate-limits` table (section 3). One route, its own function: it is the
only component that verifies passwords, mints tokens, and reads the signing key,
so isolating it means the signing key is reachable from exactly one function.
That is a blast-radius argument, not a volume argument, and it is the right
trade here.

### public, 4 routes

From `backend/app/api/seo.py` (2) and `backend/app/main.py` (2).

```
GET    /
GET    /health
GET    /sitemap.xml
GET    /robots.txt
```

Reads `posts` (the published GSI, for the sitemap) and `site-content` (for
`database_status()`). Writes nothing. Needs no Secrets Manager access at all,
because it has no authenticated route.

### Table ownership

`meta` holds three item families: `COUNTER#<entity>` sequence counters,
`UNIQUE#<entity>#<field>#<value>` uniqueness lookup items, and today
`LOGIN_FAIL#<ip>`. The first two are written by `Repository.create` in
`backend/app/db/repository.py` for every entity, so **every writing domain needs
read and write on `meta`**. This is a correction worth stating plainly: `meta` is
not identity's table, it is shared infrastructure for the id allocator.

| Domain | Owns (read and write) | Reads only | Secrets Manager |
| --- | --- | --- | --- |
| `content` | posts, categories, site-content, meta | users | yes |
| `resume` | projects, experience, skills, education, certifications, meta | site-content, users | yes |
| `identity` | users, rate-limits | meta | yes |
| `public` | none | posts (+ published-index), site-content | **no** |

### Cross-domain calls

**There are none, and none need to become async.** The two couplings that exist
are both shared reads of a table, not one domain invoking another:

- `resume` reads the `site-content` singleton for `project_sort_mode`.
- `content`, `resume` and `identity` all read `users` to authorise admin writes.

Admin authorisation being a table read rather than a service call is what makes
this split safe. Nothing has to be duplicated and nothing has to be published as
an event. The rule binds forward, not backward: no file under `domains/<name>/`
may import from `domains/<other>/`, and `tests/entrypoints/` is where that is
asserted. If a future write ever spans two domains it goes out as an event.

### Route ordering, and why the count is four

`/api/v1/posts/categories` and `/api/v1/posts/admin` are literal siblings of the
`/api/v1/posts/{slug}` catch-all. Because all three stay inside `content`,
FastAPI's declaration order continues to resolve them and API Gateway never has
to disambiguate. Splitting categories into a fifth domain would push that
resolution into the gateway for no benefit. Four domains, not five.

### Adjustments to the design's map

The design named the four domains and this plan keeps all four. Three
refinements fall out of reading the code:

1. **`meta` is shared, not identity's.** Stated above. The design's IAM sketch
   gave `meta` to identity alone; every writing domain needs it.
2. **`public` must not get `SeedMiddleware`.** `backend/app/core/middleware.py`
   runs `ensure_admin_seeded()` and `ensure_site_content_seeded()` on every HTTP
   scope, which writes the `users` and `site-content` tables on the first request
   in a process. Wiring today's middleware stack into `public` would make the
   least-privileged function attempt two writes it has no IAM for, on its first
   request. This is the sharpest edge in the split.
   **`client_ip()` silently changes meaning under the adapter**, and it gates
   `identity`. `backend/app/core/login_limiter.py` reads
   `request.scope["aws.event"]` first, which is a Mangum artifact the Web Adapter
   does not set, then falls through to the leftmost `x-forwarded-for` hop, which
   a client controls. Under the adapter the limiter therefore keys on a spoofable
   value and stops limiting anything. The correct source is the
   `x-amzn-request-context` header the adapter injects, and three details about
   it matter, all verified against the adapter source and the HTTP API payload
   reference
   (https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-develop-integrations-lambda.html):
   the header is **plain JSON, not base64**, so it is a straight parse; on
   **payload format 2.0** the field is **`requestContext.http.sourceIp`**, not
   the `identity.sourceIp` that the adapter's own README example shows, because
   that example is the 1.0 REST shape and reads as undefined on a 2.0 HTTP API;
   and the adapter strips bytes below `0x20` from the header value rather than
   escaping them, which is harmless for an IP. The shared package's `client_ip`
   already reads this header correctly, so the fix is to adopt it rather than to
   write it, and its `test_client` fixture takes a `source_ip` and a
   `payload_format` so a test can exercise the real path.
3. **`/health` moves into shared wiring, not the `public` domain.** The Web
   Adapter's readiness check points at `/health`, so every function must serve
   it. The shared package's `create_app` already adds `GET /health` via
   `include_health=True`, and its `health_router` is liveness-only and does no
   I/O by design. Portfolio's current `/health` calls `database_status()`, which
   reads DynamoDB. Keep the I/O-free one on the adapter path and expose the
   database check as `public`'s own route, or the readiness probe takes a
   DynamoDB read on every cold start.

## 2. Code layout

### The two composition roots

Root A, `backend/app/composition/app.py`, mounts every domain. It is what local
development, the existing `TestClient` suite, and any future container run
against. Root B is `backend/app/entrypoints/<domain>.py`, one per domain, each
the `CMD` of a deployed image.

The shared package gives both roots directly. From
`/home/tyler-webb/Documents/Github/WebbPulse/webbpulse-python/src/webbpulse/http.py`:

```python
def create_app(
    domain_routers: Iterable[APIRouter] = (),
    *,
    title: str = "WebbPulse service",
    version: str = "0.0.0",
    service_name: str = "webbpulse",
    settings: BaseServiceSettings | None = None,
    cors_allow_origins: Sequence[str] | None = None,
    cors_allow_credentials: bool | None = None,
    router_prefix: str = "",
    include_health: bool = True,
    instrument: bool = True,
    **fastapi_kwargs: Any,
) -> FastAPI: ...

def mount_all(
    apps: Mapping[str, FastAPI],
    *,
    title: str = "WebbPulse",
    version: str = "0.0.0",
    service_name: str = "webbpulse",
    **fastapi_kwargs: Any,
) -> FastAPI: ...
```

So root B is `create_app([router], router_prefix="/api/v1", settings=settings)`
and root A is `mount_all({...})` over the four. `create_app` adds CORS, the
request-id middleware, the error handlers and `GET /health` in request-traversal
order, so the middleware stack is identical in local development, in tests, and
in each deployed function. That property is what keeps the existing test suite
meaningful after the split.

Two behaviours of `create_app` to design against, both verified in the source:

- `cors_allow_origins` takes precedence over `settings`, and the CORS middleware
  is only added when the resolved origin list is non-empty. Portfolio sends
  `credentials: 'include'` on every request for the access gate's signed
  cookies, so the origin list must be exact and non-empty in every environment.
  `create_app` raises `ValueError` if credentials are on and `"*"` is in the
  list, which is the right failure.
- `redirect_slashes` is not a `create_app` parameter, so it goes through
  `**fastapi_kwargs`. Portfolio's `main.py` sets `redirect_slashes=False` today
  and the frontend depends on it: `getProjects(true)` emits the malformed
  `/projects?featured_only=true/`, which `TrailingSlashMiddleware` absorbs. Pass
  `redirect_slashes=False` in every entrypoint and keep the trailing-slash
  middleware, or that URL breaks first.

### Package structure

```
backend/
├── pyproject.toml              replaces requirements*.txt, pins webbpulse
├── Dockerfile                  one image, domain chosen by build arg
├── docker-compose.yml          DynamoDB Local, unchanged
├── app/
│   ├── domains/
│   │   ├── content/{router,service,repository,schemas,defaults}.py
│   │   ├── resume/{router,service,repository,schemas}.py
│   │   ├── identity/{router,service,repository,schemas}.py
│   │   └── public/{router,service,repository}.py
│   ├── composition/
│   │   ├── settings.py         the Portfolio BaseServiceSettings subclass
│   │   ├── wiring.py           domain descriptors, shared middleware
│   │   └── app.py              ROOT A: mount_all over all four
│   └── entrypoints/
│       ├── content.py          ROOT B, one per domain
│       ├── resume.py
│       ├── identity.py
│       └── public.py
├── scripts/create_local_tables.py
└── tests/
    ├── conftest.py
    ├── domains/<name>/         service-level, no HTTP
    ├── api/                    contract tests through ROOT A
    └── entrypoints/            one smoke test per entrypoint
```

`domains/<name>/router.py` is the only file in a domain that imports FastAPI. No
file in a domain imports from `entrypoints/`. The two composition roots are the
only places that assemble an application.

### Entrypoint shape

The canonical pattern from the package README, adapted:

```python
# app/entrypoints/content.py
from webbpulse.lambda_entry import run_uvicorn
from webbpulse.logging import configure_logging
from webbpulse.otel import configure_tracing

from app.composition.settings import settings
from app.domains.content.router import router


def build_app():
    from webbpulse.http import create_app
    return create_app(
        [router],
        title="WebbPulse Portfolio content",
        version=VERSION,
        service_name="webbpulse-portfolio-content",
        settings=settings,
        router_prefix="/api/v1",
        redirect_slashes=False,
    )


def main() -> None:
    configure_logging(level=settings.log_level, service=settings.service_name,
                      environment=settings.environment)
    configure_tracing(settings.service_name, environment=settings.environment)
    run_uvicorn(build_app())


if __name__ == "__main__":
    main()
```

`configure_logging` is keyword-only, there is no positional level.
`configure_tracing` returns a bool and no-ops when the SDK is absent or
`WEBBPULSE_OTEL_DISABLED` is set. `run_uvicorn` blocks, passes `log_config=None`
so uvicorn does not install its own handlers, and defaults `access_log=False`.

### Local development and tests

Root A keeps the whole surface in one process, so `docker-compose.yml`,
`scripts/create_local_tables.py` and the 3,914 lines of existing tests keep
working with an import change. The split of the test suite:

- Tests that drive HTTP through `TestClient` move to `tests/api/` and run
  against root A, so they keep proving the whole public contract in one process.
- Tests for `Repository`, the serializer, settings and security move to the
  shared package's own suite, or are deleted here once the package owns the code.
- What is left becomes per-domain service tests under `tests/domains/`.
- `tests/entrypoints/` is new and small but load-bearing: it asserts each
  entrypoint exposes exactly its own routes and no others, which is what stops a
  domain quietly re-acquiring the whole router after a refactor.

The package ships a pytest plugin. Enable it with
`pytest_plugins = ["webbpulse.testing"]` in `conftest.py` for the `moto`
fixtures, the `rate_limit_table` fixture, and the `test_client` factory. That
factory takes `source_ip` and `payload_format` and calls
`make_request_context_headers`, which is how a test exercises the request-context
path the rate limiter reads in production.

### One Dockerfile, parameterised

One Dockerfile with a `DOMAIN` build arg, built once per domain. The alternative,
one image built once and tagged into four repositories with `DOMAIN` as a runtime
variable, is cheaper to build but means all four functions run identical bytes
and differ only by an environment variable, which loses the per-domain dependency
trimming and makes an image's contents ambiguous. Build per domain; the layers
are shared anyway, which is the point the `ecr-repository` README makes about
storage cost.

```dockerfile
# syntax=docker/dockerfile:1.7
ARG BASE_IMAGE=<artifacts-account>.dkr.ecr.us-west-2.amazonaws.com/webbpulse/python-lambda-base:<tag>
FROM ${BASE_IMAGE} AS base

ARG DOMAIN
ENV DOMAIN=${DOMAIN}

COPY app/ /var/task/app/

ENV PYTHONPATH=/var/task \
    PYTHONUNBUFFERED=1 \
    AWS_LWA_PORT=8080 \
    AWS_LWA_READINESS_CHECK_PATH=/health \
    AWS_LWA_ASYNC_INIT=true

WORKDIR /var/task
CMD ["sh", "-c", "exec python -m app.entrypoints.${DOMAIN}"]
```

The adapter copy line, when the base image does not already carry it:

```dockerfile
COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:1.0.1 \
     /lambda-adapter /opt/extensions/lambda-adapter
```

`1.0.1` is both the latest adapter release and the version the shared package
pins and exposes as `webbpulse.lambda_entry.ADAPTER_IMAGE`. Three things about
that line, all verified against the adapter's own documentation
(https://github.com/awslabs/aws-lambda-web-adapter):

- **There is no architecture-specific tag.** The container image is multi-arch,
  and the identical `COPY` line serves both arm64 and x86_64. Only the Zip layer
  form splits by architecture (`LambdaAdapterLayerX86` versus
  `LambdaAdapterLayerArm64`), and that form is not in use here.
- **The source path is `/lambda-adapter`**, at the image root, not a layer path.
- **The destination must be `/opt/extensions/lambda-adapter`**, because Lambda
  only starts extension binaries from `/opt/extensions`.

Four details that are load-bearing rather than decorative:

- **`AWS_LWA_READINESS_CHECK_PATH=/health` must point at a route that does no
  I/O.** The adapter polls it on every cold start. The package's `health_router`
  is liveness-only for exactly this reason, and `instrument_fastapi` excludes
  `health` and `ready` from tracing to match.
- **`AWS_LWA_ASYNC_INIT=true`** moves slow imports into Lambda's 10 second init
  window, which matters more with four cold paths than with one.
- **`PYTHONUNBUFFERED=1`** stops log lines sitting in the buffer between invokes.
- **The CodeArtifact token must be a BuildKit secret mount**, never a build arg
  or `ENV`. Both persist in `docker history`. The package README's snippet uses
  `--mount=type=secret,id=codeartifact_token` and that is the shape to copy.

### Base image, and the assumption to state

The plan assumes an ECR repository `webbpulse/python-lambda-base` in the
Artifacts account, holding an image built `FROM
public.ecr.aws/docker/library/python:3.13-slim` with the adapter binary copied in
and the shared package's pinned dependency set installed to `/var/task`.

Three assumptions, all of which need confirming before the Dockerfile PR lands,
because none of them is verifiable from this repository:

1. **The tag.** Assume an immutable `sha-<commit>` tag from the Artifacts repo
   build, not `latest`, matching the `sha-` prefix convention the
   `ecr-repository` module's `tag_prefix_list` defaults to. Portfolio pins one
   digest and bumps it deliberately.
2. **The architecture.** Portfolio builds `arm64` today
   (`architectures = ["arm64"]` in `terraform/lambda.tf`) and CarModPicker builds
   `x86_64`. A shared base must therefore be a multi-architecture manifest, or
   the two applications cannot share it. Note that the `container-image.yml`
   workflow deliberately refuses a multi-arch *application* image, because Lambda
   rejects an OCI index; that constraint is on the image Lambda pulls, not on the
   base it is built `FROM`. Portfolio's build stays single-platform `linux/arm64`.
3. **Cross-account pull, and the distinction that matters.** The base lives in
   the Artifacts account and is pulled at *build* time by CI in the app account,
   never at runtime by Lambda. Lambda only ever pulls the per-domain images, and
   those are same-account. So the base repository needs a policy granting the CI
   principals in the two Portfolio accounts, and it does **not** need the
   `LambdaECRImageCrossAccountRetrievalPolicy` service-principal statement.
   This distinction is worth stating because getting it backwards is a delayed
   failure rather than an immediate one: for an image Lambda genuinely does pull
   cross-account, the service-principal statement naming `lambda.amazonaws.com`
   is **not optional**, since Lambda re-fetches the image for optimization and
   caching after the initial create. A repository policy that grants only the
   consuming account works at create time and then breaks weeks later when the
   function goes `Inactive` and cannot re-fetch. The `ecr-repository` module
   writes both statements together for exactly this reason, and it is the correct
   pairing to keep if a cross-account runtime pull is ever introduced.

**Image size.** The dominant term is the dependency layer, shared across all four
domains as long as every domain image is built `FROM` the same base with the same
install. Give each domain a trimmed dependency set and the layers stop being
bit-identical and storage roughly triples. Build all four from one shared
dependency layer. Lambda's limit is 10 GB uncompressed including all layers
(https://docs.aws.amazon.com/lambda/latest/dg/images-create.html), which this is
nowhere near; the reason to care is cold start, not the ceiling.

**Two container-image lifecycle facts worth designing around**, both from the
same page. First, **Lambda resolves the image tag to a digest at deploy time and
does not follow the tag afterwards**, so pushing a new image to an existing tag
deploys nothing until `UpdateFunctionCode` is called. With immutable `sha-`
tags this cannot bite, which is a second reason to keep `IMMUTABLE` on. Second,
**a function left uninvoked for several weeks goes `Inactive`**, and the first
invoke after that is rejected while Lambda re-optimizes the image. Four
low-traffic functions on staging is exactly the shape that hits this, so the
first request after a quiet period can fail for reasons that have nothing to do
with the code. If the underlying image has been deleted or the pull permissions
revoked in the meantime, the function goes `Failed` instead and does not recover.
The lifecycle rule keeping the last ten tagged images is what stops a
long-running production function's image being expired out from under it.

## 3. Terraform changes, in order

All in `WebbPulse-Portfolio/terraform/`. `<prefix>` stays `webbpulse-<env>`,
built by `local.prefix` in `locals.tf` as `"${local.project}-${var.environment}"`.

### 3.1 ECR repositories, one per domain per environment

New file `terraform/ecr.tf`. One module call per environment root, four
repositories.

```hcl
module "registry" {
  source  = "app.terraform.io/WebbPulse/platform-modules/aws//modules/ecr-repository"
  version = "~> 2.0"

  name_prefix = local.prefix

  repositories = {
    content  = {}
    resume   = {}
    identity = {}
    public   = {}
  }
}
```

That yields `webbpulse-staging/content` and so on, with the module defaults:
`IMMUTABLE` tags, `scan_on_push = true`, keep the last 10 tagged images, expire
untagged after 1 day, `tagPrefixList = ["sha-"]`, `AES256`. All four defaults are
right here and none needs overriding.

**Leave `repository_policy_principals` empty.** Section "Lambda, and why there is
no repository policy by default" in the module README is explicit: same-account
access needs only one side to grant it, and Lambda writes the
`LambdaECRImageRetrievalPolicy` statement onto the repository itself at
`CreateFunction`, provided the caller holds `ecr:GetRepositoryPolicy` and
`ecr:SetRepositoryPolicy`. Setting the input would make Terraform own the whole
document and drop that statement on the next apply. The repository and the
function must be in the same region, which they are.

Expected plan: 4 `aws_ecr_repository` plus 4 `aws_ecr_lifecycle_policy`,
**8 to add, 0 to change, 0 to destroy**, and no `aws_ecr_repository_policy`.

### 3.2 Deploy role additions

`terraform/iam_github_actions.tf`, in the `policy_statements` list passed to
`github-actions-role`. Four additions and one deletion.

```hcl
# ECR: push domain images
{
  actions   = ["ecr:GetAuthorizationToken"]
  resources = ["*"]   # takes no resource
},
{
  actions = [
    "ecr:BatchCheckLayerAvailability",
    "ecr:InitiateLayerUpload",
    "ecr:UploadLayerPart",
    "ecr:CompleteLayerUpload",
    "ecr:PutImage",
    "ecr:BatchGetImage",           # the workflow's manifest assertion
    "ecr:GetDownloadUrlForLayer",
    "ecr:GetRepositoryPolicy",     # so Lambda can write the retrieval statement
    "ecr:SetRepositoryPolicy",
  ]
  resources = module.registry.repository_arns_list
},
# CodeArtifact: read the shared package during the image build
{
  actions   = ["sts:GetServiceBearerToken"]
  resources = ["*"]
},
{
  actions   = ["codeartifact:GetAuthorizationToken"]
  resources = [<the webbpulse domain ARN in the Artifacts account>]
},
{
  actions   = ["codeartifact:ReadFromRepository"]
  resources = [<the python repository ARN>]
},
```

The Lambda statement's `resources` becomes the list of four function ARNs
instead of the single `module.lambda_api.function_arn`. The S3 artifact statement
naming `module.lambda_artifacts.bucket_arn` is deleted with the bucket.

`sts:GetServiceBearerToken` is the one to not miss. Without it the CodeArtifact
login fails with an access denied that names no CodeArtifact action.
`ecr:GetAuthorizationToken` and `sts:GetServiceBearerToken` both take `"*"`.

### 3.3 Lambda functions, and the bootstrap order

`terraform/lambda.tf` becomes a `for_each` over the four domains. Deleted:
`module.lambda_artifacts`, `data.archive_file.lambda_placeholder`, and the
`archive` provider from `versions.tf`.

```hcl
locals {
  domains = {
    content  = { secrets = true,  memory = 512 }
    resume   = { secrets = true,  memory = 512 }
    identity = { secrets = true,  memory = 512 }
    public   = { secrets = false, memory = 256 }
  }
}

module "lambda_api" {
  for_each = local.domains

  source  = "app.terraform.io/WebbPulse/platform-modules/aws//modules/lambda-function"
  version = "~> 2.0"

  function_name = "${local.prefix}-${each.key}"
  role_name     = "${local.prefix}-${each.key}-lambda"

  package_type  = "Image"
  runtime       = null      # must be null for Image
  handler       = null      # must be null for Image
  architectures = ["arm64"]
  memory_size   = each.value.memory
  timeout       = 15

  code = {
    image_uri = "${module.registry.repository_urls[each.key]}:${var.bootstrap_image_tag}"
  }

  environment_variables = merge({
    DYNAMODB_TABLE_PREFIX = local.prefix
    ENVIRONMENT           = var.environment
    SERVICE_NAME          = "webbpulse-portfolio-${each.key}"
    CORS_ALLOW_ORIGINS    = local.cors_origins
    SITE_URL              = local.frontend_url
    LOG_LEVEL             = "INFO"
  }, each.value.secrets ? { APP_SECRETS_ARN = module.app_secrets.arns["app"] } : {})

  log_retention_days           = 7
  log_format                   = "JSON"
  application_log_level        = "INFO"
  system_log_level             = "INFO"
  set_logging_config_log_group = true

  attach_xray_write_policy = true
}
```

`runtime` and `handler` must be null: the module validates
`var.package_type == "Image" ? var.runtime == null : var.runtime != null`. The
`code` variable validates that `image_uri` and `package_type = "Image"` go
together. `image_uri` is already in the module's `ignore_changes` list, so a CI
`UpdateFunctionCode` is not undone by the next plan.

The environment variable names change to the ones the shared package reads:
`ENVIRONMENT`, `SERVICE_NAME`, `LOG_LEVEL`, `CORS_ALLOW_ORIGINS`,
`APP_SECRETS_ARN`, `DYNAMODB_TABLE_PREFIX`. The two `POWERTOOLS_*` variables go
away with Powertools. Note the rename: today's `CORS_ORIGINS` becomes
`CORS_ALLOW_ORIGINS`.

**The chicken and egg.** The image must exist in ECR before the apply that
creates the function. This is stated directly by
https://docs.aws.amazon.com/lambda/latest/dg/images-create.html: "Before you
create a Lambda function from a container image, you must build the image
locally and upload it to an Amazon ECR repository." Lambda pulls and optimizes
the image at create time, so an `ImageUri` that does not resolve fails the
create. Three options:

1. A CI job that builds and pushes before the Terraform apply.
2. A placeholder image pushed once by hand.
3. A `bootstrap_image_tag` variable, defaulted to a tag CI has already pushed.

**Recommend option 1, with the repositories landing in their own earlier PR.**
The sequence is: PR creates the four ECR repositories and applies (nothing
depends on an image); CI builds and pushes all four domain images on the next
push to `staging`, tagged `sha-<commit>`; the PR that adds the functions passes
that tag through `var.bootstrap_image_tag`. This needs no placeholder, no manual
push, and no `MUTABLE` repository. The `image_uri` in state is only ever the seed
value, because the module ignores changes to it afterwards, so the variable does
not need updating again.

Option 2 is the fallback if the ordering proves awkward, but a placeholder image
that answers 503 is a real image somebody has to build and push, and it can be
left behind in a repository whose lifecycle rule then counts it against the ten
retained tags.

### 3.4 IAM, per domain

The single `aws_iam_role_policy.lambda_api` becomes a `for_each` over the same
map. Each function gets its own log group statement, the X-Ray statement (or the
module's `attach_xray_write_policy`, not both), a DynamoDB statement scoped to
the tables in its column of the section 1 table, and the app secret statement
only when `each.value.secrets`.

`public` is the one that matters: no `secretsmanager:GetSecretValue` at all, and
DynamoDB limited to `GetItem`, `Query` and `Scan` on the `posts` and
`site-content` tables plus the `published-index` GSI. That is the clearest
least-privilege win in the whole split, and it only works if the settings class
does not require the four secret fields at import. `config.py` today ends in a
module-level `settings = Settings()` whose `resolve_secrets` validator raises
when `SECRET_KEY`, `ADMIN_USERNAME`, `ADMIN_PASSWORD` or `ADMIN_EMAIL` is still
`None`. The package's `BaseServiceSettings` has no such requirement, so the
Portfolio subclass declares the four as optional and only the domains that need
them assert their presence.

### 3.5 API Gateway routes, one prefix at a time

`terraform/apigateway.tf`. The module call already has the right shape; the
`integrations` map grows from one entry to five and `routes` grows one prefix at
a time. `default_integration` flips from `null` to `"legacy"` on the first
strangler step, because the monolith has to hold everything not yet carved out.

```hcl
integrations = merge(
  {
    legacy = {
      lambda_function_name           = module.lambda_monolith.function_name
      lambda_invoke_arn              = module.lambda_monolith.invoke_arn
      lambda_permission_statement_id = "AllowAPIGatewayInvoke"
    }
  },
  {
    for k, m in module.lambda_api : k => {
      lambda_function_name = m.function_name
      lambda_invoke_arn    = m.invoke_arn
    }
  },
)

default_integration = "legacy"

routes = {
  # public, first cut
  "GET /health"      = { integration = "public" }
  "GET /"            = { integration = "public" }
  "GET /sitemap.xml" = { integration = "public" }
  "GET /robots.txt"  = { integration = "public" }

  # resume, second cut. Two keys per collection.
  "ANY /api/v1/projects"           = { integration = "resume" }
  "ANY /api/v1/projects/{proxy+}"  = { integration = "resume" }
  # ... same pair for experience, skills, education, certifications

  # content, third cut
  "ANY /api/v1/posts"                 = { integration = "content" }
  "ANY /api/v1/posts/{proxy+}"        = { integration = "content" }
  "ANY /api/v1/site-content"          = { integration = "content" }
  "ANY /api/v1/site-content/{proxy+}" = { integration = "content" }

  # identity, last
  "ANY /api/v1/admin"          = { integration = "identity" }
  "ANY /api/v1/admin/{proxy+}" = { integration = "identity" }
}
```

Two things the module's own variable documentation makes explicit and that are
easy to get wrong:

- **Two keys per collection.** `"ANY /api/v1/posts"` does not match
  `/api/v1/posts/123`, and `"ANY /api/v1/posts/{proxy+}"` does not match the bare
  collection path. Both are needed to carve a prefix off the monolith cleanly.
  Portfolio's collection GETs carry a trailing slash and item routes do not, so
  both forms are genuinely in use.
- **Do not list `$default` in `routes`.** The module validates against it and
  refuses. Name the integration that serves it with `default_integration`, so the
  access gate's authorizer reaches it the same way it reaches every other route.

**The strangler works because of a documented precedence order**, not because of
an implementation detail. From
https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-develop-routes.html,
API Gateway selects the most specific match in three tiers: a full match for
route and method first, then a match with a greedy path variable (`{proxy+}`),
then `$default` last. The doc states the consequence outright: "Routes with
greedy path variables have higher priority than the `$default` route." So each
`ANY /api/v1/<prefix>/{proxy+}` key added below reliably peels its prefix off the
monolith, and everything not yet carved out keeps falling through to `$default`.
That is the whole mechanism. Because `/api/v1/posts/{proxy+}` all lands on one
function, FastAPI keeps resolving `categories` and `admin` ahead of `{slug}`
internally and the gateway never has to break that tie.

The quota is 300 routes per HTTP API (L-65B5C802, adjustable). The full split
uses about 20, so it is not a constraint here.

**The access gate keeps working by construction.** The authorizer attaches at the
route level and the module applies `var.authorizer_id` uniformly to every route
it creates, so each new per-prefix route inherits the same REQUEST authorizer.
The `routes` entries above deliberately set no `authorization_type`, which means
the module's own choice: `CUSTOM` when `authorizer_id` is set. Setting it to
`NONE` anywhere punches a hole straight past the gate. `disable_execute_api_endpoint`
must stay `true`.

`access_log_retention_days` goes 30 to 7 in the same file.

### 3.6 Alarms

`terraform/monitoring.tf`. The log-based alarm generalises for free, because
`error_log_groups` is already a map and every filter publishes to one shared
metric with no dimensions, so four log groups still means one alarm:

```hcl
error_log_groups = {
  for k, m in module.lambda_api : k => m.log_group_name
}
```

The two metric alarms do not generalise. `api-alarms` takes a single
`lambda_function_name` string feeding the `FunctionName` dimension. Options:

1. Add `lambda_aggregate_alarm` and its threshold, period and evaluation inputs
   to `api-alarms`, mirroring the `dynamodb_aggregate_*` set that already exists
   there. One alarm on `AWS/Lambda` `Errors` with no `FunctionName` dimension
   covers every function in the account and picks up new ones without a change.
2. Call `api-alarms` once per function. Four times the alarms, four times the
   billable alarm metrics, and it contradicts the bucketed-alarm decision.

**Recommend option 1.** It matches the shape already proven by
`dynamodb_aggregate_alarm` in the same module, it is the only remaining module
work, and it is small. The caveat, which the aggregate DynamoDB alarm shares, is
that an account-wide dimensionless alarm also catches the access gate's authorizer
Lambda and the CloudFront function, so the threshold is a per-environment
judgement rather than a copy of the per-function one. This is the alarm question
in section 9.

Until that lands, keep `lambda_function_name` pointed at the monolith: it is the
function still serving `$default` and therefore still the one whose errors matter
most.

### 3.7 The rate-limits table

`terraform/dynamodb.tf`. One entry added to `local.dynamodb_tables`, no module
change. The shared package's `RATE_LIMIT_TABLE` is `rate-limits` and its
`TTL_ATTRIBUTE` is `expires_at`, which differs from the `ttl` the `meta` table
uses today, so the table declaration must match the package rather than `meta`:

```hcl
"rate-limits" = {
  hash_key               = "pk"
  attributes             = [{ name = "pk", type = "S" }]
  ttl_attribute          = "expires_at"
  point_in_time_recovery = false
}
```

`table_name` in the package is `<prefix>-<logical>`, matching
`local.prefix`, so the table is `webbpulse-<env>-rate-limits` and
`DYNAMODB_TABLE_PREFIX` already carries the prefix.

## 4. CI and CD

### Per-domain jobs

`deploy-backend.yml` becomes a caller of the org reusable workflows. All three
are tagged `v1` in `WebbPulse/.github`.

```yaml
jobs:
  build:
    strategy:
      matrix:
        domain: [content, resume, identity, public]
    permissions:
      contents: read
      id-token: write
    uses: WebbPulse/.github/.github/workflows/container-image.yml@v1
    with:
      ecr-repository: webbpulse-${{ ... }}/${{ matrix.domain }}
      aws-region: us-west-2
      context: backend
      dockerfile: backend/Dockerfile
      platform: linux/arm64
      build-args: |
        DOMAIN=${{ matrix.domain }}
    secrets:
      role-to-assume: ${{ vars.AWS_DEPLOY_ROLE_ARN }}

  deploy:
    needs: build
    permissions:
      contents: read
      id-token: write
    uses: WebbPulse/.github/.github/workflows/lambda-image-deploy.yml@v1
    with:
      aws-region: us-west-2
      function-image-map: <JSON of the four function names to digest-pinned URIs>
    secrets:
      role-to-assume: ${{ vars.AWS_DEPLOY_ROLE_ARN }}
      smoke-header: <the origin-verify header on staging>
```

`container-image.yml` outputs `image-uri` pinned by digest
(`registry/repo@sha256:...`), which is what `function-image-map` should carry.
`lambda-image-deploy.yml` already handles the N-function case: it resolves
targets from the map, calls `wait function-updated-v2` before and after each
`update-function-code`, and retries `ResourceConflictException` up to six times
with linear backoff. That directly addresses the deploy-versus-apply race the
inventory flagged as widening with N.

**The caller permissions trap.** Every job that calls one of these workflows must
declare `permissions: {contents: read, id-token: write}` on the calling job
itself. A called workflow cannot hold permissions wider than the caller's grant,
and a job-level `permissions` block replaces rather than merges with the
top-level one. Getting this wrong fails the run at startup, before any step, with
an error naming the permission rather than the missing credential. This is
documented in the org README as what broke the first CI run of `webbpulse-python`.

`test-backend.yml` becomes a caller of `python-ci.yml@v1`, passing
`codeartifact-domain: webbpulse`, `codeartifact-repository: python`,
`aws-region: us-west-2`, with `codeartifact-domain-owner` as a secret. That
workflow runs `ruff` rather than the current flake8, black and isort trio, so the
lint configuration converges in the same PR.

### Path filters

Today's filters are an allow list and the union across all four workflows is
`backend/**`, `frontend/**` and the workflow files themselves. Keep that shape.
Add `backend/Dockerfile` implicitly via `backend/**`. A change touching only
`docs/**` matches nothing, which is what makes this pull request deploy nothing.

Per-domain path filters, so that touching `domains/content/` rebuilds only
`content`, are tempting and should be resisted at first. The shared
`composition/` and `pyproject.toml` are inputs to every image, the matrix build
is cheap because the layers cache, and a partial rebuild means the four functions
can run different commits of the shared code. Build all four on any `backend/**`
change.

### Staging then main

Unchanged in shape: push to `staging` deploys staging, push to `main` deploys
production, both gated on the existing `STAGING_DEPLOY_ENABLED` variable and the
GitHub Environment. The HCP run poll stays; it polls the workspace rather than
any resource, so it generalises to four functions for free.

The **smoke test must probe one path per domain**. Today it probes only `/health`
in a ten-attempt loop and asserts the body reports `"database": "healthy"`.
During the strangler the monolith answers `$default`, so `/health` passes whether
or not a newly split domain works. That is false confidence at exactly the moment
it matters. `lambda-image-deploy.yml` takes a single `smoke-url`, so the
per-domain probes go in a step after it, or the workflow is called once per
domain with its own `smoke-url`.

### Image promotion between staging and prod

Two options.

**Rebuild per environment.** Each environment's CI builds from the same commit
and pushes to that account's own repositories. Simple, no cross-account trust,
and it fits the existing shape where `staging` and `main` are separate pushes
into separate accounts. The cost is that the bytes production runs were never the
bytes staging tested: a base image that moved, a transitive dependency that
resolved differently, or a non-reproducible build step makes them differ silently.

**Cross-account copy.** Build once on `staging`, then pull and re-push the same
digest into the production account's repository on promotion. Production runs
exactly the tested bytes. The cost is a cross-account pull policy on the staging
repositories naming the production account, a promotion job that does the copy,
and the fact that ECR has no server-side copy so the job pulls and pushes the
whole image.

**Recommend rebuild per environment for the pilot, and revisit.** Three reasons.
The `container-image.yml` workflow tags by `sha-<full git sha>`, so the same
commit produces the same tag in both accounts and the provenance question is
answerable without the copy. The `ecr-repository` module's defaults create
same-account repositories with no repository policy, which is the configuration
its README documents as correct; adding a cross-account policy is a deliberate
step away from that. And the pilot's purpose is to prove the split, not to prove
the promotion pipeline, so the simpler option keeps the variables down.

The reason to revisit is real, though, and it is the reproducibility gap. The
mitigation that makes rebuild honest is pinning: pin the base image by digest,
pin `webbpulse` to an exact version rather than a range, and keep a lockfile. If
those three hold, a rebuild from the same commit is reproducible in practice and
the copy buys little. If any of them slips, switch to cross-account copy.

## 5. Observability

### Tracing

`configure_tracing(service_name, environment=..., ...)` from
`webbpulse.otel`, called once in each entrypoint's `main()`. It exports OTLP over
HTTP to X-Ray, deriving the endpoint from the region, and instruments botocore.
`instrument_fastapi` is called by `create_app` when `instrument=True`, and
excludes `health` and `ready` by default.

Two things it needs from the environment, both documented in the package but not
read by it, so Terraform must set them:

- `OTEL_EXPORTER_OTLP_TRACES_PROTOCOL=http/protobuf`. There is no gRPC listener.
- `OTEL_PYTHON_DISTRO=aws_distro` and `OTEL_PYTHON_CONFIGURATOR=aws_configurator`,
  which is what makes the ADOT distro sign the request with SigV4. `configure_tracing`
  warns loudly if the endpoint looks like the X-Ray OTLP endpoint and
  `amazon.opentelemetry.distro` is not importable, because the failure otherwise
  is a 403 at export time rather than at start-up.

For IAM, use the module's `attach_xray_write_policy = true` rather than a hand
written statement, and drop the `xray:PutTraceSegments` statement from the
per-domain inline policy. Today's `lambda.tf` sets it to `false` precisely
because the inline policy duplicated it; with the policy being rewritten per
domain anyway, letting the module own it is one less thing to keep in sync. It
grants only when `tracing_mode` is `Active`, which is the module default.

Sampling is deliberately not overridden by the package. `OTEL_TRACES_SAMPLER`
and `OTEL_TRACES_SAMPLER_ARG` are the knobs, and the right value is a judgement
call: a low rate on low-traffic staging can leave an incident with no trace at
all. See section 9.

### Logging

`configure_logging(level=..., service=..., environment=...)`, keyword-only,
called before `configure_tracing` in each entrypoint. It replaces the root
handlers rather than appending, which removes Lambda's own handler, and it
reattaches `uvicorn`, `uvicorn.error` and `uvicorn.access` to root. The emitted
record carries `timestamp`, `level`, `message`, `logger`, the static service and
environment fields, and `trace_id` and `span_id` when a span is active. That
last pair is what preserves the log-to-trace join that Powertools'
`inject_lambda_context` provides today.

The `level` field is what the alarm depends on: `api-alarms` defaults
`error_filter_pattern` to `{ $.level = "ERROR" }`, and a JSON filter pattern only
matches events that parse as JSON. `log_format = "JSON"` stays set on every
function for the same reason it is set today.

### Removing Sentry

There is no Sentry in this repository. `grep` for `sentry` across `backend/`
returns nothing, and `requirements.txt` carries no Sentry SDK. The observability
stack to remove is **AWS Lambda Powertools**, which goes domain by domain: each
entrypoint that switches to `configure_logging` drops its `app/core/logging.py`
import, and the `POWERTOOLS_SERVICE_NAME` and `POWERTOOLS_METRICS_NAMESPACE`
environment variables come out of `lambda.tf` with it. `app/lambda_handler.py`,
which is Mangum plus the Powertools `inject_lambda_context` decorator, is deleted
outright when the last domain moves, along with `mangum` from the dependencies.

### What stays on the monolith until it is gone

The monolith keeps Powertools, its Mangum handler, its 30-day log retention if
changing it would churn the group, and the `lambda_function_name` alarm pair
pointed at it. It is serving `$default` and therefore every route not yet carved
out, so it stays the most important function to alarm on until the last cut.
Nothing about it changes until section 6's final step.

## 6. Cutover sequence

### First domain: `public`

Recommend `public`, not `content`. Four reasons:

1. **It has the least to lose.** Four routes, none authenticated, none writing.
   A regression is a broken sitemap or a health check, not a lost post or a
   failed login.
2. **It proves the hardest IAM claim.** `public` is the domain with no Secrets
   Manager access and read-only DynamoDB. If the settings refactor is wrong, or
   `SeedMiddleware` is wired in by accident, `public` fails immediately and
   loudly on its first request. Every other domain would mask that failure by
   having the permissions to succeed anyway.
3. **Its routes are literal, so the gateway change is trivial.**
   `GET /health`, `GET /`, `GET /sitemap.xml`, `GET /robots.txt` are four exact
   route keys with no `{proxy+}` and no collection-versus-item pair to get wrong.
4. **`/health` is what the smoke test already probes**, so the existing CI gate
   becomes meaningful on the very first cut instead of continuing to pass
   vacuously.

`content` is the wrong first choice for the mirror-image reason: it is the domain
with the `/posts` literal siblings, the one place where route ordering is
genuinely subtle. Cut it third, once the pattern is proven.

Order: `public`, `resume`, `content`, `identity`. Auth moves last, when a
rollback is still one revert and when every other domain has already proven the
image, the adapter, the settings and the IAM shape.

### Verifying a route flip on staging

The staging access gate makes a bare `curl` return the Cognito redirect rather
than the API response, so a check needs one of the two things the authorizer
admits. It admits an `OPTIONS` preflight, a matching `x-origin-verify` header, or
valid CloudFront signed cookies.

Use the header. It is what `deploy-backend.yml` already does and it needs no
browser:

```bash
VALUE=$(aws ssm get-parameter --with-decryption \
  --name /webbpulse-staging/access-gate/origin-verify \
  --query Parameter.Value --output text)

curl -sS -o /dev/null -w '%{http_code}\n' \
  -H "x-origin-verify: $VALUE" \
  https://api.staging.webbpulse.com/health
```

The deploy role already holds `ssm:GetParameter` on that parameter and
`kms:Decrypt` on the SSM key, granted conditionally in
`terraform/iam_github_actions.tf` when the gate is enabled. Mask the value in CI
with `::add-mask::`, which the current workflow does.

Three checks per flip, beyond a 200:

- **The route reached the new function.** Read the HTTP API access log:
  `routeKey` shows which route matched, and the log format already includes it.
  A request that fell through to `$default` shows `$default` there, not the
  explicit key, which is the difference between a working flip and a flip that
  silently did nothing.
- **The trailing-slash pair both work.** `GET /api/v1/projects/` and
  `GET /api/v1/projects?featured_only=true/` are both real URLs the frontend
  emits. They are the first thing to break if the routing layer normalises.
- **The authorizer still applies.** A request with no header and no cookies must
  not return 200. If it does, that route was created with
  `authorization_type = NONE` and is an open hole past the gate.

### Rollback

Remove the domain's entries from the `routes` map and apply. `$default` sends the
prefix back to the monolith, which still has every route because nothing is
deleted from it until the final step. That is the whole rollback: one map edit,
one apply, no image change, no function change, no data migration. It is why the
monolith keeps serving every route through the entire strangler rather than being
trimmed as each domain moves.

The rollback for a bad image, as opposed to a bad route, is
`aws lambda update-function-code --image-uri` pointing at the previous
`sha-<commit>` tag, which the repository still holds because the lifecycle rule
keeps the last ten.

### Retiring the monolith

Only after all four domains have been serving their prefixes on production long
enough to trust. Then, in one PR:

1. Set `default_integration = null`, which is where Portfolio is today and what
   the module supports. The API then answers 404 for anything the explicit routes
   do not match, which is the correct behaviour once the routes are exhaustive.
2. Delete the `legacy` integration, `module.lambda_monolith`, and its IAM policy.
3. Delete `backend/app/main.py`, `backend/app/lambda_handler.py`,
   `backend/app/api/v1/api.py` and `backend/scripts/build_lambda.sh`.
4. Drop `mangum` and `aws-lambda-powertools` from the dependencies.

Before that PR, confirm the routes are genuinely exhaustive: every one of the 44
application routes appears in the `routes` map under some prefix. The four
documentation routes are the ones to decide about deliberately, because
`/docs`, `/redoc` and `/openapi.json` are served by whichever app declares them,
and after the split each domain has its own. Either route them to one domain or
accept four separate schema documents. That is the retirement question in
section 9.

## 7. Data

**The tables stay exactly as they are.** No table is created, renamed, or
repartitioned by the split, and no data moves. The only new table is
`<prefix>-rate-limits`, which is new state rather than migrated state.

The repository layer is the seam. `backend/app/db/repository.py` is the generic
DynamoDB repository and `backend/app/db/entities.py` declares one instance per
table; after the split each `domains/<name>/repository.py` narrows to its own
tables and the generic base comes from `webbpulse.dynamodb.Repository`.

**Cross-domain table access exists and needs no tombstone or Streams pattern.**
Two couplings, both shared reads:

- `resume` reads the `site-content` singleton for `project_sort_mode`.
- `content`, `resume` and `identity` read `users` for admin authorisation.

Both are reads of a table with a single writer. `site-content` is written only by
`content`, `users` only by `identity`. There is no write that spans two domains,
so there is no consistency problem to solve, no tombstone to write, and no
DynamoDB Stream to consume. **Portfolio needs none of that pattern.** Saying so
explicitly matters because the pattern is expensive and the temptation to adopt
it pre-emptively is real.

The one shared-write table is `meta`, and it is shared infrastructure rather than
domain data: it holds the `COUNTER#<entity>` sequences and the
`UNIQUE#<entity>#<field>#<value>` lookup items that `Repository.create` writes
inside a `TransactWriteItems`. Each domain writes only the items for its own
entities, so the keys never collide even though the table is shared. That is safe
because the key space partitions by entity, not because of any coordination.

If a cross-domain write is ever introduced, it goes out as an event and is
consumed asynchronously. The structural expression of that rule is that no file
under `domains/<name>/` imports from `domains/<other>/`, asserted in
`tests/entrypoints/`.

## 8. Pull request list

Prerequisites that sit outside the sequence:

- **P1. `webbpulse` published to CodeArtifact.** The package has no git tags and
  has never been published. Someone tags `v0.1.0` in
  `WebbPulse/webbpulse-python` and lets `publish.yml` run. Nothing in this
  sequence past PR 3 can build without it. Not Portfolio's work, but on
  Portfolio's critical path.
- **P2. `webbpulse/python-lambda-base` built in the Artifacts account**, as a
  multi-architecture manifest, with a cross-account pull policy naming the two
  Portfolio accounts. Needed from PR 4.

| # | Scope | Expected plan | Depends on |
| --- | --- | --- | --- |
| 1 | This plan, docs only | none | none |
| 2 | Rewrite `client_ip()` against the request context the adapter forwards; move limiter items to `<prefix>-rate-limits`; add the fail-open wrapper and tests | none (code only) | none |
| 3 | Restructure `backend/app/` into four domain packages behind the existing app. No behaviour change, no infrastructure change | none | 2 |
| 4 | Add the two composition roots and the four entrypoints; the `BaseServiceSettings` subclass that does not require secrets; consume `webbpulse` | none | 3, P1 |
| 5 | `Dockerfile` with the `DOMAIN` build arg, adapter layer, local compose | none | 4, P2 |
| 6 | Terraform: four ECR repositories | **8 to add**, 0 change, 0 destroy | none |
| 7 | Terraform: deploy role gains ECR push, `Get`/`SetRepositoryPolicy`, and the CodeArtifact read statements | 1 to change (the inline policy) | 6 |
| 8 | CI: `test-backend.yml` calls `python-ci.yml@v1`; `deploy-backend.yml` gains the matrix `container-image.yml@v1` build. No deploy step yet, so the first images land in ECR | none | 5, 7 |
| 9 | Terraform: the four `package_type = "Image"` functions, per-domain IAM, the `rate-limits` table, 7-day retention. Monolith untouched and still holding every route | ~30 to add (4 functions, 4 roles, 4 policies, 4 log groups, 1 table), a few to change | 6, 8 |
| 10 | CI: `deploy-backend.yml` gains the `lambda-image-deploy.yml@v1` step with `function-image-map`, and per-domain smoke probes | none | 9 |
| 11 | `api-alarms` gains `lambda_aggregate_alarm` and its threshold, period and evaluation inputs | none (module repo) | none |
| 12 | Terraform: `error_log_groups` covers all five functions; switch to the aggregate Lambda alarm | ~4 to add, 2 to change | 9, 11 |
| 13 | **Cut 1.** Route `/health`, `/`, `/sitemap.xml`, `/robots.txt` to `public`; `default_integration` flips to `legacy` | 5 to add (4 routes + `$default`), 0 destroy | 10, 12 |
| 14 | **Cut 2.** Route the five resume prefixes, two keys each | 10 to add | 13 |
| 15 | **Cut 3.** Route the content prefixes, including the `/posts` literal siblings | 4 to add | 14 |
| 16 | **Cut 4.** Route `/api/v1/admin` to `identity` | 2 to add | 15 |
| 17 | Retire the monolith: `default_integration = null`, delete the `legacy` integration and function, delete `main.py`, `lambda_handler.py`, `api/v1/api.py`, `build_lambda.sh`, drop `mangum` and Powertools | ~10 to destroy | 16 |

PRs 2 and 6 are independent of everything and can start immediately. PR 11 is
independent and lands in the modules repository, so it can run in parallel with
the whole Portfolio spine. The serial spine is 3, 4, 5, then 9, then the four
cuts 13 through 16, one domain at a time so any regression is one revert away.

Plan counts are estimates from reading the module sources, not from a
speculative plan. Read the real plan on `staging` before applying; PR 6 in
particular should show exactly 8 to add and no `aws_ecr_repository_policy`, and
anything else means the name prefix or the encryption type is wrong.

## 9. Open questions

Only the ones where a real judgement call exists and the answer changes the plan.

1. **Base image contents.** Does `python-lambda-base` carry only the Python
   runtime and the adapter binary, or also the `webbpulse` package and its
   pinned dependency set? Carrying the dependencies makes Portfolio's build a
   ten-second source copy instead of a two-minute install, and gives one place to
   patch a CVE. It also couples every application's release to the base image's,
   and means a `webbpulse` bump is a base image rebuild rather than a
   `pyproject.toml` edit. This decides PR 5's Dockerfile and P2's scope.

2. **Aggregate Lambda alarm threshold.** A dimensionless `AWS/Lambda` `Errors`
   alarm catches every function in the account, including the access gate's
   authorizer and anything else added later. The per-function threshold today is
   0 with `GreaterThanThreshold`, meaning any single error alarms. Account-wide
   that is probably too sensitive on staging and about right on production.
   Should staging and production carry different thresholds, or should the alarm
   stay per-function for the four domains and accept eight billable alarm
   metrics?

3. **Trace sampling rate.** The package deliberately does not override
   `OTEL_TRACES_SAMPLER`. Portfolio's traffic is low enough that a percentage
   sampler can leave an incident with no trace at all, and high enough that
   always-on has a real cost across four functions. What rate, and does staging
   differ from production?

4. **The documentation routes after the split.** `/docs`, `/redoc` and
   `/openapi.json` are currently one schema for the whole API. After the split
   each of the four apps declares its own. Route them all to one domain and the
   schema is incomplete; leave them per-domain and there are four schema
   documents at four paths; disable them in the deployed entrypoints and keep
   them only on root A for local development. The third is probably right for a
   private API behind a gate, but it is a deliberate loss.

5. **Image promotion, revisited after the pilot.** Section 4 recommends rebuild
   per environment on the strength of pinning the base image by digest, pinning
   `webbpulse` exactly, and keeping a lockfile. If any of those three does not
   hold in practice, the recommendation flips to cross-account copy. Worth an
   explicit decision once the first production deploy has happened rather than
   now.

6. **Whether `identity` stays its own function.** One route, its own image, its
   own cold starts. The blast-radius argument for isolating the signing key is
   good and this plan follows it. The counter-argument is that a login that pays
   a container cold start is a login that feels slow, and folding `identity` into
   `content`, which already reads `users`, would remove that. Keeping it separate
   is the recommendation; it is listed here because it is the one domain-count
   decision that could reasonably go the other way, and PR 16 is the last moment
   to change it cheaply.

## PR 4 notes

What PR 4 built, and the four places it changed a fact this document asserted.
Everything not listed here held.

### Root A composes with `include_router`, not `mount_all`

Section 2 sketches root A as
`mount_all({"/api/v1/posts": posts_app, "/api/v1/projects": projects_app, ...})`.
That does not work here, for two reasons that were verified rather than
reasoned about:

- **Starlette strips a mount path.** `mount_all` fits when a domain's routers
  carry no prefix of their own and the mount path supplies it. Portfolio's carry
  theirs: `content` declares `/posts` and `/site-content`, `resume` declares
  five collection prefixes. One domain is therefore not one path, and mounting a
  router that already declares `/api/v1/posts` at the mount path `/api/v1/posts`
  404s everything, because the sub-application then sees
  `/api/v1/posts/api/v1/posts/...`.
- **A mounted sub-application contributes nothing to the parent's OpenAPI
  document.** The parent reports an empty `paths` map, which would take the
  monolith's published contract with it.

So the per-domain applications keep `router_prefix="/api/v1"`, which is what
makes each one's route set a literal subset of the monolith's, and both roots
include the same routers directly. `app/composition/app.py` carries the same
note at the point of use, and `tests/entrypoints/test_route_split.py` asserts
the two roots agree.

`mount_all` stays the right tool for a service whose domain routers are prefix
free. It is the shape, not the function, that does not fit Portfolio.

### Secrets stopped failing at import and started failing at use

The settings class ended in a validator that raised when `SECRET_KEY`,
`ADMIN_USERNAME`, `ADMIN_PASSWORD` or `ADMIN_EMAIL` was unset, and the module
ended in a bare `settings = Settings()`. Together those made importing anything
under `app/` fail without secrets, which the split cannot have: `public` is the
one function with no `secretsmanager:GetSecretValue` at all, so an import-time
read would fail it on every cold start before any route was reached.

The four are ordinary optional fields now, filled from the `APP_SECRETS_ARN`
blob on first read, and a domain that needs one calls
`settings.require_secrets(...)` and gets the same message the validator raised.
`Domain.requires_secrets` on the descriptor records which domain needs what, and
`public` names none, which is the least-privilege claim the split rests on.

### `identity` mounts at `/api/v1/admin`, and the prefix lives on the descriptor

`domains/identity/router.py` declares a bare `POST /login`. The `/admin` prefix
and the `admin` tag were left on the composition root by PR 3, so both roots have
to supply them. `create_app` takes a single `router_prefix` and no tags at all,
so routers are included by an explicit `include_router` loop after `create_app`
returns, with the prefix and tags read off `Domain`. That is what keeps the
operation ids and tags in a domain application identical to the monolith's
rather than merely similar.

### `public` keeps the database-reading `/health`; the other three get the shared one

`create_app` adds a liveness-only `GET /health` that does no I/O, which is what
`AWS_LWA_READINESS_CHECK_PATH` should point at: the adapter polls it on every
cold start, and a check that reads DynamoDB fails the function to start whenever
the table is briefly unavailable. Portfolio's own `/health` reads the
site-content singleton to report `database`, and the existing deploy smoke test
asserts on that field, so it has to survive. It stays on `public`, whose
application therefore sets `include_health=False`, and the other three get the
shared route. Section 6's first cut routes `GET /health` to `public`, which is
what keeps that smoke test meaningful.

### CI: PR 8's first item, pulled forward

`test-backend.yml` is now a caller of `python-ci.yml@v1`. That is PR 8's item on
the table in section 8, moved here because PR 4 is the change that makes it
necessary: `requirements.txt` pins `webbpulse`, which exists only in
CodeArtifact, and the old hand-written job could not install it. The alternative
was a hand-rolled login step that PR 8 would then delete.

Two things travelled with it:

- **Lint converged on ruff**, as section 4 anticipated. `pyproject.toml`
  configures `E`, `F` and `I`, which is the surface flake8 and isort already
  covered, and `.flake8` is gone. `B` and `UP` were deliberately left off:
  enabling them flags 196 findings across the existing tree, and `B008` flags
  FastAPI's own `Depends()` idiom on every route signature. `ruff format`
  reformatted 10 files, all of it nested-quote normalisation inside f-strings
  that black wrote differently.
- **The CI role moved to a repository variable.** `AWS_DEPLOY_ROLE_ARN` lives in
  the `staging` GitHub Environment, whose deployment branch policy admits only
  the `staging` branch, so a pull request job cannot read it. `CI_AWS_ROLE_ARN`
  and `CODEARTIFACT_DOMAIN_OWNER` are repository scoped, for the same reason
  `STAGING_DEPLOY_ENABLED` is. `CI_AWS_ROLE_ARN` names the same staging role and
  is used only to mint a read-only CodeArtifact token.

`deploy-backend.yml` needed the same access and got it differently: its AWS
credentials step already existed but ran *after* `build_lambda.sh`, which was
fine while every dependency came from PyPI. The credentials step and a
`codeartifact login` now run before the build. The build script itself is
unchanged.

### Note for PR 5

The base image is

```
432410731887.dkr.ecr.us-west-2.amazonaws.com/webbpulse/python-lambda-base@sha256:b5298b4b773ad6c9e311057cf5d43f37ceb98f0367347d714c6817f250a5cef7
```

Python 3.13 slim, Lambda Web Adapter 1.0.1 already at `/opt/extensions`, both
`amd64` and `arm64`, and no application dependencies. Pin it by digest, not by
tag. PR 4 deliberately writes no Dockerfile.

The CodeArtifact token that the image build needs must be a BuildKit secret
mount, `--mount=type=secret,id=codeartifact_token`. Not a build argument and not
an `ENV`: both persist in `docker history` for anyone who can pull the image.
