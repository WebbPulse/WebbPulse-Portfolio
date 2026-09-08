#!/usr/bin/env bash
#
# Verify that one domain's routes were actually cut over to that domain's
# function, rather than still falling through to the monolith on $default.
#
# Section 6 of docs/migration/pilot-split-plan.md, "Verifying a route flip on
# staging". Each cut in section 3.5 moves a set of route keys off the monolith,
# and the failure this script exists to catch is the quiet one: a cut that
# applies cleanly, returns 200, and changes nothing, because the route key did
# not match and API Gateway sent the request to $default after all. A 200 alone
# cannot tell those apart. The X-WebbPulse-Domain response header can.
#
#   scripts/verify_route_cut.sh <env> <domain>
#
#     env      staging or production
#     domain   public, resume, content or identity
#
# How it decides
# --------------
# Every application stamps X-WebbPulse-Domain on its responses
# (backend/app/core/middleware.py). A per-domain function reports its own name;
# both whole-surface roots, including the deployed monolith that serves
# $default, report "monolith". So for each path this script expects:
#
#   X-WebbPulse-Domain: <domain>   the cut worked
#   X-WebbPulse-Domain: monolith   the route fell through to $default
#   (absent)                       an older image that predates the header, or
#                                  an unhandled 500, which Starlette answers
#                                  outside every user middleware
#
# The header is the primary signal because it is synchronous and needs no
# CloudWatch read. The access log's routeKey field says the same thing and is
# the cross-check to reach for when a response looks wrong; the log group is
# /aws/apigateway/webbpulse-<env>-api.
#
# The status code is not the signal, and cut 4 is where that distinction starts
# to matter. What this script asks is "which function answered", and the header
# answers it on an error response just as well as on a 200: a 405 carrying
# X-WebbPulse-Domain: identity proves the request reached the identity function,
# which is the whole question. The status is only used to tell a real answer
# apart from a cold-start blip worth retrying, so each domain declares the codes
# it expects rather than every domain being held to 200.
#
# The staging access gate
# -----------------------
# Behind the gate the API host answers only an OPTIONS preflight, a request
# carrying the origin-verify header, or one carrying valid CloudFront signed
# cookies. A bare curl gets the Cognito redirect instead of the API, which would
# read here as a failed cut when it is really a missing credential.
#
# Nothing is embedded in this file. Supply one of:
#
#   WEBBPULSE_ORIGIN_VERIFY   the origin-verify header value. What CI uses.
#   WEBBPULSE_GATE_COOKIE     a Cookie header value, for a browser session.
#
# Neither is needed against an environment with no gate. To read the header
# value from SSM yourself, with credentials that allow it:
#
#   export WEBBPULSE_ORIGIN_VERIFY=$(aws ssm get-parameter --with-decryption \
#     --name /webbpulse-staging/access-gate/origin-verify \
#     --query Parameter.Value --output text)
#
# In CI, mask it with ::add-mask:: before it can reach a log, the way
# deploy-backend.yml already does.
#
# Override the host with WEBBPULSE_API_BASE_URL when the environment is not on
# its custom domain, for example a staging profile serving on the execute-api
# hostname.

set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage: scripts/verify_route_cut.sh <env> <domain>

  env      staging | production
  domain   public | resume | content | identity

Environment:
  WEBBPULSE_ORIGIN_VERIFY   origin-verify header value for the staging gate
  WEBBPULSE_GATE_COOKIE     Cookie header value, as an alternative to the above
  WEBBPULSE_API_BASE_URL    override the API base URL entirely
  WEBBPULSE_CURL_TIMEOUT    per request timeout in seconds (default 20)
  WEBBPULSE_RETRIES         attempts per path (default 5)
USAGE
  exit 2
}

[ $# -eq 2 ] || usage

ENV_NAME=$1
DOMAIN=$2

case "$ENV_NAME" in
staging | production) ;;
*)
  echo "Unknown environment: $ENV_NAME" >&2
  usage
  ;;
esac

# The paths each cut moves, kept in the same order as section 3.5's routes map
# so the two can be read side by side. A path listed here must appear in
# terraform/apigateway.tf's routes map for that domain, or this script will
# correctly report it as still on the monolith.
#
# All four domains are cut as of cut 4, so every case below is populated and
# the "no paths" guard is now unreachable. It stays as a guard rather than
# being deleted: a future domain added to the case with an empty list should
# fail loudly rather than silently pass on an empty loop.
#
# EXPECTED_CODES is the set of HTTP status codes that count as "the function
# answered" for this domain, as a space separated list. It defaults to 200,
# which is what cuts 1 to 3 all want because every path they probe is an
# unauthenticated GET that really does return a body. Cut 4 overrides it: see
# the identity case for why.
EXPECTED_CODES="200"

