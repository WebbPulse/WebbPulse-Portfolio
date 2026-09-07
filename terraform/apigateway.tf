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
  # Cut 1 is `public`, cut 2 is `resume`. Cuts 3 and 4 append content and
  # identity.
  routed_lambda_domains = ["public", "resume"]

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
  # so the two domains still waiting for their cut are deliberately not listed
  # yet: they arrive with their routes in cuts 3 and 4.
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
    # `/api/v1/projects/` is genuinely unspecified:
    #
    #   - The routing doc's precedence list (full match, then greedy variable,
    #     then $default) has no trailing-slash or empty-remainder example, and
    #     nothing in the HTTP API documentation says whether a trailing slash is
    #     normalised away before route selection.
    #   - Whether `{proxy+}` can capture an empty remainder is likewise
    #     undocumented for HTTP APIs. The v1 REST API doc describes
    #     `/parent/{proxy+}` as standing for `/parent/*`, which reads as
    #     requiring a non-empty remainder, but that sentence is not restated for
    #     v2 and carrying it across is an inference.
    #
    # So the behaviour is not something to depend on in either direction. A full
    # match takes documented priority over a greedy one, which makes the literal
    # `ANY /api/v1/projects/` key safe to add and removes the ambiguity: the
    # collection GET the site's front page depends on lands on `resume` whatever
    # API Gateway does with the slash. Without it, the failure mode is the quiet
    # one, a cut that applies cleanly while its collection reads keep being
    # answered by the monolith through $default.
    #
    # The bare key is not redundant either: the frontend's getProjects(true)
    # emits `/projects?featured_only=true/`, whose path component is the bare
    # `/api/v1/projects` with the slash inside the query string
    # (frontend/src/services/api.ts), and TrailingSlashMiddleware is what makes
    # that reach the handler once the request arrives.
    #
    # ANY rather than a method per route. The 25 routes are five methods across
    # five collections and the domain owns every method on its prefixes, so ANY
    # names them in three keys instead of fifteen and cannot drift when a sixth
    # operation is added to build_crud_router. It also keeps an unsupported
    # method answering from the domain's own 405 rather than from the monolith.
    merge([
      for collection in local.resume_collections : {
        "ANY /api/v1/${collection}"          = { integration = "resume" }
        "ANY /api/v1/${collection}/"         = { integration = "resume" }
        "ANY /api/v1/${collection}/{proxy+}" = { integration = "resume" }
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
