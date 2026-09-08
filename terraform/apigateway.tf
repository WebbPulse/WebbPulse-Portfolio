# ---------------------------------------------------------------------------
# HTTP API in front of the Lambda backend.
#
# Behind the staging access gate the API is reachable only through its custom
# domain, where the gate's authorizer applies. The browser calls it directly at
# api.staging.webbpulse.com and the authorizer checks the gate's signed cookies,
# an origin-verify header (pipelines, health checks), or lets an OPTIONS
# preflight through. Both inputs are gated on local.staging_gate_enabled so
# production plans a no-op.
#
# The certificate lives in acm.tf and the api.<domain> alias record in
# route53.tf, because production writes DNS through aws.dns.
#
# Section 3.5 and section 6 of docs/migration/pilot-split-plan.md: the strangler
# runs through this file. Each cut adds route keys for one domain and the
# monolith keeps everything else through $default, so a cut is one map edit and
# a rollback is deleting it again. The cuts so far are recorded in
# docs/migration/cutover-log.md.
# ---------------------------------------------------------------------------

locals {
  # Domains that have been cut over, in cut order. A domain belongs here only
  # once apigateway.tf's routes map names it: the http-api module's
  # every_integration_is_routed check fails the plan on an integration no route
  # can reach, so this list and the routes map below move together.
  #
  # Cut 1 is `public`, cut 2 is `resume`, cut 3 is `content`. Cut 4 appends
  # identity.
  routed_lambda_domains = ["public", "resume", "content"]

  # The five collections the `resume` domain owns. Every one of them is built by
  # build_crud_router in backend/app/domains/resume/crud_router.py and so serves
  # exactly the same five operations, which is why the route keys below are
  # generated from this list rather than written out twenty-five times. The
  # names are the router prefixes in backend/app/domains/resume/router.py.
  resume_collections = [
    "projects",
    "experience",
    "skills",
    "education",
    "certifications",
  ]

  # The two prefixes the `content` domain mounts, from
  # backend/app/domains/content/router.py: `posts_router` under `/posts` and
  # `site_content_router` under `/site-content`. Both are plain APIRouters
  # whose own routes are declared at `/` and below, so both take the same two
  # keys, bare and greedy, and the names here are the router prefixes with
  # their leading slash stripped.
  #
  # These are not five sibling collections the way `resume`'s are. `posts` is a
  # deep tree (`/admin/{post_id}/publish` is three segments below the prefix)
  # and `site-content` is a singleton with one path. What they share is the
  # only thing the route keys care about: everything the domain serves under
  # each name belongs to the domain, so one greedy key per prefix covers it.
  content_prefixes = [
    "posts",
    "site-content",
  ]
}

module "api" {
  source  = "app.terraform.io/WebbPulse/platform-modules/aws//modules/http-api"
  version = "~> 2.0"

  name = "${local.prefix}-api"

  # The monolith plus the four per-domain functions from lambda_domains.tf. The
  # per-domain entries are generated from module.lambda_domain rather than
  # written out one at a time, so a domain added to local.lambda_domains cannot
  # be left without an integration here.
  #
  # Only the domains that have a route are reachable. The module's
  # every_integration_is_routed check refuses an integration nothing can reach,
  # so the one domain still waiting for its cut is deliberately not listed yet:
  # identity arrives with its routes in cut 4.
  integrations = merge(
    {
      legacy = {
        lambda_function_name           = module.lambda_api.function_name
        lambda_invoke_arn              = module.lambda_api.invoke_arn
        lambda_permission_statement_id = "AllowAPIGatewayInvoke"
      }
    },
    {
      for name in local.routed_lambda_domains : name => {
        lambda_function_name = module.lambda_domain[name].function_name
        lambda_invoke_arn    = module.lambda_domain[name].invoke_arn
      }
    },
  )

  # Cut 1. The monolith moves off its two explicit route keys and onto $default,
  # which is what lets a prefix be carved off it one cut at a time: API Gateway
  # matches a full route key first, then a greedy {proxy+}, then $default last,
  # so everything not named in routes keeps falling through to the monolith and
  # a rollback is deleting the routes entry again.
  default_integration = "legacy"

