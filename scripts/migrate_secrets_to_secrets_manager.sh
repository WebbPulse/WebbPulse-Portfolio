#!/usr/bin/env bash
#
# Copy the WebbPulse-Portfolio application secrets from SSM SecureString
# parameters into the Secrets Manager secrets created by the app-secrets module.
#
# Step 2 of the four-step migration described at the top of terraform/db.tf. Run
# it after the terraform change that creates the secrets has been applied, and
# before the backend is switched over to reading them.
#
# No secret value is ever printed, written to a file, or held in a shell
# variable. Each value goes from the SSM read straight into the Secrets Manager
# write through a pipe.
#
# The value is read as JSON and emitted with `jq -rj`, which writes the raw
# bytes with no trailing newline. `--output text` would append one, and
# `--secret-string file:///dev/stdin` stores whatever it is given verbatim, so
# every secret would end up one byte longer than its source and admin login
# would fail after the switch.
#
# This script does not read the secrets back. `get-secret-value` is not called
# here in any form: byte counts of a password leak its length, and the estate
# rule is that the value is never read outside the application. The write check
# is `set -euo pipefail` plus the VersionId each put returns. End-to-end
# verification is the backend switch in the next change, where the application
# reads Secrets Manager and admin login is exercised in staging before
# production.
#
# Usage:
#   AWS_PROFILE=Portfolio-Staging/AdministratorAccess \
#     scripts/migrate_secrets_to_secrets_manager.sh staging
#
#   AWS_PROFILE=Portfolio-Production/AdministratorAccess \
#     scripts/migrate_secrets_to_secrets_manager.sh production
#
# Idempotent: re-running it writes a fresh version holding the same bytes.

set -euo pipefail

ENVIRONMENT="${1:-}"
AWS_REGION="${AWS_REGION:-us-west-2}"

if [ -z "$ENVIRONMENT" ]; then
  echo "usage: $0 <environment>    (staging or production)" >&2
  exit 2
fi

if [ "$ENVIRONMENT" != "staging" ] && [ "$ENVIRONMENT" != "production" ]; then
  echo "error: environment must be 'staging' or 'production', got '$ENVIRONMENT'" >&2
  exit 2
fi

if [ -z "${AWS_PROFILE:-}" ]; then
  echo "error: set AWS_PROFILE to the account holding the $ENVIRONMENT estate" >&2
  exit 2
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "error: jq is required; it emits the parameter value with no trailing newline" >&2
  exit 2
fi

PREFIX="webbpulse-${ENVIRONMENT}"

# Key names are shared: the SSM parameter is /<prefix>/<key> and the secret is
# <prefix>/<key>, so one list drives both sides.
KEYS=(secret-key admin-username admin-password admin-email)

ssm_name() { echo "/${PREFIX}/$1"; }
secret_name() { echo "${PREFIX}/$1"; }

echo "Account:     $(aws sts get-caller-identity --query Account --output text)"
echo "Region:      ${AWS_REGION}"
echo "Environment: ${ENVIRONMENT}"
echo "Prefix:      ${PREFIX}"
echo

# ---------------------------------------------------------------------------
# Preflight. Refuse to copy anything unless every source parameter and every
# destination secret exists, so a partial run cannot leave half the secrets
# populated.
# ---------------------------------------------------------------------------

missing=0

for key in "${KEYS[@]}"; do
  if ! aws ssm describe-parameters \
        --region "$AWS_REGION" \
        --parameter-filters "Key=Name,Values=$(ssm_name "$key")" \
        --query 'Parameters[0].Name' --output text 2>/dev/null | grep -q .; then
    echo "missing source parameter: $(ssm_name "$key")" >&2
    missing=1
  fi
done

for key in "${KEYS[@]}"; do
  if ! aws secretsmanager describe-secret \
        --region "$AWS_REGION" \
        --secret-id "$(secret_name "$key")" \
        --query Name --output text >/dev/null 2>&1; then
    echo "missing destination secret: $(secret_name "$key")" >&2
    echo "  apply the terraform that creates it before running this script" >&2
    missing=1
  fi
done

if [ "$missing" -ne 0 ]; then
  echo >&2
  echo "refusing to run: fix the above and try again" >&2
  exit 1
fi

echo "Preflight passed: 4 parameters, 4 secrets."
echo

# ---------------------------------------------------------------------------
# Copy. One pipeline per secret, value never leaving the pipe. --query VersionId
# keeps put-secret-value from echoing the secret back.
# ---------------------------------------------------------------------------

for key in "${KEYS[@]}"; do
  printf 'copying %-16s ' "$key"

  # jq -rj writes the raw value with no trailing newline. Anything that appends
  # one would be stored verbatim by --secret-string file:///dev/stdin.
  version_id=$(
    aws ssm get-parameter \
        --region "$AWS_REGION" \
        --name "$(ssm_name "$key")" \
        --with-decryption \
        --output json \
      | jq -rj '.Parameter.Value' \
      | aws secretsmanager put-secret-value \
          --region "$AWS_REGION" \
          --secret-id "$(secret_name "$key")" \
          --secret-string file:///dev/stdin \
          --query VersionId \
          --output text
  )

  echo "version ${version_id}"
done

echo

# ---------------------------------------------------------------------------
# Done. Nothing is read back: set -euo pipefail fails the run if any stage of a
# pipeline fails, and each put above printed the VersionId it created, which is
# the confirmation that the write landed.
#
# End-to-end verification is the next change, which switches the backend onto
# Secrets Manager. Confirm admin login works in staging there before promoting
# to production.
# ---------------------------------------------------------------------------

echo "All 4 secrets copied."
echo "Next: merge the backend change that reads Secrets Manager, deploy it to"
echo "staging, and confirm admin login works before promoting to production."
