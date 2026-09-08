"""The public domain's entrypoint.

The unauthenticated surface: `GET /`, `/health`, `/sitemap.xml` and
`/robots.txt`. It reads no secret at all, which is the least-privilege claim the
whole split rests on.

Run by the image as `python -m app.entrypoints.public`. There is no Lambda
handler and no Mangum: the Web Adapter starts before this process, turns each
invoke into an ordinary HTTP request against `127.0.0.1:$AWS_LWA_PORT`, and
turns the response back, so the same image runs on Lambda and in a container.

`build_app` is importable on its own and reads no AWS, which is what lets the
tests build this application with no credentials and no environment. Only
`main` configures logging and tracing, because those are process-wide effects
that a test importing the module must not inherit.
"""

from webbpulse.lambda_entry import run_uvicorn
from webbpulse.logging import configure_logging
from webbpulse.otel import configure_tracing, instrument_fastapi, resolve_sample_ratio

from ..composition.settings import get_settings
from ..composition.wiring import DOMAINS, build_domain_app

DOMAIN = DOMAINS["public"]


def build_app():
    """This domain's application: its routers and nothing else."""
    return build_domain_app(DOMAIN)


def main() -> None:
    settings = get_settings()
    # Keyword-only, and logging first: `configure_tracing` logs its own warnings
    # about a missing ADOT distro, and they are worth having in JSON.
    configure_logging(
        level=settings.log_level,
        service=DOMAIN.service_name,
        environment=settings.environment,
    )
    # Tracing before the application is built, so `instrument_fastapi` attaches
    # to a real tracer provider rather than the API's no-op one. The ratio is
    # resolved explicitly rather than left to the default so the value this
    # process is actually running with appears in the configuration log line,
    # which is the only way to tell a misread WEBBPULSE_OTEL_SAMPLE_RATIO from a
    # correctly read one.
    configure_tracing(
        DOMAIN.service_name,
        environment=settings.environment,
        sample_ratio=resolve_sample_ratio(),
    )
    app = build_app()
    # Must happen before uvicorn serves: `instrument_app` can only inject the
    # server span middleware while the middleware stack is still unbuilt, and
    # the flush wrapper it installs is what exports a tail sampled trace before
    # the Lambda execution environment freezes. Auto-on under Lambda, off in a
    # local run.
    instrument_fastapi(app)
    # Blocks. `run_uvicorn` binds AWS_LWA_PORT, then PORT, then 8080, which is
    # the adapter's own precedence; binding anything else presents as the
    # readiness check never passing with no application logs at all.
    run_uvicorn(app)


if __name__ == "__main__":
    main()
