# Cutover log

What actually happened on each strangler cut, as against what
`pilot-split-plan.md` section 6 said would happen. The plan is the design and
does not change once a cut has landed; this file is the record, and it is where
a surprise gets written down so the next cut does not rediscover it.

One section per cut, in cut order: `public`, `resume`, `content`, `identity`.

## Cut 1: public

PR 13. Routes `GET /health`, `GET /`, `GET /sitemap.xml` and `GET /robots.txt`
to the `public` function, and moves the monolith from its two explicit route
keys onto `$default`.

### What changed

`terraform/apigateway.tf`, and nothing else in Terraform.

- `integrations` grows from one entry to two. `legacy` still names
  `module.lambda_api`, the monolith, and keeps its
  `lambda_permission_statement_id = "AllowAPIGatewayInvoke"` so its existing
  permission is not replaced. `public` is generated from
  `module.lambda_domain["public"]` through a new `local.routed_lambda_domains`.
- `default_integration` goes from `null` to `"legacy"`.
- `routes` loses `ANY /{proxy+}` and `ANY /` and gains the four `public` keys.
- `access_log_retention_days` goes 30 to 7, which section 3.5 puts in this file
  alongside the first cut.

### Expected plan

Roughly 5 to add and 2 to destroy, not the "5 to add, 0 destroy" section 8
row 13 estimates. The difference is real and is worth stating plainly, because
a reviewer who sees destroys on a cut should stop and read rather than assume
the estimate was right.

To add:

- 4 `aws_apigatewayv2_route`, one per `public` route key
- 1 `aws_apigatewayv2_route` for `$default`
- 1 `aws_apigatewayv2_integration` for `public`
- 1 `aws_lambda_permission` for `public`, whose statement id the module derives
  as `AllowAPIGatewayInvoke-public` because `public` is not the
  `default_integration`

To destroy:

- 2 `aws_apigatewayv2_route`, the monolith's `ANY /{proxy+}` and `ANY /`

To change:

- 1 `aws_cloudwatch_log_group`, the access log's retention

The two destroys are the whole point of the cut rather than a mistake. Section
3.5 says `default_integration` "flips from `null` to `"legacy"`", and Portfolio
had reached the module with `default_integration = null` and two explicit
monolith route keys precisely so that adopting the module planned zero add. Once
`$default` exists, those two keys are what `$default` now does, and the module
refuses to let `$default` be listed in `routes` at all. So the route keys have
to go. The monolith's coverage is unchanged across the apply: `ANY /{proxy+}`
and `$default` match the same requests, and API Gateway's documented precedence
puts an explicit route key above `{proxy+}` above `$default`, so the four
`public` keys peel off exactly their four paths and everything else still lands
on the monolith.

The `aws_apigatewayv2_route` resources are addressed by route key, so nothing
here renames an existing address. The monolith's integration and its permission
are untouched.

### Module shape, and where the plan's snippet does not match the repository

