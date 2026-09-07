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
