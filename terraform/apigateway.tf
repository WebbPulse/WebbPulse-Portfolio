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
  source = "app.terraform.io/WebbPulse/platform-modules/aws//modules/http-api"

  # 2.9 for identity_jwt, identity_jwt_depends_on and the per route
  # require_identity_jwt flag, all three of which this file now uses. The
  # release is additive and every new default preserves current behaviour, so
  # the bump on its own is a no-op plan: what changes anything is the routes
  # marked below and var.identity_jwt_mode being something other than "off".
  version = "~> 2.9"

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

    # The identity standard's M1, and the one place in this map where the
    # paragraph at the top of `routes` does not hold. Read that paragraph first:
    # no entry above sets authorization_type, so every one of them takes the
    # module's CUSTOM default and sits behind the staging access gate, and it
    # says in as many words that setting NONE on any of them would punch a hole
    # straight past the gate.
    #
    # These two set it deliberately, and they are unconditional: no count,
    # present in every environment. They are what this product publishes about
    # itself, and terraform/identity.tf creates the signing key they publish
    # unconditionally to match.
    #
    # WHY THEY MUST BE ANONYMOUS, which is section 2.5 and the single most
    # likely way to get this deployment wrong. The JWT authorizer fetches both
    # documents itself, from API Gateway's own infrastructure, carrying no gate
    # cookie and no origin-verify header. M0 proved this is not only a
    # request-time fetch: it happens at CreateAuthorizer time, and the create
    # call fails outright with a BadRequestException naming the discovery URL
    # when either document does not answer. The JWKS is fetched in the same
    # second, from the same address, by following jwks_uri out of the discovery
    # document, so gating the JWKS fails the create call exactly as surely as
    # gating discovery does, and the error names only the discovery URL. When
    # M2 attaches an authorizer, these two routes already answering anonymously
    # is what makes that a first apply rather than a half-created stack.
    #
    # What they expose is a public key and a document saying where the public
    # key is, which is what every OIDC provider on the internet serves
    # anonymously by definition. The private half never leaves KMS. So this is
    # a hole in the gate in the literal sense, and an empty one.
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
    # Their paths sit under `/api/auth`, which is the issuer's own path, and not
    # at the API origin. This is the detail that is easy to get backwards.
    #
    # API Gateway appends `/.well-known/openid-configuration` to the configured
    # issuer with its path included. M0 proved it from the other direction: an
    # issuer of `https://api.staging.webbpulse.com` with no path produced a
    # create-time error quoting
    # `https://api.staging.webbpulse.com/.well-known/openid-configuration`.
    # local.identity_issuer is `https://<api host>/api/auth`, per the standard,
    # so the discovery document has to answer at
    # `/api/auth/.well-known/openid-configuration`.
    #
    # The JWKS follows from the discovery document rather than from a rule.
    # IdentitySettings builds the `jwks_uri` member as issuer plus
    # `/.well-known/jwks.json`, so the document this product serves advertises
    # `/api/auth/.well-known/jwks.json`, and M0's access log shows API Gateway
    # fetching whatever jwks_uri names rather than guessing a path. So the JWKS
    # key has to match the advertised URL, and these two keys are what
    # `app/composition/wiring.py` mounting the router at the issuer's path
    # produces. Putting either at the origin instead would serve a document
    # nothing fetches and leave the fetched path a 404.
    {
      "GET /api/auth/.well-known/jwks.json" = {
        integration        = "identity"
        authorization_type = "NONE"
      }
      "GET /api/auth/.well-known/openid-configuration" = {
        integration        = "identity"
        authorization_type = "NONE"
      }
    },

    # The identity function's own liveness probe, and the reason it needs a key
    # of its own rather than sharing `GET /health` above.
    #
    # `GET /health` is already taken: cut 1 routes it to `public`, whose handler
    # reads DynamoDB and reports on the database. One route key resolves to one
    # integration, so the identity function cannot also be reached at that path
    # from the gateway.
    #
    # It does not need to be. `build_identity_router` declares `/health` on the
    # router, and the router mounts at the issuer's path, so inside the identity
    # application the path is `/api/auth/health` and this key names it directly.
    # No rewriting and no second declaration: the key is the served path.
    #
    # It sits behind the gate, taking the module's CUSTOM default like every
    # ordinary route, and that is deliberate: a liveness probe is not something
    # API Gateway fetches on its own, so nothing about the authorizer's
    # create-time behaviour argues for making it anonymous, and section 2.5's
    # hole should stay exactly two documents wide. The Lambda Web Adapter's own
    # readiness check reaches the in-process `/health` directly on 127.0.0.1 and
    # never traverses the gateway, so gating this key costs the platform
    # nothing.
    #
    # Literal, GET, and no trailing slash.
    {
      "GET /api/auth/health" = { integration = "identity" }
    },

    # The identity standard's M2 flows: the six POST routes
    # `build_identity_router` mounts once the product supplies hooks and a
    # credential store. Like `GET /api/auth/health` above, each one is a
    # literal key naming the served path, because the router mounts at the
    # issuer's path and the issuer's path is `/api/auth`.
    #
    # None of them sets authorization_type, so each takes the module's default
    # exactly as the health key does: CUSTOM behind the staging access gate in
    # staging, and NONE in production where no gate authorizer exists. That is
    # the correct treatment rather than an omission. These are state changing
    # routes, so the `authorization_type = "NONE"` the two `.well-known`
    # documents carry would be wrong here: that hole exists only because API
    # Gateway fetches those two documents itself at CreateAuthorizer time, and
    # section 2.5 says it should stay exactly two documents wide.
    #
    # These routes are not behind the identity JWT authorizer either, and they
    # cannot be. An HTTP API route takes one authorizer and in staging the gate
    # already occupies that slot. It is also the wrong control for four of the
    # six: `register`, `login` and `refresh` are how a caller obtains a token in
    # the first place, so requiring one would make them unreachable. `password`
    # and `logout-all` do need an authenticated caller, and they get it inside
    # the application: both read the subject from the verified claims the
    # gateway forwards and refuse with NOT_AUTHENTICATED when there is none,
    # rather than trusting anything in the body.
    #
    # Literal, POST, and no trailing slash: a route key path segment may not be
    # empty, and a trailing slash fails at apply with a green plan.
    #
    # TWO OF THE SIX NOW CARRY require_identity_jwt, and the split is the one
    # the paragraph above already describes in prose. `password` and
    # `logout-all` are the two that need an authenticated caller, and both read
    # the subject from verified claims and answer NOT_AUTHENTICATED without
    # one, so marking them states at the gateway what the application already
    # refuses without. `register`, `login` and `refresh` are how a caller
    # obtains a token, so requiring one would make them unreachable.
    #
    # `logout` is the one that looks like it belongs with `logout-all` and does
    # not. It takes no access token at all: `webbpulse.identity.router` reads
    # the refresh cookie, ignores the Authorization header entirely, and always
    # answers 200 because signing out is idempotent and the caller's intent is
    # to end up signed out. Requiring an access token on it would break sign
    # out for exactly the caller whose access token has expired, which is the
    # common case for somebody signing out, while the refresh cookie that
    # actually carries the session is still valid. It stays open.
    {
      "POST /api/auth/register" = { integration = "identity" }
      "POST /api/auth/login"    = { integration = "identity" }
      "POST /api/auth/password" = {
        integration          = "identity"
        require_identity_jwt = true
      }
      "POST /api/auth/refresh" = { integration = "identity" }
      "POST /api/auth/logout"  = { integration = "identity" }
      "POST /api/auth/logout-all" = {
        integration          = "identity"
        require_identity_jwt = true
      }
    },

    # The identity standard's M3 email flows: the four POST routes
    # `build_identity_router` mounts once the product supplies an email sender
    # and an `identity-tokens` store, on the same rule the six above follow.
    # `terraform/ses.tf` creates the sending identity and the configuration set
    # and `terraform/lambda_domains.tf` passes them, which is what supplies the
    # sender.
    #
    # **Exactly the same authorizer treatment as the six above**, which means
    # `authorization_type` omitted and the module's CUSTOM default taken: the
    # staging access gate in staging, and NONE in production where no gate
    # authorizer exists. Not `authorization_type = "NONE"`. These are state
    # changing routes, and the anonymous hole exists only because API Gateway
    # fetches the two discovery documents from its own infrastructure at
    # `CreateAuthorizer` time with no cookie to present. Section 2.5 says it
    # should stay exactly two documents wide, and a test asserts it does.
    #
    # They are not behind the identity JWT authorizer either, and could not be
    # even if the gate's slot were free. All four are anonymous by design: a
    # person who cannot sign in is precisely who asks for a password reset, and
    # a person confirming an address has no token yet. Section 5.4 is why both
    # request routes answer 200 for any address, and the package's flow methods
    # return `None` on every path so a router cannot branch on the outcome even
    # by accident.
    #
    # `verify-email` and `verify-email/confirm` are two separate literal keys
    # rather than one greedy `verify-email/{proxy+}`. A greedy key would route
    # any future path under `verify-email/` to this function without anybody
    # declaring it, which is the by-omission widening the rest of this file
    # avoids. `POST /api/auth/reset` and `POST /api/auth/reset/confirm` are
    # distinct keys for the same reason.
    #
    # Literal, POST, and no trailing slash: a route key path segment may not be
    # empty, and a trailing slash fails at apply with a green plan.
    {
      "POST /api/auth/verify-email"         = { integration = "identity" }
      "POST /api/auth/verify-email/confirm" = { integration = "identity" }
      "POST /api/auth/reset"                = { integration = "identity" }
      "POST /api/auth/reset/confirm"        = { integration = "identity" }
    },

    # The identity standard's M4 MFA flows: the six POST routes
    # `build_identity_router` mounts once the product supplies a TOTP factor
    # store and a recovery code store alongside the identity-tokens store M3
    # already needed, with `totp_enabled` left at the package's default.
    # `terraform/identity.tf` creates the two tables and
    # `app/composition/identity.py` supplies the stores.
    #
    # **The same authorizer treatment as M2's six and M3's four**, which means
    # `authorization_type` omitted on every one of them and the module's CUSTOM
    # default taken: the staging access gate in staging, and NONE in production
    # where no gate authorizer exists. The anonymous surface stays exactly the
    # two discovery documents, and a test asserts it does.
    #
    # `POST /api/auth/login/totp` IS THE ONE WORTH READING TWICE, because it is
    # the route with two different authorization stories and it is easy to
    # conflate them.
    #
    # It must stay outside the **identity JWT authorizer**, and that is not a
    # preference. It is the second leg of a login, so its caller holds no access
    # token: what it carries is an MFA ticket whose `aud` is `<issuer>/mfa`
    # rather than local.identity_audience. A JWT authorizer configured with the
    # API audience rejects that ticket before the function ever sees it, which
    # would make every MFA login unfinishable, and the package's own router
    # docstring says so in as many words. It is the same reason `login`,
    # `register` and `refresh` cannot sit behind that authorizer: they are how a
    # caller obtains a token rather than a place to spend one.
    #
    # It stays **inside the staging access gate**, which is a different control
    # answering a different question. The gate is the fence around a non
    # production environment, not authentication, and somebody completing a
    # login in staging is somebody who already got through the fence. So this
    # key omits `authorization_type` exactly as `POST /api/auth/login` does, and
    # is pointedly not `authorization_type = "NONE"`.
    #
    # Nothing here attaches the identity JWT authorizer to anything. No route in
    # this map names one, module.identity is still called with http_api_id null,
    # and section 2.5's question about the gate occupying the single authorizer
    # slot is as open after this change as before it. The five routes that do
    # need an authenticated caller get one inside the application: each reads
    # the subject from the verified claims the gateway forwards and refuses with
    # NOT_AUTHENTICATED when there is none, rather than trusting a user id in a
    # body. That is what `change_password` and `logout-all` already do, and it
    # matters more here, because a user id in the body of `totp/enrol` would let
    # anybody enrol a factor on anybody's account.
    #
    # `POST /api/auth/login/totp` is a literal key and a sibling of
    # `POST /api/auth/login` rather than a child route of it. API Gateway
    # matches a literal key exactly, so the two coexist with neither shadowing
    # the other, and writing the parent as `POST /api/auth/login/` to
    # distinguish them is the mistake that plans green and fails at apply with
    # "Part of the given route key path is empty". The `totp/` trio is three
    # separate literal keys rather than one greedy `totp/{proxy+}`, for the same
    # reason `verify-email/confirm` is its own key: a greedy key routes any
    # future path under it to this function without anybody declaring it.
    #
    # Literal, POST, and no trailing slash on any of the six.
    #
    # FIVE OF THE SIX NOW CARRY require_identity_jwt, and the sixth is
    # `POST /api/auth/login/totp` for the reason spelled out at length above:
    # its caller holds an MFA ticket whose `aud` is `<issuer>/mfa` rather than
    # local.identity_audience, so any check configured with the API audience
    # refuses it and every MFA login becomes unfinishable. That is true of the
    # native JWT authorizer and equally true of the gate Lambda doing the same
    # verification, because both are configured from the same pair of values.
    # The paragraph above said this route must stay outside the identity JWT
    # authorizer; this is where that sentence becomes a flag not set.
    #
    # The other five all call `require_subject` in
    # `webbpulse.identity.router` and answer 401 NOT_AUTHENTICATED without a
    # verified subject, so the gateway is now refusing the same requests the
    # application already refused, one hop earlier. The application check stays
    # exactly where it is: nothing here replaces it.
    {
      "POST /api/auth/login/totp" = { integration = "identity" }
      "POST /api/auth/totp/enrol" = {
        integration          = "identity"
        require_identity_jwt = true
      }
      "POST /api/auth/totp/activate" = {
        integration          = "identity"
        require_identity_jwt = true
      }
      "POST /api/auth/totp/disable" = {
        integration          = "identity"
        require_identity_jwt = true
      }
      "POST /api/auth/recovery-codes" = {
        integration          = "identity"
        require_identity_jwt = true
      }
      "POST /api/auth/step-up" = {
        integration          = "identity"
        require_identity_jwt = true
      }
    },

    # The identity standard's M5 passkey flows: the seven routes
    # `build_identity_router` mounts when `passkeys_enabled` is on and the
    # product supplies both a `passkeys` store and a `webauthn_challenges`
    # store, plus the eighth route that mounts whatever those say. `terraform/identity.tf` creates the two tables and sets
    # `IDENTITY_PASSKEYS_ENABLED` true in staging;
    # `app/composition/identity.py` supplies the stores unconditionally.
    #
    # THESE KEYS WERE MISSING AND THAT WAS AN OUTAGE, not a latent gap. Section
    # 6 set `default_integration = null`, so there is no `$default` to fall
    # through to: a served path with no key is API Gateway's own 404 and reaches
    # no function at all. The identity function was mounting all seven of these
    # routes in staging while the gateway answered `{"message":"Not Found"}` to
    # every one of them, which is the exact failure
    # `backend/tests/entrypoints/test_gateway_routes.py` exists to catch and did
    # not, because its identity assertions were written per milestone and no
    # milestone set covered M5. The `_PACKAGE_*` sets added there now derive the
    # expected keys from the package's own path constants, so the next milestone
    # to mount routes without keys fails a test rather than shipping a 404.
    #
    # **The same authorizer treatment as M2, M3 and M4**, which means
    # `authorization_type` omitted on all seven and the module's CUSTOM default
    # taken: the staging access gate in staging, and NONE in production where no
    # gate authorizer exists. The anonymous surface stays exactly the two
    # discovery documents, and a test asserts it does.
    #
    # THE SPLIT ON require_identity_jwt IS FIVE AND TWO, and the package's own
    # module docstring draws it in the same place. The two `/login/passkey/`
    # routes are the passwordless login ceremony and their caller is by
    # definition not signed in yet: `options` is fetched by somebody with no
    # token at all, and `verify` carries a WebAuthn assertion rather than a
    # bearer token. Flagging either would make a passkey login unperformable,
    # which is `POST /api/auth/login` and `POST /api/auth/login/totp`'s
    # reasoning applied to a third way into an account. Both are rate limited
    # per IP by the package instead, at 30 per 15 minutes, which is the
    # substitute for an authorizer on an anonymous route.
    #
    # It is worth being precise about why these two differ from
    # `POST /api/auth/login/totp` even though all three are unflagged. The TOTP
    # leg carries an MFA ticket whose `aud` is `<issuer>/mfa`, so a check
    # configured with local.identity_audience actively REFUSES a valid ticket.
    # The passkey login legs carry no token of any kind, so the flag would
    # refuse them for having nothing to present. Different mechanisms, same
    # conclusion: neither can sit behind the identity JWT authorizer.
    #
    # The other five are account management and every one of them calls
    # `require_subject` in `webbpulse.identity.passkey_routes`, which reads the
    # subject from the verified claims and raises NOT_AUTHENTICATED without one.
    # Marking them states at the gateway what the application already refuses
    # without, one hop earlier, exactly as `totp/enrol` does. It matters as much
    # here as it does there: a `user_id` in a registration body would let
    # anybody enrol a passkey on anybody's account, and a credential is harder
    # to notice and harder to revoke than a password change.
    #
    # `PATCH` and `DELETE /api/auth/passkeys/{credential_id}` are the file's
    # first route keys carrying a path variable, and that is a supported route
    # key shape rather than a novelty: an HTTP API route key may contain a
    # `{name}` segment, and modules/http-api passes `var.routes` keys through to
    # `aws_apigatewayv2_route.route_key` verbatim as the `for_each` key, so the
    # module neither parses nor constrains them. A variable segment is not the
    # greedy `{proxy+}` this file avoids: it matches exactly one segment, so
    # these two keys claim `/api/auth/passkeys/<one id>` and nothing deeper, and
    # no future path under `passkeys/` is routed by omission.
    #
    # `GET /api/auth/passkeys` and the two item keys are three separate literal
    # keys rather than one greedy `passkeys/{proxy+}`, on the same rule
    # `verify-email/confirm` follows. `register/options` and `register/verify`
    # are likewise their own keys and sit below `passkeys/` without the
    # collection key shadowing them: API Gateway matches a full route before a
    # variable one, and `/api/auth/passkeys/register/options` has more segments
    # than `{credential_id}` can match anyway.
    #
    # THE EIGHTH KEY, `GET /api/auth/passkeys/availability`, IS THE ONE THAT
    # DOES NOT FOLLOW THE PARAGRAPHS ABOVE, and it is unflagged for a reason
    # none of the other seven share. Added by webbpulse-python 0.17.0 through
    # its own `register_passkey_availability`, it mounts in EVERY deployment,
    # including one with `passkeys_enabled` off and one supplying no stores at
    # all, where it answers `{"enabled": false, "passwordless": false}`. That is
    # deliberate package design on exactly the terms
    # `GET /api/auth/oauth/providers` in the M6 block below is designed: an
    # absent route is a 404 the sign-in page cannot tell apart from a routing
    # mistake, a gateway misconfiguration or a backend older than 0.17.0, and
    # the whole point of a discovery route is an answer the frontend can trust
    # in the negative. `{"enabled": false}` says "no passkeys, and I am sure".
    #
    # The other seven do not mount when they cannot work, because a route that
    # can only answer 503 is worse than an absent one. This one can always work,
    # so its key is unconditional here for the same reason all six OAuth keys
    # are: a key for a route the function has not mounted is harmless and gives
    # the function's own 404 rather than the gateway's, while a path with no key
    # is the outage the seven keys above were added to end.
    #
    # UNFLAGGED, and not on the two login legs' reasoning. Those two carry no
    # token because a caller mid sign-in has none to carry. This one is read by
    # a sign-in page that holds no token by definition and answers two booleans
    # derived from configuration: it touches no store, makes no call, is not
    # rate limited by the package, and holds nothing about any user. It is
    # `GET /api/auth/oauth/providers`'s twin in every respect, which is why it
    # is written in that key's style rather than this block's.
    #
    # `authorization_type` omitted, like every other identity key in this file.
    # Anonymous to the application and outside the staging access gate are two
    # different claims, and the anonymous surface stays exactly the two
    # discovery documents: somebody loading a sign-in page in staging is
    # somebody already through the fence.
    #
    # IT IS A LITERAL KEY UNDER `passkeys/` AND IT DOES NOT COLLIDE WITH
    # `{credential_id}`. `GET /api/auth/passkeys/availability` and
    # `PATCH`/`DELETE /api/auth/passkeys/{credential_id}` would match the same
    # segment shape, but they are different methods, and a route key is a method
    # and a path together: no GET key carries the variable, so nothing here is
    # shadowed in either direction. API Gateway prefers a literal segment over a
    # variable one in any case, which is the rule `register/options` already
    # relies on two paragraphs up.
    #
    # No trailing slash on any of the eight.
    {
      "GET /api/auth/passkeys/availability" = { integration = "identity" }
      "POST /api/auth/passkeys/register/options" = {
        integration          = "identity"
        require_identity_jwt = true
      }
      "POST /api/auth/passkeys/register/verify" = {
        integration          = "identity"
        require_identity_jwt = true
      }
      "POST /api/auth/login/passkey/options" = { integration = "identity" }
      "POST /api/auth/login/passkey/verify"  = { integration = "identity" }
      "GET /api/auth/passkeys" = {
        integration          = "identity"
        require_identity_jwt = true
      }
      "PATCH /api/auth/passkeys/{credential_id}" = {
        integration          = "identity"
        require_identity_jwt = true
      }
      "DELETE /api/auth/passkeys/{credential_id}" = {
        integration          = "identity"
        require_identity_jwt = true
      }
    },

    # The identity standard's M6 OAuth flows: the six routes
    # `build_identity_router` mounts for third party sign in.
    # `terraform/identity.tf` creates the `oauth-states` and `oauth-links`
    # tables and `app/composition/identity.py` supplies both stores.
    #
    # MISSING FOR THE SAME REASON M5's SEVEN WERE, with the same consequence: a
    # gateway 404 on every OAuth path while the function served them. It is what
    # `curl https://api.staging.webbpulse.com/api/auth/oauth/providers`
    # answering API Gateway's `{"message":"Not Found"}` proved from the outside.
    #
    # THE SIX DIVIDE UNEVENLY, and the division is not the one the paths
    # suggest. Five mount only when a provider is configured with a client id;
    # `GET /api/auth/oauth/providers` mounts in EVERY deployment through the
    # package's own `register_oauth_provider_discovery`, including one with no
    # OAuth at all, where it answers `{"providers": []}`. That is deliberate
    # package design rather than an accident: an absent route is a 404 the
    # frontend cannot distinguish from a routing mistake, and the sign-in page
    # needs an authoritative answer either way.
    #
    # A key for a route the function has not mounted is harmless and is the
    # right thing to declare. It makes the response the identity function's own
    # 404 rather than the gateway's, which is the same argument
    # `ANY /api/v1/admin` is kept on, and it means turning a provider on is a
    # workspace variable rather than a Terraform change plus a variable. All six
    # keys are therefore unconditional, matching how M3's and M4's keys are
    # written whether or not their feature flags are on.
    #
    # **The same authorizer treatment as every identity block above**:
    # `authorization_type` omitted throughout, so the staging access gate covers
    # all six in staging and nothing gates them in production. Not
    # `authorization_type = "NONE"` on `oauth/providers`, even though it is
    # anonymous to the application and read by a sign-in page that holds no
    # token. Anonymous to the application and outside the staging gate are two
    # different claims, and section 2.5's hole stays exactly two documents wide:
    # somebody loading a sign-in page in staging is somebody who is already
    # through the fence, exactly as with `POST /api/auth/login`.
    #
    # THE require_identity_jwt SPLIT IS THREE AND THREE, and it follows the
    # package's own table rather than the shape of the paths.
    #
    # Unflagged, because all three are legs of a browser navigation by a caller
    # who is not signed in:
    #
    #   `GET /oauth/providers`      read by the sign-in page, which has no token
    #                               by definition. Answers a constant derived
    #                               from configuration, touches no store and
    #                               holds nothing about any user.
    #   `GET /oauth/{provider}/start`
    #                               a top level browser navigation that answers
    #                               302 to the provider. A browser following a
    #                               link sends no Authorization header and there
    #                               is nowhere to put one, so flagging it would
    #                               refuse every sign in before it began. Its
    #                               `mode=link` variant does read a bearer token
    #                               when one is present, but that path is
    #                               reached through `POST /oauth/{provider}/link`
    #                               in practice and the route must stay usable
    #                               without one.
    #   `GET /oauth/callback`       the provider navigates the browser here with
    #                               `state` and `code`. The caller is the
    #                               provider's redirect and carries no token of
    #                               ours at all; authorization is the single use
    #                               state row the package spends before anything
    #                               else happens. Flagging it would break every
    #                               sign in on the return leg, which is the
    #                               worse half to break because the user has
    #                               already consented at the provider.
    #
    # Flagged, because all three are settings page calls made over `fetch` with
    # an Authorization header by a signed-in user:
    #
    #   `POST /oauth/{provider}/link`   starts a link for the authenticated
    #                                   caller and answers JSON rather than a
    #                                   redirect precisely because it is a
    #                                   `fetch` and not a navigation.
    #   `GET /oauth/links`              lists the caller's linked providers.
    #   `DELETE /oauth/{provider}/link` detaches one.
    #
    # All three call `require_subject` and refuse with NOT_AUTHENTICATED without
    # a verified subject, reading the subject from the claims rather than from a
    # body, so the gateway now refuses what the application already refused. The
    # application check stays exactly where it is.
    #
    # `POST` and `DELETE /api/auth/oauth/{provider}/link` are two entries on the
    # same path, which is two route keys because a route key is a method and a
    # path together. They are not `ANY`: the package declares exactly these two
    # methods there, and `ANY` would route a `PUT` to the function for a handler
    # that does not exist.
    #
    # `{provider}` is a single segment variable, on the same terms as
    # `{credential_id}` in M5's block above. `GET /api/auth/oauth/providers` and
    # `GET /api/auth/oauth/callback` are literal keys that would also be matched
    # by a hypothetical `GET /api/auth/oauth/{provider}`, which is why no such
    # key exists: the package declares neither, and API Gateway prefers the
    # literal in any case.
    #
    # No trailing slash on any of the six.
    {
      "GET /api/auth/oauth/providers"        = { integration = "identity" }
      "GET /api/auth/oauth/{provider}/start" = { integration = "identity" }
      "GET /api/auth/oauth/callback"         = { integration = "identity" }
      "POST /api/auth/oauth/{provider}/link" = {
        integration          = "identity"
        require_identity_jwt = true
      }
      "GET /api/auth/oauth/links" = {
        integration          = "identity"
        require_identity_jwt = true
      }
      "DELETE /api/auth/oauth/{provider}/link" = {
        integration          = "identity"
        require_identity_jwt = true
      }
    },

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

  # The native JWT authorizer, and ONLY in the native mode. Non-null here is
  # what makes the module create an aws_apigatewayv2_authorizer and move every
  # route marked require_identity_jwt above onto it; null leaves all seven
  # routes exactly where they are and publishes their keys in the
  # identity_jwt_route_keys output instead, which is what
  # terraform/staging_access_gate.tf reads.
  #
  # It is null in staging and it has to be. Every route on this API carries the
  # gate's REQUEST authorizer, an HTTP API route takes exactly one authorizer,
  # and a second one has no slot to occupy. var.identity_jwt_mode's own
  # validation refuses "native" in staging for that reason, so this expression
  # and that validation say the same thing from two directions.
  #
  # The issuer and the audience are local.identity_issuer and
  # local.identity_audience, the same two locals module.identity is configured
  # with in terraform/identity.tf and the same two the `iss` and `aud` claims
  # are stamped from. Byte identity with the signer is the whole requirement
  # here, so they are read rather than restated: a second spelling of either
  # string is a token that verifies nowhere.
  identity_jwt = local.identity_jwt_native_enforced ? {
    issuer   = local.identity_issuer
    audience = local.identity_audience
  } : null

  # What CreateAuthorizer cannot be ordered against by the resource graph alone.
  # The call synchronously fetches <issuer>/.well-known/openid-configuration
  # from outside AWS with none of our credentials, so the identity function has
  # to be deployed and answering before it runs. depends_on orders API calls
  # rather than their effects, which is why the module takes this as an input
  # and why the module's own README recommends two runs for a first apply:
  # routes and function, then the authorizer.
  #
  # Empty in every mode but native, because in the other two no authorizer is
  # created and there is nothing to order.
  identity_jwt_depends_on = local.identity_jwt_native_enforced ? [module.lambda_domain["identity"]] : []

  domain_name     = local.custom_domains_enabled ? local.api_host : null
  certificate_arn = module.api_certificate.certificate_arn
  # zone_id stays null: production writes api.webbpulse.com cross-account through aws.dns.
}