Section 3.5's snippet is written against module names this repository does not
use. It reads `module.lambda_monolith` for the monolith and `module.lambda_api`
for the domain functions. In the code as merged, `module.lambda_api` is the
monolith (`terraform/lambda.tf`) and the domain functions are
`module.lambda_domain`, a `for_each` over `local.lambda_domains`
(`terraform/lambda_domains.tf`, PR 9, merged as #102). The names are swapped
relative to the snippet. Anyone copying the snippet literally would point the
`legacy` integration at a domain function.

The snippet also generates all four domain integrations at once. That does not
plan: the module has a `check` block, `every_integration_is_routed`, which fails
on any integration no route and no `$default` can reach. Cut 1 routes only
`public`, so only `public` may appear in `integrations`. Hence
`local.routed_lambda_domains`, a list that grows by one name per cut and keeps
the integrations map and the routes map moving together by construction.

Two module behaviours worth knowing before the next cut:

- **`$default` is synthesised, not listed.** `var.routes` validates against a
  `$default` key and refuses it. The integration that serves it is named by
  `default_integration`, and the module builds the route itself so it cannot be
  created with different authorization by accident.
- **Authorization is decided once, for every route.** The module resolves
  `authorization_type` to `CUSTOM` whenever `authorizer_id` is set, and none of
  the four `public` entries overrides it. That is what keeps them behind the
  staging access gate. Setting `NONE` on any of them, including on `/health` to
  make a health check simpler, opens a hole past the gate.

### How a cut is verified

`scripts/verify_route_cut.sh <env> <domain>`.

A 200 does not prove a flip worked, because the monolith serves all four of
these paths too and would answer them identically through `$default`. So every
application now stamps an `X-WebbPulse-Domain` response header
(`backend/app/core/middleware.py`): a per-domain function reports its own name,
and both whole-surface roots, `app.main` and `app.composition.app`, report
`monolith`. The script asserts the header equals the domain being verified, and
reports `monolith` as "not cut over" rather than as a pass.

The header is the synchronous signal. The access log's `routeKey` field, in
`/aws/apigateway/webbpulse-<env>-api`, says the same thing and is the
cross-check when a response looks wrong: a request that fell through shows
`$default` there rather than the explicit key.

The script also runs section 6's third check, one request with no credential at
all, and fails if it returns 200. That catches a route created with
`authorization_type = NONE`, which is invisible to any check that always sends
the credential.

The staging gate credential is never embedded. The script takes
`WEBBPULSE_ORIGIN_VERIFY` (the header, which is what `deploy-backend.yml`
already reads from SSM and masks) or `WEBBPULSE_GATE_COOKIE` (a browser
session), and warns rather than silently failing when neither is set against
staging.

One boundary, found while testing rather than assumed: Starlette builds
`ServerErrorMiddleware` outside every user middleware, so the bare 500 it
synthesises for an *unhandled* exception carries no header. Handled errors and
404s do carry it. A test pins that behaviour so a future Starlette moving the
boundary fails the suite instead of quietly changing what the script can rely
on.

### Rollback

Delete the four `routes` entries and the `public` entry from
`routed_lambda_domains`, then apply. `$default` sends all four paths back to the
monolith, which still serves them because nothing has been deleted from it. No
image change, no function change, no data migration.

Reverting `default_integration` to `null` is not part of a rollback and should
not be done: it would leave the API answering 404 for everything, since the
monolith's two explicit route keys are gone. `$default` is the monolith's
coverage from this cut onward, until section 6's retirement step.

### Applied

Applied on staging 2026-09-07, HCP Terraform run `run-wkWvqnQhDMmeziYm`, from
PR #107. The plan calls this cut PR 13; #107 is the pull request that carried
it.

Verification is no longer a manual step. `deploy-backend.yml` gained a
`verify-route-cuts` job that runs `scripts/verify_route_cut.sh` after both the
monolith zip deploy and the domain image chain, so every backend deploy
re-checks that the four `public` paths are still answered by the `public`
function rather than having quietly fallen back to `$default`. The job reads
the same origin-verify parameter from SSM that the smoke test already reads and
masks it the same way; production needs no credential and the job sends no gate
header there.

The list of domains the job verifies lives in one `DOMAINS` variable in that
job. Cuts 2 through 4 each add one word to it.
## Cut 2: resume

PR 14. Routes the five resume collections, projects, experience, skills,
education and certifications, to the `resume` function. Status: **Applied on
staging, in two steps** (PR #110, then the correction PR below).

**The first apply errored, and the error is the lesson of this cut.** HCP run
`run-wejfhcFYu9riFnvc` created the `resume` integration, its permission and the
ten bare and `{proxy+}` routes, then failed on all five
`ANY /api/v1/<collection>/` keys with
`BadRequestException: Part of the given route key path is empty`. **API Gateway
HTTP API will not accept a route key whose path ends in a slash.** The
reasoning in "The route keys" below, written before the apply, was sound as a
reading of the documentation and wrong about the product; it is kept as
written, with this note, because the next person to reason about the trailing
slash will otherwise reach the same conclusion. The correction PR removes the
five keys so the workspace converges on 12 resources, changes the parsed
route test to model trailing-slash normalisation instead of the conservative
reading, and leaves both slash probes in the verify script so the gateway's
real behaviour is observed by CI on the next deploy rather than assumed.

### What changed

`terraform/apigateway.tf`, `scripts/verify_route_cut.sh` and one new test.

- `local.routed_lambda_domains` goes from `["public"]` to
  `["public", "resume"]`, which is what adds `resume` to the `integrations` map
  and, through the module, its `aws_lambda_permission`.
- A new `local.resume_collections` lists the five collections, and the `routes`
  map gains 15 keys generated from it. The map is now a `merge` of cut 1's four
  literal `public` keys and the generated `resume` block, so each further cut
  appends a block rather than editing the existing ones.
- `scripts/verify_route_cut.sh`'s `resume` case goes from empty to ten GET
  probe paths, both slash forms of all five collections.
- `backend/tests/entrypoints/test_gateway_routes.py` is new: it parses the
  route keys out of `apigateway.tf` and asserts they cover exactly the paths
  `build_domain_app("resume")` serves.

### The route keys, and why there were three per collection and not two (superseded, see above)

This is the one place cut 2 departs from section 3.5, and it is worth reading
before the next cut copies the pattern.

Section 3.5 gives each collection two keys, `ANY /api/v1/projects` and
`ANY /api/v1/projects/{proxy+}`. The paths this domain actually serves are
`/api/v1/projects/` and `/api/v1/projects/{item_id}`, because
`build_crud_router` in `backend/app/domains/resume/crud_router.py` declares its
collection operations at `/` and the router mounts under `/api/v1/projects`. So
the collection path carries a trailing slash, and **whether either of section
3.5's two keys matches it is undocumented**:

- The HTTP API routing documentation gives the precedence order (full match,
  then a greedy path variable, then `$default`) but has no trailing-slash or
  empty-remainder example anywhere, and says nothing about whether a trailing
  slash is normalised before route selection.
- Whether `{proxy+}` can capture an empty remainder is also unstated for HTTP
  APIs. The v1 REST API documentation describes `/parent/{proxy+}` as standing
  for `/parent/*`, which reads as requiring a non-empty remainder, but that
  sentence is not repeated for v2 and carrying it over is an inference rather
  than a documented fact.

Rather than depend on unspecified behaviour, each collection gets a third key,
the literal `ANY /api/v1/projects/`. A full match outranks a greedy one, so the
extra key is correct whichever way API Gateway actually behaves, and it is
harmless if AWS turns out to normalise the slash. Five collections times three
keys is 15.

The bare `ANY /api/v1/projects` is not redundant either. The frontend's
`getProjects(true)` emits `/projects?featured_only=true/`, whose path component
is the bare collection with the slash inside the query string
(`frontend/src/services/api.ts`), and `TrailingSlashMiddleware` is what makes
that reach the handler once the request has arrived at the function.

`ANY` rather than a method per route: the domain owns every method on these
prefixes, so `ANY` expresses the 25 routes in 15 keys instead of 75, cannot
drift when an operation is added to `build_crud_router`, and keeps an
unsupported method answering from the domain's own 405 rather than from the
monolith.

### Plan

Not yet applied. The speculative plan on the PR confirms 17 to add, 0 to
change, 0 to destroy:

- 15 `aws_apigatewayv2_route`, one per generated `resume` route key
- 1 `aws_apigatewayv2_integration` for `resume`
- 1 `aws_lambda_permission` for `resume`, whose statement id the module derives
  as `AllowAPIGatewayInvoke-resume` because `resume` is not the
  `default_integration`

Every one of the 15 routes plans with `authorization_type = CUSTOM` and the
same authorizer id the existing `$default`, `GET /`, `GET /health`,
`GET /robots.txt` and `GET /sitemap.xml` routes already carry, which is the
check worth making by hand: a route that planned as `NONE` would be a hole
straight past the staging access gate, and the routes map sets no
`authorization_type` precisely so the module picks `CUSTOM` for it. Those five
existing routes plan as no-op.

No destroys this time, unlike cut 1. Cut 1 destroyed the monolith's two
explicit route keys because `$default` replaced them; that is a one-time cost of
the first cut and `default_integration` is already `"legacy"`. Nothing about the
monolith, the `legacy` integration or its permission changes here, so a plan
showing any destroy on this PR is a reason to stop and read.

### Verification, once applied

`scripts/verify_route_cut.sh staging resume`, with `WEBBPULSE_ORIGIN_VERIFY`
set. Ten paths, both slash forms of each collection, all expected to report
`X-WebbPulse-Domain: resume`.

Item paths are deliberately not probed. Ids come from the `COUNTER#` allocator
in `backend/app/db/repository.py`, so they differ between staging and
production and no literal id is safe to hard code in the script. The `{proxy+}`
key that serves them is what the admin panel exercises.

The `/api/v1/projects/` probe is the one that matters most: it is the path whose
route key section 3.5 would have omitted, so it is the one that would report
`monolith` if the third key were ever dropped.

**One follow up this PR deliberately does not make.** PR #109 added the
`verify-route-cuts` job to `.github/workflows/deploy-backend.yml` and put the
domains it checks in a single `DOMAINS` variable, so that each cut adds one
word to it. Cut 2 should add `resume` there, and this PR does not: that file was
being edited concurrently and touching it here would have meant resolving a
conflict in a workflow this change has no other reason to modify. Until that one
word is added, CI verifies only `public` after each deploy and `resume` has to
be checked by running `scripts/verify_route_cut.sh staging resume` by hand.
The script side of that is ready; only the workflow variable is missing.

### Rollback

Delete the `resume` block from the `routes` map and `"resume"` from
`local.routed_lambda_domains`, then apply. Both have to move together: the
module's `every_integration_is_routed` check fails a plan on an integration no
route can reach, so leaving the name in the list without its route keys does not
plan. `$default` sends all 25 routes back to the monolith, which still serves
them because nothing has been deleted from it.

## Cut 3: content

PR 15. Routes the two prefixes the `content` domain mounts, `posts` and
`site-content`, to the `content` function. Status: **PR open, not applied**.

### What changed

`terraform/apigateway.tf`, `scripts/verify_route_cut.sh` and
`backend/tests/entrypoints/test_gateway_routes.py`.

- `local.routed_lambda_domains` goes from `["public", "resume"]` to
  `["public", "resume", "content"]`, which adds `content` to the `integrations`
  map and, through the module, its `aws_lambda_permission`.
- A new `local.content_prefixes` lists the two mounted prefixes, and the
  `routes` map gains four keys generated from it, appended as a third block
  rather than editing cut 1's or cut 2's.
- `scripts/verify_route_cut.sh`'s `content` case goes from empty to four GET
  probe paths, both slash forms of both prefixes.
- `test_gateway_routes.py` gains the content half, including a test that no
  route key anywhere in the file ends in a trailing slash.

### Two keys per prefix, not three: what cut 2's apply proved

This is the one thing to read before cut 4, and it reverses cut 2's reasoning
above rather than extending it.

Cut 2 gave each collection a third route key, the literal
`ANY /api/v1/<collection>/`, on the grounds that the trailing-slash path is what
the application really serves and that AWS documents neither whether a trailing
slash is normalised before route selection nor whether `{proxy+}` can capture an
empty remainder. The argument was that a literal key is correct whichever way
API Gateway behaves.

**Applying it proved the key cannot exist.** Every one of the five trailing-slash
keys failed the apply with:

```
BadRequestException: Part of the given route key path is empty
```

A route key path segment may not be empty, so `ANY /api/v1/projects/` is not a
route key API Gateway will accept at all. That is a stronger answer than either
reading cut 2 weighed, and it retires the question rather than settling it: the
third option was never available. A separate PR removes those five keys from the
resume block; cut 3 is written to the corrected shape from the start.

So `content` gets two keys per prefix, the bare `ANY /api/v1/posts` and the
greedy `ANY /api/v1/posts/{proxy+}`, and the same pair for `site-content`. Four
keys for 14 application routes.

**What now serves the trailing slash is an open question, and it is deliberately
left to the apply.** `/api/v1/posts/` and `/api/v1/site-content/` are real served
paths. Since no literal key can name them, one of the two remaining keys must
match, either because API Gateway normalises the slash away and the bare key
matches, or because `{proxy+}` does capture an empty remainder. Both remain
undocumented and the two candidate behaviours are not distinguishable by reading.
The verify script therefore probes both slash forms of both prefixes, and the
answer gets written into this section once the apply lands. Either way the path
is served by `content` rather than falling through to the monolith, which is
what the cut has to guarantee; what is unknown is only which key does it.

`test_gateway_routes.py` reflects that honestly rather than picking a side. Its
`matches` helper still encodes the strict reading inherited from cut 2, so the
content coverage test asserts that the only paths it leaves unrouted are the two
collection roots, which keeps a genuinely missing key failing while not
asserting a gateway behaviour nobody has observed yet. The deep paths, which are
routed under any reading, are asserted unconditionally in their own test.

### Why the deep tree needs no more keys than a flat collection

`resume`'s five collections are five flat sibling CRUD routers. `content` is not
shaped like that, and it is worth stating why the same two keys still cover it.

`posts` serves eight paths at three different depths: `/`, `/admin`,
`/admin/{post_id}`, `/admin/{post_id}/publish`, `/categories`,
`/categories/{category_id}`, `/category/{category_slug}` and `/{slug}`.
`site-content` serves one, `/`. The greedy `ANY /api/v1/posts/{proxy+}` key
matches every one of the sub-paths regardless of depth, because `{proxy+}`
captures the whole remainder rather than a single segment. Depth never turns
into extra keys. What makes that safe is ownership rather than shape: the domain
owns every path under both prefixes, so nothing under them should still reach
the monolith.

This is also why the sibling-ordering problem section 1 of the plan flags needs
no gateway involvement. `/api/v1/posts/categories` and `/api/v1/posts/admin` are
literal siblings of the `/api/v1/posts/{slug}` catch-all, and all three stay
inside `content`, so FastAPI's declaration order in
`backend/app/domains/content/posts.py` resolves them exactly as it does in the
monolith. Giving them separate route keys would move that disambiguation into
API Gateway for no benefit and is the one way to get this cut wrong.

`site-content` is a singleton and still gets both keys. Its greedy key matches
nothing the application declares today, unless it turns out to be what serves
the trailing slash. It stays either way: a future sub-path then cannot land on
the monolith by omission, and an unmatched greedy key costs one route resource
and answers from the domain's own 404 rather than from the monolith, which is
the behaviour this cut wants.

`ANY` rather than a method per route, as in cut 2. The domain owns every method
on both prefixes, the unauthenticated GETs and the admin writes alike, so four
keys stand in for all 14 routes and cannot drift when an operation is added.

### Plan

Not yet applied. The speculative plan on the PR confirms 6 to add, 0 to change,
0 to destroy:

- 4 `aws_apigatewayv2_route`, one per generated `content` route key
- 1 `aws_apigatewayv2_integration` for `content`
- 1 `aws_lambda_permission` for `content`, whose statement id the module derives
  as `AllowAPIGatewayInvoke-content` because `content` is not the
  `default_integration`

Every one of the four routes plans with `authorization_type = CUSTOM` and the
same authorizer id the existing routes already carry, which is the check worth
making by hand for the same reason as cut 2: a route that planned as `NONE`
would be a hole straight past the staging access gate, and the routes map sets
no `authorization_type` precisely so the module picks `CUSTOM` for it.

No destroys, as in cut 2. Nothing about the monolith, the `legacy` integration
or its permission changes here, so a plan showing any destroy on this PR is a
reason to stop and read.

### Verification, once applied

`scripts/verify_route_cut.sh staging content`, with `WEBBPULSE_ORIGIN_VERIFY`
set. Four paths, both slash forms of both prefixes, all expected to report
`X-WebbPulse-Domain: content`.

The two trailing-slash probes are the ones that matter, and for a different
reason than cut 2's did. There they proved a key worked; here they establish
which of the two keys serves a path that no key names. `/api/v1/posts/` is the
published post list and `/api/v1/site-content/` is the singleton the front page
renders from, so both are unauthenticated reads and both are load-bearing for
the site.

The deeper posts paths are deliberately not probed, for two separate reasons.
Item paths carry ids and slugs that differ per environment: `{slug}` and
`category/{category_slug}` need content that exists there, and
`admin/{post_id}` ids come from the `COUNTER#` allocator in
`backend/app/db/repository.py`. And the `/admin` paths need an admin bearer
token on top of the gate credential, so an unauthenticated GET would answer 401
from the domain and fail the script's HTTP 200 check while saying nothing about
routing. Both sets are served by the `ANY /api/v1/posts/{proxy+}` key, which
`test_gateway_routes.py` covers in CI and the admin panel exercises in practice.

**The same follow up cut 2 left open applies here.** The `verify-route-cuts` job
in `.github/workflows/deploy-backend.yml` keeps the domains it checks in one
`DOMAINS` variable, and cut 3 should add `content` to it. This PR does not touch
that file: a separate one-line PR is handling the variable for both cuts, and
editing a workflow this change has no other reason to modify would have meant
resolving a conflict in it. Until that lands, CI verifies only `public` after
each deploy and `content` has to be checked by running
`scripts/verify_route_cut.sh staging content` by hand.

### Rollback

Delete the `content` block from the `routes` map and `"content"` from
`local.routed_lambda_domains`, then apply. Both have to move together: the
module's `every_integration_is_routed` check fails a plan on an integration no
route can reach. `$default` sends all 14 routes back to the monolith, which
still serves them because nothing has been deleted from it.