case "$DOMAIN" in
public)
  PATHS=(/health / /sitemap.xml /robots.txt)
  ;;
resume)
  # Cut 2. Two keys per collection in the routes map, bare and {proxy+}. A
  # trailing-slash key is not legal: API Gateway rejected "ANY /api/v1/<c>/"
  # with "Part of the given route key path is empty" on the first cut 2 apply.
  #
  # The collection path this application serves carries a trailing slash, and
  # AWS does not document whether "ANY /api/v1/projects" or
  # "ANY /api/v1/projects/{proxy+}" matches it: nothing says a trailing slash is
  # normalised before route selection, and nothing says a greedy variable can
  # capture an empty remainder. The trailing-slash probe below is what settles
  # that against the real gateway. If it reports "monolith", the routes map is
  # not wrong, the application is: the fix is serving the bare collection path.
  #
  # The bare form is probed too. It is what the frontend's getProjects(true)
  # actually requests: it emits /projects?featured_only=true/, whose path
  # component is the bare collection with the slash inside the query string.
  #
  # Item paths are deliberately not probed. Ids come from the COUNTER#
  # allocator in backend/app/db/repository.py, so they differ between staging
  # and production and no literal id is safe to hard code here. The
  # {proxy+} key that serves them is exercised by the deploy workflow's own
  # requests instead. GET only: every other method on these prefixes writes.
  PATHS=(
    /api/v1/projects/
    /api/v1/projects
    /api/v1/experience/
    /api/v1/experience
    /api/v1/skills/
    /api/v1/skills
    /api/v1/education/
    /api/v1/education
    /api/v1/certifications/
    /api/v1/certifications
  )
  ;;
content)
  # Cut 3. Two mounted prefixes, `posts` and `site-content`, two keys each in
  # the routes map, and both slash forms of both prefixes probed here.
  #
  # Both forms are probed because which key serves the trailing slash is an
  # open question that only the real gateway can answer. Each router declares a
  # route at `/`, so /api/v1/posts/ and /api/v1/site-content/ are paths the
  # application really serves, and the routes map cannot name them directly:
  # API Gateway rejects a route key with a trailing slash outright, which cut
  # 2's apply found the hard way with "BadRequestException: Part of the given
  # route key path is empty". So the trailing slash is served by either the
  # bare key or the greedy one, AWS documents neither case, and these probes
  # are what establish which. Both are expected to report `content`; a trailing
  # slash reporting `monolith` would mean neither key matches it and the cut is
  # incomplete.
  #
  # GET only. Every other method on these prefixes writes, and the two GETs
  # listed are the domain's unauthenticated reads: /api/v1/posts/ is the
  # published post list and /api/v1/site-content/ is the singleton the front
  # page renders from.
  #
  # The deeper posts paths are deliberately not probed, and there are two
  # separate reasons rather than one.
  #
  #   - Item paths carry ids and slugs that differ per environment.
  #     /api/v1/posts/{slug} and /api/v1/posts/category/{category_slug} need
  #     content that exists in that environment, and /api/v1/posts/admin/
  #     {post_id} ids come from the COUNTER# allocator in
  #     backend/app/db/repository.py, so no literal is safe to hard code here.
  #   - The /admin paths require an admin bearer token on top of the gate
  #     credential, so an unauthenticated GET would answer 401 from the domain
  #     and fail the HTTP 200 check while telling us nothing about routing.
  #
  # Both sets are served by the ANY /api/v1/posts/{proxy+} key. That key is
  # covered instead by backend/tests/entrypoints/test_gateway_routes.py, which
  # asserts in CI that every path the content application declares is matched
  # by some content route key, and by the admin panel's own traffic.
  PATHS=(
    /api/v1/posts/
    /api/v1/posts
    /api/v1/site-content/
    /api/v1/site-content
  )
  ;;
