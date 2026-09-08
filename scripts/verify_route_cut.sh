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
# `public` and `resume` are cut today. The other two are filled in by cuts 3 and
# 4 and are listed as empty so the script fails loudly with "no paths" instead
# of silently passing on an empty loop.
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
  # Cut 3.
  PATHS=()
  ;;
identity)
  # Cut 4.
  PATHS=()
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
    if [ "$code" = "200" ]; then
      break
    fi
    if [ "$attempt" -lt "$RETRIES" ]; then
      sleep 5
    fi
  done

  rm -f "$headers"
  trap - EXIT

  label="  ${path}"
  if [ "$code" != "200" ]; then
    echo "$label -> HTTP $code, served by '${served_by:-unknown}'  FAIL"
    FAILURES=$((FAILURES + 1))
    continue
  fi

  case "$served_by" in
  "$DOMAIN")
    echo "$label -> HTTP 200, served by '$DOMAIN'  OK"
    ;;
  "$MONOLITH")
    echo "$label -> HTTP 200, served by '$MONOLITH'  NOT CUT OVER"
    NOT_CUT=$((NOT_CUT + 1))
    ;;
  "")
    echo "$label -> HTTP 200, no $DOMAIN_HEADER header  FAIL"
    echo "      The function is running an image from before the header was"
    echo "      added. Redeploy the backend, then run this again."
    FAILURES=$((FAILURES + 1))
    ;;
  *)
    echo "$label -> HTTP 200, served by '$served_by'  FAIL"
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
  bare=$(curl -sS --max-time "$TIMEOUT" -o /dev/null -w '%{http_code}' \
    "${BASE_URL}${probe}" 2>/dev/null || echo 000)
  if [ "$bare" = "200" ]; then
    echo "Gate check: ${probe} returned 200 with no credential  FAIL"
    echo "  That route is past the access gate. Check that its routes entry"
    echo "  sets no authorization_type, so the module applies CUSTOM."
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
