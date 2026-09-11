#!/usr/bin/env bash

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

EXPECTED_CODES="200"

case "$DOMAIN" in
public)
  PATHS=(/health / /sitemap.xml /robots.txt)
  ;;
resume)
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
  PATHS=(
    /api/v1/posts/
    /api/v1/posts
    /api/v1/site-content/
    /api/v1/site-content
  )
  ;;
identity)
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
UNROUTED=0

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
  if [ "$code" = "404" ] && [ -z "$served_by" ]; then
    echo "$label -> HTTP 404, no $DOMAIN_HEADER header  NO ROUTE"
    echo "      No route key in terraform/apigateway.tf matches this path, so"
    echo "      API Gateway answered it rather than any function. There is no"
    echo "      \$default to catch it since the monolith was retired, so this"
    echo "      path is unreachable and not merely misrouted."
    UNROUTED=$((UNROUTED + 1))
    continue
  fi

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
    echo "$label -> HTTP $code, served by '$MONOLITH'  FAIL"
    echo "      The monolith was retired and there is no \$default route. A"
    echo "      response from it means the function and a route to it were"
    echo "      re-created, which is only ever a deliberate rollback. If that"
    echo "      is what happened, this path is on the rolled-back surface."
    NOT_CUT=$((NOT_CUT + 1))
    ;;
  "")
    echo "$label -> HTTP $code, no $DOMAIN_HEADER header  FAIL"
    echo "      A function answered but stamped no header, so it is running an"
    echo "      image from before the header was added, or the response came"
    echo "      from outside the middleware stack (an unhandled 500)."
    echo "      Redeploy the backend, then run this again."
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

if [ "$ENV_NAME" = "staging" ] && [ ${#GATE_ARGS[@]} -gt 0 ]; then
  probe=${PATHS[0]}
  headers_gate=$(mktemp)
  bare=$(curl -sS --max-time "$TIMEOUT" -o /dev/null -D "$headers_gate" \
    -w '%{http_code}' "${BASE_URL}${probe}" 2>/dev/null || echo 000)
  gate_served_by=$(header_value "$DOMAIN_HEADER" "$headers_gate")
  rm -f "$headers_gate"

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
if [ "$UNROUTED" -gt 0 ]; then
  echo "NO ROUTE: $UNROUTED path(s) match no route key and are unreachable."
  echo "API Gateway answered them itself with a 404. Before the monolith was"
  echo "retired these would have fallen through to \$default and been served"
  echo "correctly; there is no \$default now, so this is an outage on those"
  echo "paths and not a routing warning."
  echo "The Terraform apply has not landed, or the routes map in"
  echo "terraform/apigateway.tf does not name these paths. Cross-check routeKey"
  echo "in /aws/apigateway/webbpulse-${ENV_NAME}-api."
  exit 1
fi
if [ "$FAILURES" -gt 0 ]; then
  echo "FAILED: $FAILURES path(s) did not verify."
  exit 1
fi
if [ "$NOT_CUT" -gt 0 ]; then
  echo "MONOLITH SERVING: $NOT_CUT path(s) were answered by the monolith."
  echo "It was retired, so this means it and a route to it were re-created."
  echo "Cross-check routeKey in /aws/apigateway/webbpulse-${ENV_NAME}-api."
  exit 1
fi

echo "All ${#PATHS[@]} '$DOMAIN' path(s) are served by the '$DOMAIN' function."
