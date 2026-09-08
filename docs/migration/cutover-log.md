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
`site-content`, to the `content` function. Status: **Applied on staging**
(PR #112), HCP Terraform run `run-pjWK9LRzZz4JL891`: **6 added, 0 changed, 0
destroyed**, exactly the speculative plan below. **Verified in CI** (PR #114,
deploy-backend run 34174774044): all four probes, both slash forms of `posts`
and `site-content`, are served by the `content` function, and the bare request
is rejected by the gate with 403. As with cut 2, the trailing-slash paths are
matched by the bare key: the gateway normalises the slash before route
selection.

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

Not yet applied. The speculative plan after rebasing onto the trailing-slash
fix, `run-yAAN8wvkX3hW6pcb`, reads **6 to add, 0 to change, 0 to destroy**:

- 4 `aws_apigatewayv2_route`, one per generated `content` route key
- 1 `aws_apigatewayv2_integration` for `content`
- 1 `aws_lambda_permission` for `content`, whose statement id the module derives
  as `AllowAPIGatewayInvoke-content` because `content` is not the
  `default_integration`

Confirmed from `/plans/plan-jYeuqdxcNFqnHyo6/json-output`: every one of the four
routes plans with `authorization_type = "CUSTOM"` and
`authorizer_id = "p5vo7t"`, the same
authorizer the existing `$default`, `GET /`, `GET /health`, `GET /robots.txt`
and `GET /sitemap.xml` routes already carry. This is the check worth making by
hand for the same reason as cut 2: a route that planned as `NONE` would be a
hole straight past the staging access gate, and the routes map sets no
`authorization_type` precisely so the module picks `CUSTOM` for it.

No destroys, as in cut 2. Nothing about the monolith, the `legacy` integration
or its permission changes here, so a plan showing any destroy on this PR is a
reason to stop and read. Every existing resource plans as a no-op.

**One thing the earlier plan on this PR showed that is worth carrying into cut
4.** Before the rebase this branch still carried cut 2's five trailing-slash
keys, and the plan then read 11 to add: the five invalid keys planned perfectly
cleanly, with `authorization_type = CUSTOM` like everything else. Terraform
cannot tell that API Gateway will reject a route key with an empty path
segment; the `BadRequestException` appears only at apply. **A green plan is
therefore not evidence that a route key is valid.** That is why
`test_gateway_routes.py` asserts key shape statically across the whole routes
map rather than trusting the plan, and it is the check cut 4 should keep.

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

## Cut 4: identity

PR 16. Routes the `/api/v1/admin` prefix to the `identity` function. Status:
**Applied on staging** (PR #115), HCP Terraform run `run-DqfE5zcewV5esunT`:
**4 added, 0 changed, 0 destroyed**, exactly the speculative plan below. CI
verification is wired by the same PR that records this status, which adds
`identity` to the `verify-route-cuts` `DOMAINS` list; its result is recorded
under "Verification, once applied" when the next deploy runs.

This is the last cut. With `identity` routed, every domain in
`local.lambda_domains` has an integration and a route key, and what remains in
section 6 is retiring the monolith rather than carving anything further off it.

### What changed

`terraform/apigateway.tf`, `scripts/verify_route_cut.sh` and
`backend/tests/entrypoints/test_gateway_routes.py`.

- `local.routed_lambda_domains` goes from `["public", "resume", "content"]` to
  `["public", "resume", "content", "identity"]`, which adds `identity` to the
  `integrations` map and, through the module, its `aws_lambda_permission`.
- The `routes` map gains two literal keys, `ANY /api/v1/admin` and
  `ANY /api/v1/admin/{proxy+}`, appended as a fourth block.
- `scripts/verify_route_cut.sh`'s `identity` case goes from empty to four GET
  probe paths, and the script gains a per-domain `EXPECTED_CODES` set. See
  "The script had to change, and why" below; this is the one place cut 4 needed
  more than a copy of cut 3.
- `test_gateway_routes.py` gains the identity half, seven tests.

### The route keys, written literally rather than generated

Cuts 2 and 3 each generated their keys from a `local` list, because they had
five collections and two prefixes respectively. `identity` mounts one prefix, so
there is no `local.identity_prefixes`: a one element list would be indirection
with nothing to factor out. The two keys are written out in the routes map.

The expected keys from section 3.5 line 753 are exactly what landed:

```
ANY /api/v1/admin
ANY /api/v1/admin/{proxy+}
```

Two keys per prefix, no trailing-slash key, matching cut 3's corrected shape.

### Where the router code and the plan document agree, and one place the shape differs

Section 1 of the plan says `identity` is "1 route", `POST /api/v1/admin/login`,
and the code agrees exactly. `backend/app/domains/identity/router.py` declares a
single bare `POST /login`; the `/admin` prefix comes from the descriptor's
`router_prefix` in `backend/app/composition/wiring.py`, not from the router, as
the plan's own note at "identity mounts at /api/v1/admin" describes. Building
the application confirms it: `build_domain_app("identity")` serves
`POST /api/v1/admin/login` and nothing else outside `/health` and the FastAPI
documentation paths. **Nothing identity serves lies outside `/api/v1/admin`**,
so the two keys above are the whole cut.

What is different from the earlier cuts is not the key list but which key does
the work, and it is worth stating because it inverts the pattern:

- **The greedy key carries all of the traffic.** `/api/v1/admin/login` is one
  segment below the prefix, so `ANY /api/v1/admin/{proxy+}` matches it with a
  non-empty remainder. **Cut 4 therefore rests on no undocumented gateway
  behaviour at all.** The empty-remainder and trailing-slash questions that cuts
  2 and 3 had to leave to the apply simply do not arise: no served path here
  ends in a slash, because the domain declares no route at its prefix root.
- **The bare key matches nothing the application serves.** There is no `GET /`
  under `/api/v1/admin` the way `resume`'s collections and `content`'s prefixes
  have, so `/api/v1/admin` and `/api/v1/admin/` are both 404s from the identity
  function. It is kept for the same reason `content` keeps `site-content`'s
  unmatched greedy key: the prefix belongs to this domain, so its root should
  answer from the domain's own 404 rather than fall through to `$default`, and a
  route added at the root later cannot then be left on the monolith by omission.

`ANY` rather than `POST`, even though the only route is a POST. The domain owns
every method on the prefix, so a GET to `/api/v1/admin/login` should answer 405
from `identity`. Routing it to the monolith instead would be the worst kind of
failure here, because the monolith declares the same login endpoint and would
answer plausibly. It is also what makes the verify script's GET probes
meaningful at all.

### The script had to change, and why

This is cut 4's counterpart to cut 2's trailing-slash lesson, and the next
person to add a domain should read it.

`scripts/verify_route_cut.sh` judged every probe against HTTP 200: it retried
until it saw one and failed the path otherwise. That was correct for cuts 1 to
3, where every probed path is an unauthenticated GET that really does return a
body. **It is wrong for `identity`, and it would have failed the cut while the
cut was working.** The only route under this prefix is a POST, so the honest
answers to the script's own GET probes are:

```
GET /api/v1/admin/login  -> 405, from the identity function
GET /api/v1/admin        -> 404, from the identity function
```

Both prove the cut worked. Both would have been reported `FAIL`.

The fix is small and it clarifies what the script was always doing. The script's
verdict comes from the `X-WebbPulse-Domain` header, not from the status: a 405
carrying `X-WebbPulse-Domain: identity` answers the only question being asked,
which is which function served the request. The status is only useful for
telling a real answer apart from a cold-start blip worth retrying. So each
domain now declares an `EXPECTED_CODES` set, defaulting to `200` so cuts 1 to 3
are untouched, and `identity` sets `200 404 405`. Both messages and the retry
loop report the code they actually saw instead of a hardcoded 200.

**One further change, and it fixes a real hole rather than an inconvenience.**
The script's final authorizer check sends one request with no credential and
failed if it got a 200, on the reasoning that a route created with
`authorization_type = NONE` would answer normally. For `identity` that test is
useless: its first probe path is a GET against a POST-only route, so a route
genuinely past the gate would answer 405 and the check would have reported `OK`.
The check now keys off the same domain header as the main loop. If a request
with no credential comes back carrying `X-WebbPulse-Domain` at all, whatever the
status, it reached the application and the gate did not stop it; the gate's own
rejection is a Cognito redirect or a 401 from the authorizer and carries no such
header. This is strictly stronger than the old test for every domain, not only
for `identity`.

Both behaviours were exercised against a local mock before the PR: the healthy
case passes on 404s and 405s, a monolith fall-through still reports `NOT CUT
OVER` and exits 1, a simulated `authorization_type = NONE` is now caught on a
405 where the old check passed it, and `content`'s probes are unchanged.

The login route is probed with GET rather than POST deliberately. A POST would
run the real login handler and its rate limiter
(`backend/app/core/login_limiter.py`), which is keyed on client IP, so a CI job
running on every deploy would spend the pipeline's egress IP budget of failed
attempts and could lock out a real login from the same address. A GET reaches
the same route key and the same function, and touches no application state.

### Plan

Not yet applied. The speculative plan on the PR, `run-d2rLq7jSou8rkcUc`, reads
**4 to add, 0 to change, 0 to destroy**:

- 2 `aws_apigatewayv2_route`, one per literal `identity` route key
- 1 `aws_apigatewayv2_integration` for `identity`, pointing at
  `webbpulse-staging-identity`
- 1 `aws_lambda_permission` for `identity`, whose statement id the module
  derives as `AllowAPIGatewayInvoke-identity` because `identity` is not the
  `default_integration`

Section 8 row 16 estimates "2 to add" for this cut. The estimate counts only the
route keys; the integration and the permission come with any domain's first
route, exactly as they did in cuts 2 and 3, so 4 is the expected number and not
a surprise.

Confirmed from `/plans/plan-jE3ZQ7MrQavNnCgg/json-output`: both new routes plan
with `authorization_type = "CUSTOM"` and `authorizer_id = "p5vo7t"`, the same
authorizer every existing route already carries. This is the check worth making
by hand for the same reason as cuts 2 and 3: a route that planned as `NONE`
would be a hole straight past the staging access gate, and the routes map sets
no `authorization_type` precisely so the module picks `CUSTOM` for it.

It matters more here than it did on the earlier cuts. The route being added is
the admin login, so a route that skipped the gate would expose the one endpoint
that accepts credentials. It is also the case the verify script's old
authorizer check could not have caught, which is why that check was rewritten in
this PR to key off the domain header rather than a 200.

The other 153 resources in the workspace plan as no-ops, including all 19
existing routes and `$default`.

No destroys, as in cuts 2 and 3. Nothing about the monolith, the `legacy`
integration or its permission changes here, so a plan showing any destroy on
this PR is a reason to stop and read.

Cut 3's warning still applies and is worth repeating because it is the one thing
a green plan cannot tell you: Terraform cannot see that API Gateway will reject
a route key with an empty path segment, so a trailing-slash key plans perfectly
cleanly and fails only at apply. That is why `test_gateway_routes.py` asserts key
shape statically across the whole routes map, and cut 4 keeps that test.

### Verification, once applied

`scripts/verify_route_cut.sh staging identity`, with `WEBBPULSE_ORIGIN_VERIFY`
set. Four paths, both slash forms of the served route and of the prefix root,
all expected to report `X-WebbPulse-Domain: identity` with a 404 or a 405 rather
than a 200.

The two `/api/v1/admin` probes are the ones worth watching. They are the paths
the bare key exists for, and they are the only thing that would show that key
doing its job, since it matches nothing the application serves.

A real login is not probed, by design. It needs credentials this script must
never carry, and it would consume the rate limiter's budget for the runner's IP.
The `{proxy+}` key that serves it is covered by `test_gateway_routes.py` in CI
and by the admin panel's own traffic.

**The same follow up cuts 2 and 3 left open applies here.** The
`verify-route-cuts` job in `.github/workflows/deploy-backend.yml` keeps the
domains it checks in one `DOMAINS` variable, and cut 4 should add `identity` to
it. This PR does not touch that file: a separate PR is handling the variable for
all the cuts at once. Until that lands, CI verifies only `public` after each
deploy and `identity` has to be checked by running
`scripts/verify_route_cut.sh staging identity` by hand.

### Rollback

Delete the `identity` block from the `routes` map and `"identity"` from
`local.routed_lambda_domains`, then apply. Both have to move together: the
module's `every_integration_is_routed` check fails a plan on an integration no
route can reach. `$default` sends `POST /api/v1/admin/login` back to the
monolith, which still serves it because nothing has been deleted from it.

Rolling this cut back is the one with the sharpest user-visible edge, since the
route it moves is the admin login itself: a broken `identity` function means
nobody can sign in to the admin panel, where a broken `resume` or `content`
function degrades reads the site can mostly survive. The rollback is still just
the two edits above and one apply.

## Retirement: the monolith

PR 17, and the last entry in this file. Not a cut: the four cuts moved route
keys off the monolith one prefix at a time and this deletes what is left of it.
Status: **not yet applied**, speculative plan below.

Section 6's "Retiring the monolith" is the design. It prescribes four steps and
this PR does two of them; the other two are a separate PR and the reason is
recorded under "What section 6 got wrong" below.

### What changed

`terraform/apigateway.tf`, `terraform/lambda.tf`, `terraform/monitoring.tf`,
`terraform/outputs.tf`, `terraform/iam_github_actions.tf`,
`.github/workflows/deploy-backend.yml`, `scripts/verify_route_cut.sh` and
`backend/tests/entrypoints/test_gateway_routes.py`.

- `default_integration` goes from `"legacy"` to `null`, which deletes the
  `$default` route. Anything the explicit keys do not match now gets API
  Gateway's own 404 instead of the monolith.
- The `legacy` entry leaves the `integrations` map, taking its integration and
  its `aws_lambda_permission` with it. The map is now a plain comprehension over
  `local.routed_lambda_domains` rather than a `merge` of `legacy` and the
  domains.
- `module.lambda_api` and `aws_iam_role_policy.lambda_api` are deleted from
  `lambda.tf`, which destroys the function, its execution role, both its role
  policies and its log group. The file keeps only the artifacts bucket.
- `monitoring.tf` drops the monolith from `lambda_function_names` and drops the
  `api` key from `error_log_groups`.
- `outputs.tf` drops `lambda_function_name`.
- `iam_github_actions.tf` drops the monolith's function ARN from the
  `UpdateFunctionCode` grant and narrows the artifacts bucket grant to
  read-only.
- `deploy-backend.yml` loses the `deploy` job entirely, and `verify-route-cuts`
  loses its `needs: deploy` and the `needs.deploy.result == 'success'` guard.
- `verify_route_cut.sh` learns what a fall-through means now. See "The script
  had to change again" below.
- `test_gateway_routes.py` gains `test_no_default_route` and
  `test_no_legacy_integration`.

### What is destroyed, in full

Eight resources, confirmed against the speculative plan. The list is short
enough to read and long enough that it belongs in the PR description as well:

- `module.api.aws_apigatewayv2_route.this["$default"]`
- `module.api.aws_apigatewayv2_integration.this["legacy"]`
- `module.api.aws_lambda_permission.this["legacy"]`
- `module.lambda_api.aws_lambda_function.this`
- `module.lambda_api.aws_iam_role.this`
- `module.lambda_api.aws_cloudwatch_log_group.this`
- `aws_iam_role_policy.lambda_api`
- `module.alarms.aws_cloudwatch_log_metric_filter.errors["api"]`

Two corrections to the list this entry was first written with, both from
reading the plan rather than the module source. There is no
`module.lambda_api.aws_iam_role_policy_attachment.basic_execution`: the
`lambda-function` module attaches the basic execution policy inline on the role
rather than as its own resource, so the role is the only IAM resource the module
owns and destroying it takes the attachment with it. And the metric filter is
`aws_cloudwatch_log_metric_filter.errors`, not `application_errors`.

**Nothing about the four domain functions is destroyed, and that is the line a
reviewer should check first.** In particular none of the four
`aws_lambda_permission.this["<domain>"]` resources is replaced. The module
derives a permission's statement id as `var.lambda_permission_statement_id`
verbatim for the `default_integration` and `"<that>-<key>"` for everything else,
so a reviewer's reasonable worry is that removing the `default_integration`
moves the bare id onto one of the domains and replaces its permission. It does
not, because the id is bare only when the integration *is* the
`default_integration` or when there is exactly one integration, and after this
change there is neither: `default_integration` is null and there are four
integrations. All four keep `AllowAPIGatewayInvoke-<domain>`. The bare
`AllowAPIGatewayInvoke` is destroyed with `legacy` and is not reassigned.

### What is deliberately kept

- **The artifacts bucket** and its placeholder object. It holds the zips the
  monolith was deployed from and the last one is the rollback vehicle. Section 6
  does not mention it; keeping it is a judgement call and the reasoning is in
  `lambda.tf`'s header comment. It costs cents and destroying it would make the
  rollback below impossible.
- **The four ECR repositories.** They are the domain functions' image
  repositories and have nothing to do with the monolith, which was a zip
  function from S3 and never had an image repository at all. Section 6's
  retirement list does not mention ECR and the task framing's "check what the
  plan says about keeping the image repo" has no referent here.
- **The monolith's Python source.** See below.

### What section 6 got wrong

Section 6 lists four steps. Steps 1 and 2 are this PR. Steps 3 and 4 cannot be
done here, and one of them is wrong outright.

**Step 4, "drop `mangum` and `aws-lambda-powertools` from the dependencies", is
wrong for Powertools and would break production.** `mangum` is monolith-only:
`app/lambda_handler.py` is its only importer and dropping it is safe. Powertools
is not. `app/core/logging.py` imports `aws_lambda_powertools.Logger`, and three
of the four *domain* services import that logger:

```
backend/app/domains/public/service.py:7:   from ...core.logging import logger
backend/app/domains/content/service.py:3:  from ...core.logging import logger
backend/app/domains/identity/service.py:2: from ...core.logging import logger
```

`backend/Dockerfile` installs the same `requirements.txt` the monolith's
`build_lambda.sh` did, so dropping `aws-lambda-powertools` from it would fail
`public`, `content` and `identity` at import on their next image build. Section
5's "Removing Sentry" and the plan's expectation that domain functions log
through `webbpulse.logging` are true of the entrypoints and the middleware but
not of these three services, which were never migrated off the Powertools
logger. Retiring Powertools is a real piece of work on the domain code and is
not a line in a retirement PR. Neither dependency is dropped here.

**Step 3, deleting `app/main.py`, `app/lambda_handler.py`, `app/api/v1/api.py`
and `backend/scripts/build_lambda.sh`, is correct but is not this PR.**
`app.main` is load-bearing for the test suite rather than only for the deployed
function:

- `backend/tests/conftest.py` builds the shared test client from `app.main`.
- `backend/tests/entrypoints/test_route_split.py` imports it as `monolith` and
  proves the four domain applications are exactly a partition of it. That is the
  invariant the whole split rests on, and deleting `app.main` deletes the
  reference the partition is measured against rather than merely deleting dead
  code.
- `backend/tests/test_openapi_contract.py` and
  `backend/tests/test_domain_boundaries.py` also name it.

So step 3 is a test-suite rewrite that has to decide what replaces `app.main` as
the reference surface, most likely `app.composition.app`, which is root A and
already builds the same whole surface from the domain routers. Folding that into
the PR that destroys eleven AWS resources would make both halves harder to
review, and the source is inert once nothing deploys it. It is the next PR.

The infrastructure retirement does not wait on it: `build_lambda.sh` stops being
called the moment the `deploy` job is deleted, and the source it packages stops
being deployed the moment the function is destroyed.

### The script had to change again

Cut 4 changed `scripts/verify_route_cut.sh` because `identity` answers 404 and
405 rather than 200. The retirement changes it again, and for a sharper reason:
**the meaning of a fall-through inverted.**

The script's whole design was that a route key which fails to match is caught by
`$default`, reaches the monolith, and comes back stamped
`X-WebbPulse-Domain: monolith`. That was a wrong-routing-but-working-surface
signal, which is why the wording throughout was "NOT CUT OVER" rather than
"broken". There is no `$default` now. A path no key matches is answered by API
Gateway itself, with a 404 and **no** `X-WebbPulse-Domain` header, and it is
unreachable rather than misrouted.

Three changes follow:

1. A new `NO ROUTE` verdict, keyed on the pair *404 and no domain header*. The
   pair is what makes it unambiguous, and `identity` is why it has to be a pair:
   `identity` legitimately answers 404 from its own function, so the status
   alone cannot mean "no route matched". A 404 with the header is the function
   saying it has no such path; a 404 without it is the gateway saying no
   function was invoked.
2. That check runs **before** the `EXPECTED_CODES` status test, and has to. For
   every domain but `identity`, 404 is not an expected code, so the status test
   would have reported an unrouted path as a generic "expected 200" and buried
   the one thing worth saying about it. The retry loop also breaks early on the
   same pair, since an unmatched route key does not become matched by waiting.
3. The `monolith` verdict is kept but is no longer a fall-through. Reaching a
   retired function means it and a route to it were re-created, so it reports
   `MONOLITH SERVING` and says so.

`NO ROUTE` is reported ahead of `FAILED` in the summary because it is the more
serious of the two: an unrouted path is a 404 to every caller, where a failure
is usually a stale image or a transient status.

All five verdicts were exercised against a mock `curl` before the PR, the same
way cut 4's changes were: a healthy domain passes and exits 0; an unrouted
domain reports `NO ROUTE` and exits 1; a monolith response reports
`MONOLITH SERVING` and exits 1; a headerless non-404 reports `FAILED`; and
`identity`'s own 404s still pass.

### Plan

`run-qj94xMEonSnDKHBh` / `plan-J2rEixHoooX1Urd8`, against commit `7638ab7` on
PR 118: **0 to add, 4 to change, 8 to destroy.** The eight destroys are exactly
the list above. Every other resource in the workspace plans as a no-op,
including all 21 explicit route keys, all four domain integrations and all four
domain permissions.

Nothing plans as `create` or `replace` anywhere in the run. That is the single
most useful line in the plan for this PR, because it settles the sequencing
question below in one read.

The four changes, named because a retirement PR that shows changes rather than
only destroys invites a second look:

- `module.alarms.aws_cloudwatch_metric_alarm.lambda_aggregate_errors[0]` and
  `...lambda_aggregate_throttles[0]`. The module turns `lambda_function_names`
  into positional metric math ids and the monolith led that list, so dropping it
  shifts every domain's id down one. The errors alarm goes from
  `m0 + m1 + m2 + m3 + m4` over five ids to `m0 + m1 + m2 + m3` over four, with
  the four remaining metrics the four domain functions. A metric math rewrite
  with no behaviour change.
- `module.alarms.aws_cloudwatch_metric_alarm.errors[0]`, the log-metric-filter
  alarm, for the same reason one rung down: it aggregates over the filters and
  one filter is going away.
- `module.github_actions_role.aws_iam_role_policy.this[0]`: one fewer function
  ARN on the `UpdateFunctionCode` statement, and the artifacts bucket grant
  narrowed to read-only.

**How `$default` sequences.** It is a plain destroy. There is no
destroy-then-create on it, so no `create_before_destroy` and no two-step apply
is needed, and there is no window in which `$default` exists pointing somewhere
wrong. What there is instead is a window, inside the apply, where `$default` is
gone and a request that would have used it gets an API Gateway 404. That window
is only a problem for a request that needed `$default`, and after four cuts no
request should: every path the four applications serve has an explicit route
key, and all 21 of those keys plan as no-ops, so none of them is disturbed while
`$default` is removed. `test_gateway_routes.py` asserts the same exhaustiveness
statically in CI. If that assertion is wrong, the apply is when it becomes
visible.

The four domain permissions planning as no-ops is the confirmation of the
statement-id reasoning above: removing the `default_integration` does not move
the bare `AllowAPIGatewayInvoke` onto any domain.

### Verification, once applied

`verify-route-cuts` runs all four domains on the next deploy and is the check
that matters, because it probes the live gateway for exactly the paths that
would have been silently absorbed by `$default` before. A pass is stronger
evidence after this PR than before it: the same probes that used to prove
"routed to the right function" now also prove "reachable at all".

The `deploy` job's `/health` smoke test is gone with the job. `public` serves
`/health` and `verify-route-cuts` probes it as the first of `public`'s four
paths, so the coverage survives in a job that also checks which function
answered.

### Rollback

This is the first entry in this file whose rollback is not one map edit, and it
is worth being honest about that. The four cuts were reversible by deleting a
routes entry because the monolith still held every route. Nothing holds them
now.

Rolling back means re-creating the monolith:

1. Revert this PR's Terraform. That restores `module.lambda_api`,
   `aws_iam_role_policy.lambda_api`, the `legacy` integration and permission,
   and `default_integration = "legacy"`.
2. The function is re-created from `module.lambda_artifacts`'s placeholder
   object, which answers 503, so it has to be pointed at real code before it
   serves anything:

   ```
   aws lambda update-function-code \
     --function-name webbpulse-staging-api \
     --s3-bucket webbpulse-staging-lambda-artifacts \
     --s3-key backend/6c6a122a65f1443831255111d30102690d487cb8.zip \
     --publish
   ```

   **That key is the rollback artifact and it is why the bucket is kept.**
   `6c6a122a65f1443831255111d30102690d487cb8` is the commit at the head of
   `staging` when this PR was opened, which is the last commit whose `deploy`
   job ran and uploaded a zip. The `deploy` job's `ARTIFACT_KEY` was
   `backend/${{ github.sha }}.zip`, so every zip it ever uploaded is at that
   path under its own commit sha, and the bucket's lifecycle rule expires
   noncurrent versions after 30 days but does not expire the objects
   themselves.
3. Restore the `deploy` job in `deploy-backend.yml` if the monolith is to keep
   receiving deploys, and re-add the write half of the artifacts bucket grant in
   `iam_github_actions.tf`, which this PR narrowed to read-only.

Steps 1 and 2 are enough to serve traffic again; step 3 is only for a rollback
that is expected to last.

**The rollback window is the bucket's, not this PR's.** Nothing expires the zip
on a schedule, but nothing writes a new one either, so the longer the monolith
stays retired the staler the rollback target gets. Once the four domain
functions have carried production long enough to trust, the bucket and the
monolith's Python source go together in one final PR and the rollback stops
existing. That is the right time to close it out, and it is deliberately not
now.

## Source removal: the monolith's Python

Not a cut and not an infrastructure change: no Terraform runs and no AWS
resource is touched. The retirement above destroyed the monolith's function, its
integration and `$default`, and deliberately left the source in the tree because
the test suite was built on it. This is the PR that finishes step 3 of section 6,
which the retirement entry called out as "a test-suite rewrite" and "the next
PR".

### Deleted

| Path | Why it could go |
| --- | --- |
| `backend/app/main.py` | The monolith's application. Nothing deploys or imports it |
| `backend/app/lambda_handler.py` | The Mangum handler. The four functions run under the Web Adapter and have no handler |
| `backend/app/api/v1/api.py`, `app/api/` | The monolith's composition root. `app/composition/wiring.py` is the live one |
| `backend/scripts/build_lambda.sh` | Built `dist/function.zip` for a function that no longer exists. `build_image.sh` replaced it |
| `backend/tests/test_lambda_handler.py` | Drove API Gateway v2 events through Mangum. There is no Mangum |
| `mangum==0.19.0` | `app/lambda_handler.py` was its only importer |

**`aws-lambda-powertools` stays**, for the reason the retirement entry gives at
length: `app/core/logging.py` imports its `Logger` and the `content`, `identity`
and `public` services import that logger. Dropping it would fail three of the
four images at import. Section 6's step 4 is still wrong about it, and moving
those services onto `webbpulse.logging` is its own piece of work.

### What replaced `app.main` as the reference surface

Two things, because `app.main` was doing two jobs.

**As the application the test client is built from**, root A replaced it.
`tests/conftest.py`'s `client` fixture now calls
`app.composition.app.build_app()`. Root A is every domain's routers on one
application, assembled from the same `wiring.DOMAINS` list the four deployed
entrypoints read, so a route the test client reaches is a route some domain
function serves. That was never true by construction of `app.main`, which held
its own second copy of the router list.

**As the thing the split was measured against**, a recorded fixture replaced it.
`tests/fixtures/route_contract.json` holds the 44 (method, path) pairs and the
42 documented operations with their ids and tags, generated from the contract
`tests/test_openapi_contract.py` already pinned.

The fixture is a stronger reference than the module was, which is worth stating
because deleting a test's reference usually weakens it. `app.main` was code: a
change that broke the published contract could be made to the monolith and the
domains in one commit, and `union == monolith` would still hold while the
contract moved underneath it. A JSON file cannot be edited by a refactor. Moving
it takes a deliberate edit to a file whose only purpose is to say what the API
publishes, which is exactly the review the contract deserves.

`test_route_split.py` keeps all four of its properties (subset, no overlap,
union, counts) against the fixture, and gains two: the fixture is checked for
shape before anything is measured against it, so a truncated contract fails
loudly rather than passing everything; and root A's route set is asserted equal
to the union of the four, which is the root A / root B drift check that
`app.main` was trusted to provide and never actually gave.

### Local development

`uvicorn app.main:app` is gone from `CLAUDE.md` and both READMEs. There are three
ways to run the backend locally now, in increasing order of fidelity:

```bash
uvicorn app.composition.app:app --reload      # root A, all 44 routes, one process
PORT=8010 python -m app.entrypoints.content   # root B, one domain, as the image runs it
docker compose --profile domains up --build   # all four images, under the Web Adapter
```

The middle one is what the Dockerfile's `CMD` runs (`python -m
app.entrypoints.${DOMAIN}`), and `run_uvicorn` binds `AWS_LWA_PORT`, then
`PORT`, then 8080. The last needs a CodeArtifact token, since the image installs
`webbpulse`.

### The rollback got weaker, on purpose

The retirement entry's rollback restores the monolith by pointing
`default_integration` back at a rebuilt `legacy` integration and calling
`update-function-code` with the last zip in the artifacts bucket. That zip is
untouched and step 1 and 2 of that procedure still work, because they are
Terraform and a Lambda API call and neither reads this repository.

What no longer works is rebuilding that zip from the tree: `build_lambda.sh` and
the source it packaged are gone, so a rollback is now pinned to the artifact in
the bucket rather than reproducible from source. That is the intended direction.
The four domain functions have served every route since the retirement, and
keeping a second composition root compiling forever to preserve a rollback
nobody expects to use is the cost the retirement entry said it was not willing
to keep paying. Restoring the source is a `git revert` of this PR if it ever
comes to that.