identity)
  # Cut 4. One prefix, /api/v1/admin, two keys in the routes map, and both
  # slash forms of the prefix plus both slash forms of the served route probed
  # here.
  #
  # This is the one domain whose probes cannot expect a 200, and the reason is
  # the domain's shape rather than anything about routing. `identity` serves
  # exactly one route, POST /api/v1/admin/login
  # (backend/app/domains/identity/router.py). There is no GET anywhere under
  # this prefix and no route at the prefix root at all, so:
  #
  #   GET /api/v1/admin/login  -> 405, from the identity function
  #   GET /api/v1/admin        -> 404, from the identity function
  #
  # Both are the *correct* answers and both prove the cut worked, because both
  # carry X-WebbPulse-Domain: identity. A request that fell through to $default
  # would carry `monolith` instead, and the monolith declares the same single
  # POST route, so it would answer the same 404s and 405s with a different
  # header. The header is what separates them; the status tells us nothing here
  # and cannot be allowed to fail the run.
  #
  # Hence EXPECTED_CODES below. 404 and 405 are the real expected answers; 200
  # stays in the set so that adding a GET under this prefix later does not
  # require editing this line to keep the script honest.
  #
  # The login route is deliberately probed with GET rather than POST. A POST
  # would exercise the real login handler: it would touch the rate limiter in
  # backend/app/core/login_limiter.py, which is keyed on client IP, so a CI job
  # running on every deploy would spend the deploy pipeline's own IP budget of
  # failed attempts and could lock out a real login from the same egress
  # address. A GET reaches the same route key, gets the same routing verdict
  # from the same function, and touches no application state at all.
  #
  # Both slash forms of both paths, as in cuts 2 and 3, though the open
  # question those cuts were probing does not arise here. `/api/v1/admin/login`
  # sits one segment below the prefix, so the greedy key matches it with a
  # non-empty remainder under any reading. The trailing-slash forms are probed
  # anyway because they are cheap and they pin the bare key's behaviour: a
  # /api/v1/admin/ that reported `monolith` would mean the prefix root is still
  # falling through, which is exactly what the bare key exists to prevent.
  PATHS=(
    /api/v1/admin/login
    /api/v1/admin/login/
    /api/v1/admin
    /api/v1/admin/
  )
  EXPECTED_CODES="200 404 405"
  ;;
*)
  echo "Unknown domain: $DOMAIN" >&2
  usage
  ;;
esac

if [ ${#PATHS[@]} -eq 0 ]; then
  echo "No paths are defined for domain '$DOMAIN' yet." >&2
  echo "That cut has not landed; add its paths here when it does." >&2
  exit 2
fi

if [ -n "${WEBBPULSE_API_BASE_URL:-}" ]; then
  BASE_URL=${WEBBPULSE_API_BASE_URL%/}
elif [ "$ENV_NAME" = "production" ]; then
  BASE_URL=https://api.webbpulse.com
else
  BASE_URL=https://api.staging.webbpulse.com
fi

TIMEOUT=${WEBBPULSE_CURL_TIMEOUT:-20}
RETRIES=${WEBBPULSE_RETRIES:-5}

# Gate credentials. The header is preferred because it is what the deploy
# workflow already uses and it needs no browser.
GATE_ARGS=()
if [ -n "${WEBBPULSE_ORIGIN_VERIFY:-}" ]; then
  GATE_ARGS=(-H "x-origin-verify: ${WEBBPULSE_ORIGIN_VERIFY}")
  echo "Using the origin-verify header for the access gate."
elif [ -n "${WEBBPULSE_GATE_COOKIE:-}" ]; then
  GATE_ARGS=(-H "cookie: ${WEBBPULSE_GATE_COOKIE}")
  echo "Using the supplied gate cookie."
elif [ "$ENV_NAME" = "staging" ]; then
  echo "Warning: no WEBBPULSE_ORIGIN_VERIFY and no WEBBPULSE_GATE_COOKIE." >&2
  echo "If the staging access gate is enabled every request below will be" >&2
  echo "answered by the gate rather than the API, and will report as a" >&2
  echo "failure that is really a missing credential." >&2
fi

DOMAIN_HEADER=x-webbpulse-domain
MONOLITH=monolith

# Is this status code one the domain under test expects? Word matched against
# EXPECTED_CODES so that "40" never matches "404".
is_expected_code() {
  case " $EXPECTED_CODES " in
  *" $1 "*) return 0 ;;
  *) return 1 ;;
  esac
}

echo "Verifying the '$DOMAIN' cut against $BASE_URL"
echo

FAILURES=0
NOT_CUT=0

# Print one header's value from a curl -D dump. Header names are matched case
# insensitively because HTTP/2 lowercases them and HTTP/1.1 does not have to.
header_value() {
  awk -v want="$1" '
    BEGIN { IGNORECASE = 1 }
    tolower($1) == tolower(want) ":" {
      sub(/^[^:]*:[ \t]*/, "")
      sub(/\r$/, "")
      print
    }
  ' "$2" | tail -n1
}

