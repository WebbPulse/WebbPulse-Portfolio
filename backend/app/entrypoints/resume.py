"""The resume domain's entrypoint.

Projects, experience, skills, education and certifications: 25 routes under
`/api/v1`.

Run by the image as `python -m app.entrypoints.resume`. There is no Lambda
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
from webbpulse.otel import configure_tracing

from ..composition.settings import get_settings
from ..composition.wiring import DOMAINS, build_domain_app

DOMAIN = DOMAINS["resume"]


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
    configure_tracing(DOMAIN.service_name, environment=settings.environment)
    # Blocks. `run_uvicorn` binds AWS_LWA_PORT, then PORT, then 8080, which is
    # the adapter's own precedence; binding anything else presents as the
    # readiness check never passing with no application logs at all.
    run_uvicorn(build_app())


if __name__ == "__main__":
    main()