  # No authorization_type is set on any entry below, which means the module's
  # own choice, CUSTOM whenever authorizer_id is set, so every one of them stays
  # behind the staging access gate exactly as $default does. Setting NONE on any
  # of them, including on a read-only GET to make a probe simpler, would punch a
  # hole straight past the gate.
  routes = merge(
    # Cut 1. `public`'s four routes, all literal, all unauthenticated in the
    # application and none of them writing.
    {
      "GET /health"      = { integration = "public" }
      "GET /"            = { integration = "public" }
      "GET /sitemap.xml" = { integration = "public" }
      "GET /robots.txt"  = { integration = "public" }
    },

    # Cut 2. `resume`: five collections, five operations each, 25 application
    # routes. Three keys per collection rather than section 3.5's two, and the
    # third one is there because AWS does not document what happens without it.
    #
    # The collection path this application actually serves carries a trailing
    # slash. build_crud_router declares `GET /`, `POST /` and the item routes
    # `GET|PUT|DELETE /{item_id}`, mounted under `/api/v1/<collection>`, so the
    # real paths are `/api/v1/projects/` and `/api/v1/projects/123`. Section
    # 3.5's snippet gives each collection only `ANY /api/v1/projects` and
    # `ANY /api/v1/projects/{proxy+}`, and whether either of those matches
    # `/api/v1/projects/` is not something the routes map can name directly.
    #
    # The first cut 2 apply tried a literal `ANY /api/v1/projects/` key for it
    # and API Gateway rejected every one with "BadRequestException: Part of the
    # given route key path is empty" (HCP run run-wejfhcFYu9riFnvc, 2026-09-07).
    # A route key may not end in a slash, so the trailing-slash request has to
    # be matched by the bare key or by the greedy key, and which of those the
    # gateway picks is undocumented: nothing says a trailing slash is normalised
    # away before route selection, and nothing says whether `{proxy+}` may
    # capture an empty remainder.
    #
    # That question is settled empirically rather than by reading. The
    # verify-route-cuts job in deploy-backend.yml probes both slash forms of
    # every collection after each deploy and fails if either one is still
    # answered by the monolith through $default, which is the quiet failure mode
    # this comment exists to warn about. Until the monolith is retired, a
    # trailing-slash request that falls through is still served correctly, so
    # the probe is a signal and not an outage.
    #
    # The bare key is not redundant either: the frontend's getProjects(true)
    # emits `/projects?featured_only=true/`, whose path component is the bare
    # `/api/v1/projects` with the slash inside the query string
    # (frontend/src/services/api.ts), and TrailingSlashMiddleware is what makes
    # that reach the handler once the request arrives.
    #
    # ANY rather than a method per route. The 25 routes are five methods across
    # five collections and the domain owns every method on its prefixes, so ANY
    # names them in two keys instead of ten and cannot drift when a sixth
    # operation is added to build_crud_router. It also keeps an unsupported
    # method answering from the domain's own 405 rather than from the monolith.
    merge([
      for collection in local.resume_collections : {
        "ANY /api/v1/${collection}"          = { integration = "resume" }
        "ANY /api/v1/${collection}/{proxy+}" = { integration = "resume" }
      }
    ]...),

    # Cut 3. `content`: posts, categories and the site-content singleton, 14
    # application routes across two mounted prefixes, in four keys.
    #
    # Two keys per prefix, not cut 2's three. Cut 2 added a literal
    # trailing-slash key per collection to settle an ambiguity the AWS
    # documentation leaves open, and applying it settled the ambiguity a
    # different way: API Gateway rejects the key outright. Every
    # `ANY /api/v1/<collection>/` key failed the apply with
    #
    #   BadRequestException: Part of the given route key path is empty
    #
    # so a route key path segment may not be empty and the trailing-slash form
    # is not a route key that can exist. That is a stronger answer than either
    # reading cut 2 weighed: the question was never which of the two candidate
    # keys matches `/api/v1/posts/`, because the third option is not available.
    # A separate PR removes those five keys from the resume block; this cut is
    # written to the corrected shape from the start and must not reintroduce it.
    #
    # What serves the trailing slash is therefore one of the two keys below,
    # and which one is now an empirical question rather than a design choice.
    # The verify script probes both slash forms of both prefixes against the
    # real gateway for exactly that reason, and the answer gets written into
    # docs/migration/cutover-log.md once the apply lands. Whichever key wins,
    # the path is served by `content` rather than falling through to the
    # monolith, which is what this cut has to guarantee.
    #
    # `content` is shaped differently from `resume` and it is worth saying why
    # two keys per prefix still cover it. `resume`'s five collections are five
    # flat sibling CRUD routers. `content` is one deep tree plus one singleton:
    # `posts` serves `/`, `/admin`, `/admin/{post_id}`,
    # `/admin/{post_id}/publish`, `/categories`, `/categories/{category_id}`,
    # `/category/{category_slug}` and `/{slug}`, while `site-content` serves
    # only `/`. The greedy `ANY /api/v1/posts/{proxy+}` key matches every one of
    # those sub-paths regardless of depth, because `{proxy+}` captures the whole
    # remainder rather than a single segment, so the depth never turns into
    # extra keys. What makes that safe is ownership, not shape: the domain owns
    # every path under both prefixes, so there is nothing under them that should
    # still reach the monolith.
    #
    # This is also why the three literal sibling paths that section 1 of the
    # plan flags for ordering, `/api/v1/posts/categories`, `/api/v1/posts/admin`
    # and the `/api/v1/posts/{slug}` catch-all, need no keys of their own. They
    # resolve inside the function, by FastAPI's declaration order in
    # backend/app/domains/content/posts.py, exactly as they do in the monolith.
    # Giving them separate gateway keys would move that disambiguation into API
    # Gateway for no benefit and would be the one way to get it wrong.
    #
    # `site-content` is a singleton and still gets both keys. Its only served
    # path is `/api/v1/site-content/`, so the `{proxy+}` key matches nothing the
    # application declares today unless it is what serves the trailing slash. It
    # stays either way: a future sub-path cannot then land on the monolith by
    # omission, and an unmatched greedy key costs one route resource and answers
    # from the domain's own 404 rather than from the monolith, which is the
    # behaviour this cut wants anyway.
    #
    # ANY rather than a method per route, as in cut 2: the domain owns every
    # method on both prefixes, GET and the admin writes alike, so four keys
    # stand in for all 14 routes and cannot drift when an operation is added.
    merge([
      for prefix in local.content_prefixes : {
        "ANY /api/v1/${prefix}"          = { integration = "content" }
        "ANY /api/v1/${prefix}/{proxy+}" = { integration = "content" }
      }
    ]...),
  )

