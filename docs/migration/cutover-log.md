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