for path in "${PATHS[@]}"; do
  url="${BASE_URL}${path}"
  headers=$(mktemp)
  # shellcheck disable=SC2064
  trap "rm -f '$headers'" EXIT

  code=000
  served_by=""
  for attempt in $(seq 1 "$RETRIES"); do
    : >"$headers"
    code=$(curl -sS --max-time "$TIMEOUT" -o /dev/null -D "$headers" \
      -w '%{http_code}' "${GATE_ARGS[@]}" "$url" 2>/dev/null || echo 000)
    served_by=$(header_value "$DOMAIN_HEADER" "$headers")
    # A cold start on a freshly created image can 502 or 503 for a moment. A
    # wrong route does not fix itself, so retrying only helps the transient
    # case and costs nothing in the case this script is really checking.
    if is_expected_code "$code"; then
      break
    fi
    if [ "$attempt" -lt "$RETRIES" ]; then
      sleep 5
    fi
  done

  rm -f "$headers"
  trap - EXIT

  label="  ${path}"
  if ! is_expected_code "$code"; then
    echo "$label -> HTTP $code, served by '${served_by:-unknown}'  FAIL"
    echo "      Expected one of: $EXPECTED_CODES"
    FAILURES=$((FAILURES + 1))
    continue
  fi

  case "$served_by" in
  "$DOMAIN")
    echo "$label -> HTTP $code, served by '$DOMAIN'  OK"
    ;;
  "$MONOLITH")
    echo "$label -> HTTP $code, served by '$MONOLITH'  NOT CUT OVER"
    NOT_CUT=$((NOT_CUT + 1))
    ;;
  "")
    echo "$label -> HTTP $code, no $DOMAIN_HEADER header  FAIL"
    echo "      The function is running an image from before the header was"
    echo "      added. Redeploy the backend, then run this again."
    FAILURES=$((FAILURES + 1))
    ;;
  *)
    echo "$label -> HTTP $code, served by '$served_by'  FAIL"
    echo "      Expected '$DOMAIN'. Another domain answering this path means"
    echo "      two routes claim it, or the routes map names the wrong key."
    FAILURES=$((FAILURES + 1))
    ;;
  esac
done

echo

# The authorizer check from section 6. It is deliberately separate from the loop
# above: a route created with authorization_type = NONE is a hole straight past
# the gate, and it is invisible to a check that always sends the credential.
if [ "$ENV_NAME" = "staging" ] && [ ${#GATE_ARGS[@]} -gt 0 ]; then
  probe=${PATHS[0]}
  headers_gate=$(mktemp)
  bare=$(curl -sS --max-time "$TIMEOUT" -o /dev/null -D "$headers_gate" \
    -w '%{http_code}' "${BASE_URL}${probe}" 2>/dev/null || echo 000)
  gate_served_by=$(header_value "$DOMAIN_HEADER" "$headers_gate")
  rm -f "$headers_gate"

  # What a hole looks like has to be stated in terms of the application header,
  # not the status code. The original check read "a 200 without a credential is
  # a hole", which is right for every path cuts 1 to 3 probe because those all
  # return 200 when they are reached. It is wrong for identity: PATHS[0] here is
  # a GET against a POST-only route, so a route created with
  # authorization_type = NONE would answer 405 and sail past a 200 test while
  # being exactly the hole this check exists to find.
  #
  # The reliable signal is the same one the loop above uses. If the request
  # reached the application at all it carries X-WebbPulse-Domain, whatever the
  # status; the gate's own rejection is a Cognito redirect or a 401 from the
  # authorizer and carries no such header. So: header present means the gate did
  # not stop it.
  if [ -n "$gate_served_by" ]; then
    echo "Gate check: ${probe} reached '$gate_served_by' with no credential  FAIL"
    echo "  That route is past the access gate: it answered HTTP $bare and"
    echo "  stamped $DOMAIN_HEADER, so the request reached the application."
    echo "  Check that its routes entry sets no authorization_type, so the"
    echo "  module applies CUSTOM."
    FAILURES=$((FAILURES + 1))
  else
    echo "Gate check: ${probe} without a credential returned HTTP $bare  OK"
  fi
fi

echo
if [ "$FAILURES" -gt 0 ]; then
  echo "FAILED: $FAILURES path(s) did not verify."
  exit 1
fi
if [ "$NOT_CUT" -gt 0 ]; then
  echo "NOT CUT OVER: $NOT_CUT path(s) are still served by the monolith."
  echo "The Terraform apply has not landed, or the routes map does not name"
  echo "these paths. Cross-check routeKey in /aws/apigateway/webbpulse-${ENV_NAME}-api."
  exit 1
fi

echo "All ${#PATHS[@]} '$DOMAIN' path(s) are served by the '$DOMAIN' function."
