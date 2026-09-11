#!/usr/bin/env bash
set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

DOMAIN="${1:-}"
TAG="${2:-local}"

PLATFORM="${PLATFORM:-linux/arm64}"
ENVIRONMENT="${ENVIRONMENT:-staging}"
IMAGE_REPO="${IMAGE_REPO:-webbpulse-${ENVIRONMENT}/${DOMAIN}}"
CODEARTIFACT_DOMAIN="${CODEARTIFACT_DOMAIN:-webbpulse}"
CODEARTIFACT_DOMAIN_OWNER="${CODEARTIFACT_DOMAIN_OWNER:-432410731887}"
CODEARTIFACT_REPOSITORY="${CODEARTIFACT_REPOSITORY:-python}"
AWS_REGION="${AWS_REGION:-us-west-2}"

usage() {
    cat >&2 <<'USAGE'
usage: build_image.sh <domain> [tag]

  domain  one of content, resume, identity, public
  tag     image tag, default "local". CI passes sha-<commit>, which is what the
          ECR repositories' immutable tag prefix expects.

environment:
  CODEARTIFACT_AUTH_TOKEN   required. Mint one with:
      export CODEARTIFACT_AUTH_TOKEN="$(aws codeartifact get-authorization-token \
        --domain webbpulse --domain-owner 432410731887 \
        --region us-west-2 --query authorizationToken --output text)"
  PLATFORM                  default linux/arm64, matching terraform/lambda.tf
  ENVIRONMENT               default staging, used to build the default repo name
  IMAGE_REPO                default webbpulse-<environment>/<domain>
  BASE_IMAGE                default is the digest pinned in the Dockerfile
  PUSH                      set to 1 to push instead of loading locally
USAGE
    exit 2
}

case "${DOMAIN}" in
    content|resume|identity|public) ;;
    "") echo "error: no domain given." >&2; usage ;;
    *) echo "error: '${DOMAIN}' is not a domain." >&2; usage ;;
esac

if [[ -z "${CODEARTIFACT_AUTH_TOKEN:-}" ]]; then
    echo "error: CODEARTIFACT_AUTH_TOKEN is not set." >&2
    echo "The image installs webbpulse, which is published only to CodeArtifact." >&2
    usage
fi

if [[ "${DOMAIN}" == "public" ]]; then
    READINESS_PROTOCOL="tcp"
else
    READINESS_PROTOCOL="http"
fi

IMAGE="${IMAGE_REPO}:${TAG}"

if [[ "${PUSH:-0}" == "1" ]]; then
    OUTPUT_ARGS=(--push)
else
    OUTPUT_ARGS=(--load)
fi

BUILD_ARGS=(
    --platform "${PLATFORM}"
    --build-arg "DOMAIN=${DOMAIN}"
    --build-arg "READINESS_PROTOCOL=${READINESS_PROTOCOL}"
    --build-arg "CODEARTIFACT_DOMAIN=${CODEARTIFACT_DOMAIN}"
    --build-arg "CODEARTIFACT_DOMAIN_OWNER=${CODEARTIFACT_DOMAIN_OWNER}"
    --build-arg "CODEARTIFACT_REPOSITORY=${CODEARTIFACT_REPOSITORY}"
    --build-arg "AWS_REGION=${AWS_REGION}"
    --secret "id=codeartifact_token,env=CODEARTIFACT_AUTH_TOKEN"
    --tag "${IMAGE}"
)

if [[ -n "${BASE_IMAGE:-}" ]]; then
    BUILD_ARGS+=(--build-arg "BASE_IMAGE=${BASE_IMAGE}")
fi

echo "building ${IMAGE} (domain=${DOMAIN}, platform=${PLATFORM}, readiness=${READINESS_PROTOCOL})"

docker buildx build "${BUILD_ARGS[@]}" "${OUTPUT_ARGS[@]}" "${BACKEND_DIR}"

echo "built ${IMAGE}"