  throttling_burst_limit = 200
  throttling_rate_limit  = 100

  # 7 days, matching the per-domain function log groups in lambda_domains.tf and
  # the retention the platform migration decision settled on. Section 3.5 puts
  # this change in the same file as the first cut, because the access log is
  # what a cut is verified against and both are now read the same way.
  access_log_retention_days = 7

  lambda_permission_statement_id = "AllowAPIGatewayInvoke"

  access_log_format = {
    requestId               = "$context.requestId"
    ip                      = "$context.identity.sourceIp"
    requestTime             = "$context.requestTime"
    httpMethod              = "$context.httpMethod"
    routeKey                = "$context.routeKey"
    path                    = "$context.path"
    status                  = "$context.status"
    responseLength          = "$context.responseLength"
    integrationErrorMessage = "$context.integrationErrorMessage"
    integrationLatency      = "$context.integrationLatency"
  }

  disable_execute_api_endpoint = local.staging_gate_enabled
  authorizer_id                = local.staging_gate_enabled ? one(module.staging_access_gate[*].http_api_authorizer_id) : null

  domain_name     = local.custom_domains_enabled ? local.api_host : null
  certificate_arn = module.api_certificate.certificate_arn
  # zone_id stays null: production writes api.webbpulse.com cross-account through aws.dns.
}
