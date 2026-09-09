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
# ran through this file. Each cut added route keys for one domain and the
# monolith kept everything else through $default. All four cuts are applied and
# the monolith is retired, so there is no $default and no fall-through left:
# every route key below names the domain function that serves it, and a path no
# key matches gets API Gateway's own 404. The cuts and the retirement are
# recorded in docs/migration/cutover-log.md.
# ---------------------------------------------------------------------------

locals {
  # Every deployable domain, in cut order. A domain belongs here only once
  # apigateway.tf's routes map names it: the http-api module's
  # every_integration_is_routed check fails the plan on an integration no route
  # can reach, so this list and the routes map below move together.
  #
  # Cut 1 was `public`, cut 2 `resume`, cut 3 `content`, cut 4 `identity`. With
  # the monolith retired this list is the whole integrations map rather than the
  # part of it that had been carved off, so it now has to equal
  # keys(local.lambda_domains) exactly: a domain missing from here has no
  # integration and no route at all, where before the retirement it would still
  # have been served by the monolith on $default.
  routed_lambda_domains = ["public", "resume", "content", "identity"]

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

  # The four per-domain functions from lambda_domains.tf, and nothing else. The
  # `legacy` entry that named the monolith is gone with it; the entries are
  # generated from module.lambda_domain rather than written out one at a time,
  # so a domain added to local.lambda_domains cannot be left without an
  # integration here.
  #
  # The module's every_integration_is_routed check refuses an integration
  # nothing can reach, which is what kept each domain out of this map until its
  # own cut and is now what keeps this map and the routes map in step.
  #
  # Every statement id is derived by the module as
  # "AllowAPIGatewayInvoke-<domain>", because with default_integration null
  # there is no integration that takes var.lambda_permission_statement_id
  # verbatim. That is the id each of the four permissions already carries: they
  # were created after `legacy` had claimed the bare id, so retiring `legacy`
  # renames none of them and destroys only its own permission.
  integrations = {
    for name in local.routed_lambda_domains : name => {
      lambda_function_name = module.lambda_domain[name].function_name
      lambda_invoke_arn    = module.lambda_domain[name].invoke_arn
    }
  }

  # No $default. Section 6's retirement step, and the module's own words for it:
  # "Setting default_integration = null creates no $default route at all, so
  # anything the explicit routes do not match gets a 404 from API Gateway. That
  # is the end state of a finished migration, not somewhere to be during one."
  #
  # It is null rather than a domain on purpose. Pointing $default at `public`
  # would keep a fall-through working, and a fall-through working is exactly
  # what the strangler spent four cuts making impossible to rely on: a path that
  # no route key matches would answer 200-shaped from a function that does not
  # own it, or 404 from a function whose 404 is indistinguishable from a routing
  # mistake. With null, an unmatched path is API Gateway's own 404 with no
  # X-WebbPulse-Domain header, which is a distinct and readable signal, and it
  # is the signal scripts/verify_route_cut.sh now keys its fall-through check
  # off. It also costs nothing to reverse: naming a domain here is a one line
  # edit if the 404s ever turn out to be wrong.
  #
  # The routes map below has to be exhaustive for this to be correct, and
  # backend/tests/entrypoints/test_gateway_routes.py is what proves it is: it
  # asserts every path the four applications declare is matched by some key.
  # The four documentation paths are the deliberate exception, section 9
  # question 4 of the plan, and they 404 here rather than being routed.
  default_integration = null

  # No authorization_type is set on any entry below, which means the module's
  # own choice, CUSTOM whenever authorizer_id is set, so every one of them stays
  # behind the staging access gate. Setting NONE on any of them, including on a
  # read-only GET to make a probe simpler, would punch a hole straight past the
  # gate. With $default gone these are the only routes on the API, so this is
  # the whole of its authorization surface.
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
    # every collection after each deploy and fails if either one is not answered
    # by this domain's own function.
    #
    # **That probe stopped being a warning and became an outage check when the
    # monolith was retired.** While $default existed, a trailing-slash request
    # that matched neither key fell through to the monolith, which served it
    # correctly, so the probe reported a routing mistake against a surface that
    # still worked. There is no $default now: a request neither key matches gets
    # API Gateway's own 404 and the caller gets nothing. The keys below are
    # unchanged and the probes have passed on every deploy since cut 2, so the
    # empirical answer is in hand; what changed is the cost of it being wrong.
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

    # Cut 4. `identity`: the whole `/api/v1/admin` prefix, in two keys. This is
    # the last cut, and the smallest one by application surface: the domain
    # serves exactly one route, `POST /api/v1/admin/login`
    # (backend/app/domains/identity/router.py declares a bare `POST /login`, and
    # the `/admin` prefix comes from the descriptor's `router_prefix` in
    # backend/app/composition/wiring.py rather than from the router itself).
    #
    # Written literally rather than generated from a list. Cuts 2 and 3 each
    # looped over a local because they had five collections and two prefixes to
    # cover; `identity` has one prefix, so a `local.identity_prefixes` list of
    # one element would be indirection with nothing to factor out.
    #
    # The bare key and the greedy key still both appear, but their roles are the
    # reverse of the earlier cuts and it is worth being precise about which one
    # is load-bearing.
    #
    # `ANY /api/v1/admin/{proxy+}` is the key that carries the traffic. The only
    # served path is `/api/v1/admin/login`, one segment below the prefix, so the
    # greedy key matches it under any reading of route selection: the remainder
    # `login` is non-empty, which is the one property the empty-remainder
    # question from cuts 2 and 3 left open. Nothing about this cut depends on
    # that open question, which makes it the least uncertain of the four.
    #
    # `ANY /api/v1/admin` is the bare key, and here it matches nothing the
    # application declares. There is no route at the prefix root: the domain has
    # no `GET /` the way `resume`'s collections and `content`'s prefixes do, so
    # `/api/v1/admin` and `/api/v1/admin/` are both 404s from the identity
    # function. It is kept anyway, for the same reason `site-content` keeps a
    # greedy key that matches nothing today: the prefix belongs to this domain,
    # so a request to its root should answer from the domain's own 404 rather
    # than fall through to the monolith on `$default`, and a future route added
    # at the root cannot then be left on the monolith by omission.
    #
    # ANY rather than POST. The one route today is a POST, so `POST
    # /api/v1/admin/{proxy+}` would cover it exactly and nothing else. `ANY` is
    # still the right key for the same reason it was in cuts 2 and 3: the domain
    # owns every method on this prefix, so a GET to `/api/v1/admin/login` should
    # answer 405 from `identity` rather than be routed to the monolith, which
    # would serve it from its own copy of the same endpoint and make the cut
    # look complete while half of it was not. This one matters more than it did
    # for the earlier cuts, because it is what the verify script's GET probes
    # actually observe: they read the domain header off a 405, which only exists
    # if the method reached this function at all.
    {
      "ANY /api/v1/admin"          = { integration = "identity" }
      "ANY /api/v1/admin/{proxy+}" = { integration = "identity" }
    },

    # The identity standard's M0 spike, and the one place in this map where the
    # paragraph at the top of `routes` does not hold. Read that paragraph first:
    # no entry above sets authorization_type, so every one of them takes the
    # module's CUSTOM default and sits behind the staging access gate, and it
    # says in as many words that setting NONE on any of them would punch a hole
    # straight past the gate.
    #
    # These two entries set it deliberately, and they are gated on
    # local.identity_spike_enabled, so with the spike off this merge contributes
    # an empty map and the authorization surface is exactly what the paragraph
    # describes.
    #
    # Why they have to override it at all: API Gateway allows at most one
    # authorizer per route. The gate's CUSTOM authorizer is applied to every
    # route through the module's var.authorizer_id, so a route cannot be behind
    # the gate and behind the JWT authorizer at once. Section 2.5 of
    # docs/identity-standard.md records that as a blocker; the http-api module's
    # per-route authorization_type and authorizer_id override is the way through
    # it, and the two keys here are the first use of the type override.
    #
    # The spike's third key, `GET /api/identity/spike/whoami`, is deliberately
    # NOT here. It is a standalone aws_apigatewayv2_route in identity_spike.tf,
    # because it is the one route that names the JWT authorizer and the
    # authorizer cannot be created until these two keys already answer.
    #
    # The reason is an ordering constraint the first apply discovered the hard
    # way. CreateAuthorizer on an HTTP API validates the issuer synchronously:
    # API Gateway fetches <issuer>/.well-known/openid-configuration and refuses
    # the call with BadRequestException, "Issuer must have a valid discovery
    # endpoint", if it does not get a discovery document back. So the two keys
    # below and the identity function serving them have to exist before the
    # authorizer does.
    #
    # A whoami entry in this map would reference the authorizer's id, which
    # makes every route in the map wait on the authorizer, which waits on a
    # discovery document only those routes can serve. The first apply
    # (run-Yj1PJz22kVW7NM4p) failed exactly there: the authorizer errored and
    # all three routes were skipped, leaving /.well-known/openid-configuration a
    # gateway 404. Keeping whoami out of the map is what breaks that knot.
    #
    # The two `.well-known` keys are NONE, and that is not a convenience. The
    # JWT authorizer fetches the issuer's key material itself, from API
    # Gateway's own infrastructure, carrying no gate cookie and no origin-verify
    # header. If those two paths sat behind the gate the authorizer would get
    # the gate's 401 instead of a JWKS, could not build a verification key, and
    # would fail closed on every request to the protected route below, with the
    # cause visible nowhere except by noticing the JWKS was never fetched. They
    # have to be reachable anonymously for the design to work at all, which is
    # also true of the real thing at M2, not just of this spike.
    #
    # What they expose is a public key and a document listing where the public
    # key is, which is what every OIDC provider on the internet serves
    # anonymously by definition. There is no private key material behind either
    # path: the private half never leaves KMS. So this is a hole in the gate in
    # the literal sense, and an empty one.
    #
    # Both keys are GET and both are literal, with no `{proxy+}`. That is
    # narrower than every other entry in this map on purpose: the exemption
    # should cover exactly the two documents the authorizer needs and nothing
    # else the identity function serves. A greedy key under `/.well-known/`
    # would exempt any future path there too, which is precisely the kind of
    # by-omission widening the rest of this file is written to avoid. Neither
    # key ends in a slash, which is not a style choice either: a route key path
    # segment may not be empty, and cut 3's block above records the
    # BadRequestException that proves it.
    #
    # The paths are at the API origin rather than under `/api/v1/`, because RFC
    # 8615 puts `.well-known` at the root of the origin and the authorizer
    # derives them from the issuer, which is the origin. That is why the
    # application mounts webbpulse.identity's router with no prefix.
    #
    local.identity_spike_enabled ? {
      "GET /.well-known/jwks.json" = {
        integration        = "identity"
        authorization_type = "NONE"
      }
      "GET /.well-known/openid-configuration" = {
        integration        = "identity"
        authorization_type = "NONE"
      }
    } : {},
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
