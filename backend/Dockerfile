# syntax=docker/dockerfile:1.7

ARG BASE_IMAGE=432410731887.dkr.ecr.us-west-2.amazonaws.com/webbpulse/python-lambda-base@sha256:b5298b4b773ad6c9e311057cf5d43f37ceb98f0367347d714c6817f250a5cef7

FROM ${BASE_IMAGE} AS builder

USER root

WORKDIR /build

COPY requirements.txt ./

ARG CODEARTIFACT_DOMAIN=webbpulse
ARG CODEARTIFACT_DOMAIN_OWNER=432410731887
ARG CODEARTIFACT_REPOSITORY=python
ARG AWS_REGION=us-west-2

RUN --mount=type=secret,id=codeartifact_token,required=true \
    set -eu; \
    token="$(cat /run/secrets/codeartifact_token)"; \
    PIP_INDEX_URL="https://aws:${token}@${CODEARTIFACT_DOMAIN}-${CODEARTIFACT_DOMAIN_OWNER}.d.codeartifact.${AWS_REGION}.amazonaws.com/pypi/${CODEARTIFACT_REPOSITORY}/simple/" \
    pip install --no-cache-dir --target /deps -r requirements.txt

RUN find /deps -type d -name "__pycache__" -prune -exec rm -rf {} + \
    && find /deps -type f \( -name "*.pyc" -o -name "*.pyo" \) -delete

FROM ${BASE_IMAGE} AS runtime

ARG DOMAIN
RUN test -n "${DOMAIN}" || { \
        echo "DOMAIN build arg is required: one of content, resume, identity, public." >&2; \
        echo "  docker buildx build --build-arg DOMAIN=content ..." >&2; \
        exit 1; \
    }; \
    case "${DOMAIN}" in \
        content|resume|identity|public) ;; \
        *) echo "DOMAIN=${DOMAIN} is not a domain. Expected one of content, resume, identity, public." >&2; exit 1 ;; \
    esac

COPY --from=builder /deps /var/task
COPY app/ /var/task/app/

ENV DOMAIN=${DOMAIN} \
    PYTHONPATH=/var/task \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    AWS_LWA_PORT=8080 \
    AWS_LWA_ASYNC_INIT=true

ARG READINESS_PROTOCOL=http
RUN case "${DOMAIN}:${READINESS_PROTOCOL}" in \
        public:tcp|content:http|resume:http|identity:http) ;; \
        public:*) \
            echo "public must build with READINESS_PROTOCOL=tcp." >&2; \
            echo "Its only GET /health reads DynamoDB, so an http readiness check would" >&2; \
            echo "put that read in front of every cold start. Use scripts/build_image.sh," >&2; \
            echo "which derives this from the domain." >&2; \
            exit 1 ;; \
        *) \
            echo "DOMAIN=${DOMAIN} must build with READINESS_PROTOCOL=http, not ${READINESS_PROTOCOL}." >&2; \
            exit 1 ;; \
    esac

ENV AWS_LWA_READINESS_CHECK_PATH=/health \
    AWS_LWA_READINESS_CHECK_PROTOCOL=${READINESS_PROTOCOL}

WORKDIR /var/task

CMD ["sh", "-c", "exec python -m app.entrypoints.${DOMAIN}"]
