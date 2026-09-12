"""The resume domain's entrypoint.

Projects, experience, skills, education and certifications, under `/api/v1`.
"""

from webbpulse.lambda_entry import run_uvicorn
from webbpulse.logging import configure_logging
from webbpulse.otel import configure_tracing, resolve_sample_ratio

from ..composition.settings import get_settings
from ..composition.wiring import DOMAINS, build_domain_app, check_required_secrets

DOMAIN = DOMAINS["resume"]


def build_app():
    """This domain's application: its routers and nothing else."""
    return build_domain_app(DOMAIN)


def main() -> None:
    """Configure logging and tracing, then serve this domain until killed.

    Logging first, then tracing, then the secret check, so a misconfigured
    function fails at cold start with the failure already in JSON.

    Tracing is configured before the app is built because `create_app`
    instruments the app for us, and that instrumentation is skipped unless
    tracing is already enabled.
    """
    settings = get_settings()
    configure_logging(
        level=settings.log_level,
        service=DOMAIN.service_name,
        environment=settings.environment,
    )
    configure_tracing(
        DOMAIN.service_name,
        environment=settings.environment,
        sample_ratio=resolve_sample_ratio(),
    )
    check_required_secrets([DOMAIN], settings=settings)
    app = build_app()
    run_uvicorn(app)


if __name__ == "__main__":
    main()
