# syntax=docker/dockerfile:1.7
#
# One Dockerfile, four images. `DOMAIN` selects which entrypoint the image runs;
# everything else about the four is identical, which is what keeps the
# dependency layer bit-identical across them and the storage cost flat.
#
# Build it with `scripts/build_image.sh <domain>`, which supplies the
# CodeArtifact secret and the platform. The raw form is:
#
#   docker buildx build \
#     --platform linux/arm64 \
#     --build-arg DOMAIN=content \
#     --secret id=codeartifact_token,env=CODEARTIFACT_AUTH_TOKEN \
#     -t webbpulse-staging/content:sha-<commit> backend/
#
# Three things about this file are load-bearing rather than stylistic.
#
# **The base image is pinned by digest, not by tag.** The default below is the
# exact image the production functions are built FROM, so a build with no
# `--build-arg BASE_IMAGE` reproduces production. It already carries Lambda Web
# Adapter 1.0.1 at `/opt/extensions/lambda-adapter`, so this file must not copy
# the adapter again: a second copy over the same path is wasted layer bytes at
# best, and a version skew between the two at worst.
#
# **The CodeArtifact token is a BuildKit secret mount.** `webbpulse` is
# published only to CodeArtifact, so the dependency install needs a token, and
# a token passed as `ARG` or `ENV` persists in `docker history` for anyone who
# can pull the image. The mount exists only for the life of the RUN line, and
# the index URL is assembled inside that line so the token never becomes a
# layer.
#
# **The runtime stage copies the installed tree, not the builder.** Dev and test
# dependencies are in `requirements-dev.txt` and are never installed here, so
# `moto`, `pytest` and `ruff` cannot reach the image by accident.
# ---------------------------------------------------------------------------

ARG BASE_IMAGE=432410731887.dkr.ecr.us-west-2.amazonaws.com/webbpulse/python-lambda-base@sha256:b5298b4b773ad6c9e311057cf5d43f37ceb98f0367347d714c6817f250a5cef7

# ---------------------------------------------------------------------------
# Builder: resolve and install the runtime dependency set into /deps.
#
# `--target` rather than a virtualenv, because the runtime stage puts the same
# directory on PYTHONPATH and Lambda's read-only filesystem makes an activated
# venv more machinery than the layout needs.
# ---------------------------------------------------------------------------
FROM ${BASE_IMAGE} AS builder

WORKDIR /build

# Only requirements.txt, so a change to app/ does not invalidate the dependency
# layer. requirements-dev.txt is deliberately not copied and not installed.
COPY requirements.txt ./

# The CodeArtifact index. `aws` is the literal username CodeArtifact expects;
# the password is the token. Assembled inside the RUN so neither the token nor
# the assembled URL is written to a layer or to pip.conf.
ARG CODEARTIFACT_DOMAIN=webbpulse
ARG CODEARTIFACT_DOMAIN_OWNER=432410731887
ARG CODEARTIFACT_REPOSITORY=python
ARG AWS_REGION=us-west-2

RUN --mount=type=secret,id=codeartifact_token,required=true \
    set -eu; \
    token="$(cat /run/secrets/codeartifact_token)"; \
    PIP_INDEX_URL="https://aws:${token}@${CODEARTIFACT_DOMAIN}-${CODEARTIFACT_DOMAIN_OWNER}.d.codeartifact.${AWS_REGION}.amazonaws.com/pypi/${CODEARTIFACT_REPOSITORY}/simple/" \
    pip install --no-cache-dir --target /deps -r requirements.txt

# Caches only. Stripping them here keeps the layer the runtime stage copies as
# small as the install allows, and __pycache__ written against the builder's
# paths is not reused at runtime anyway.
RUN find /deps -type d -name "__pycache__" -prune -exec rm -rf {} + \
    && find /deps -type f \( -name "*.pyc" -o -name "*.pyo" \) -delete

# ---------------------------------------------------------------------------
# Runtime: the base image, the installed dependencies, and app/.
# ---------------------------------------------------------------------------
FROM ${BASE_IMAGE} AS runtime

# Which domain this image serves. There is no default on purpose: an image
# built without it would silently be some arbitrary domain's, and the four
# repositories would stop meaning what their names say.
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

# Dependencies first, application second: app/ changes on every commit and the
# dependency layer changes only when requirements.txt does.
COPY --from=builder /deps /var/task
COPY app/ /var/task/app/

ENV DOMAIN=${DOMAIN} \
    PYTHONPATH=/var/task \
    # Python buffers stdout when it is not a terminal, so without this a log
    # line can sit in the buffer while the execution environment is frozen
    # between invokes and arrive attributed to a later request.
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # The port the adapter polls. `run_uvicorn` reads AWS_LWA_PORT, then PORT,
    # then defaults to 8080, which is the adapter's own precedence; binding
    # anything else presents as the readiness check never passing, with no
    # application logs at all.
    AWS_LWA_PORT=8080 \
    # Moves slow imports into Lambda's 10 second init window rather than
    # charging them to the first invoke. Four cold paths instead of one makes
    # this matter more than it did on the monolith.
    AWS_LWA_ASYNC_INIT=true

# The readiness check, and the one place the four images genuinely differ.
#
# The adapter polls this on every cold start, so it must not do I/O. Three of
# the four domains get `create_app`'s liveness-only `GET /health`, which is
# exactly that route and is why the shared one exists.
#
# `public` is the exception, and it is not an oversight. Its own `GET /health`
# reads the site-content singleton to report `database`, the deploy smoke test
# asserts on that field, and `build_domain_app` therefore sets
# `include_health=False` for it so the database-reading route is the only
# `/health` its application declares. Pointing the adapter at that path would
# put a DynamoDB read in front of every `public` cold start and would fail the
# function to start whenever the table was briefly unavailable, which is the
# failure the shared route was introduced to avoid.
#
# So `public` uses the adapter's TCP readiness check: the adapter waits for the
# port to accept a connection and polls no route at all. That is the right
# check for an application whose only `/health` is a dependency check, and it
# leaves `GET /health` answering for the smoke test exactly as it does today.
# Both variable names and the `http` / `tcp` values are read out of the adapter
# binary's own strings rather than assumed.
#
# `ENV` cannot branch on a build arg, so the value arrives as one.
# `scripts/build_image.sh` derives it from the domain and callers do not pass
# it; the check below is what stops a hand-run `docker build` shipping a
# `public` image that polls its own database check. Getting this wrong is a
# delayed failure, not an immediate one: the image starts fine and only fails
# on a cold start that races an unavailable table.
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

# `sh -c` rather than an exec-form CMD with the domain inlined, because CMD does
# not expand a build-time ARG. `exec` replaces the shell so the Python process
# is PID 1 and receives Lambda's signals directly.
CMD ["sh", "-c", "exec python -m app.entrypoints.${DOMAIN}"]
