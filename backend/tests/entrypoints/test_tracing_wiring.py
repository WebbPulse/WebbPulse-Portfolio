"""What `instrument_fastapi` leaves on a domain app, and where the ratio comes from."""

import logging

import pytest
from webbpulse.otel import SAMPLE_RATIO_ENV, instrument_fastapi, resolve_sample_ratio

from app.composition.wiring import DOMAIN_NAMES, build_domain_app

FLUSH_WRAPPED_ATTR = "_webbpulse_flush_wrapped"
OTEL_INSTRUMENTED_ATTR = "_is_instrumented_by_opentelemetry"
SHUTDOWN_WRAPPED_ATTR = "_webbpulse_shutdown_flush_wrapped"
ALREADY_INSTRUMENTED = "Attempting to instrument FastAPI app while already instrumented"


@pytest.mark.parametrize("domain", sorted(DOMAIN_NAMES))
def test_building_a_domain_app_instruments_it_exactly_once(domain, caplog):
    """`create_app` instruments the app, so no entrypoint may instrument it again.

    A second call logs a warning on every cold start and installs nothing, so the
    sentinel being set by the build and the log staying clean is the contract.
    """
    with caplog.at_level(logging.WARNING):
        app = build_domain_app(domain)

    assert getattr(app, OTEL_INSTRUMENTED_ATTR, False), (
        "create_app instruments the app it builds; an entrypoint must not repeat it"
    )
    assert getattr(app, SHUTDOWN_WRAPPED_ATTR, False), (
        "the shutdown flush wrapper is installed while the app is being built"
    )
    assert ALREADY_INSTRUMENTED not in caplog.text


@pytest.mark.parametrize("domain", sorted(DOMAIN_NAMES))
def test_instrumenting_a_built_domain_app_again_warns(domain, caplog):
    """The regression this guards: the warning a duplicate entrypoint call produced."""
    app = build_domain_app(domain)

    with caplog.at_level(logging.WARNING):
        instrument_fastapi(app)

    assert ALREADY_INSTRUMENTED in caplog.text


@pytest.mark.parametrize("domain", sorted(DOMAIN_NAMES))
def test_instrumenting_a_domain_app_installs_the_flush_wrapper_once(domain):
    """One wrapper after one call, and still one after a second call."""
    app = build_domain_app(domain)
    assert not getattr(app, FLUSH_WRAPPED_ATTR, False), (
        "the per-request flush wrapper is for Lambda, and the suite is not Lambda"
    )

    instrument_fastapi(app, flush_per_request=True)
    assert getattr(app, FLUSH_WRAPPED_ATTR, False)

    stack = app.build_middleware_stack()
    assert type(stack).__name__ == "_FlushTracingASGIMiddleware"
    assert type(stack.app).__name__ != "_FlushTracingASGIMiddleware"

    instrument_fastapi(app, flush_per_request=True)
    restack = app.build_middleware_stack()
    assert type(restack).__name__ == "_FlushTracingASGIMiddleware"
    assert type(restack.app).__name__ != "_FlushTracingASGIMiddleware"


def test_the_flush_wrapper_is_off_when_not_running_under_lambda(monkeypatch):
    """A local run flushes on its own schedule, so it gets no per-request flush."""
    monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)
    app = build_domain_app("public")
    instrument_fastapi(app)
    assert not getattr(app, FLUSH_WRAPPED_ATTR, False)


def test_the_sample_ratio_is_read_from_the_environment(monkeypatch):
    """`WEBBPULSE_OTEL_SAMPLE_RATIO` is what Terraform sets per environment."""
    monkeypatch.setenv(SAMPLE_RATIO_ENV, "0.1")
    assert resolve_sample_ratio() == pytest.approx(0.1)

    monkeypatch.setenv(SAMPLE_RATIO_ENV, "1.0")
    assert resolve_sample_ratio() == pytest.approx(1.0)


def test_the_sample_ratio_defaults_to_keeping_everything(monkeypatch):
    """No variable means 1.0, so a function that lost its env var over-traces."""
    monkeypatch.delenv(SAMPLE_RATIO_ENV, raising=False)
    monkeypatch.delenv("OTEL_TRACES_SAMPLER", raising=False)
    monkeypatch.delenv("OTEL_TRACES_SAMPLER_ARG", raising=False)
    assert resolve_sample_ratio() == pytest.approx(1.0)


def test_an_unusable_sample_ratio_falls_back_rather_than_raising(monkeypatch):
    """A typo in a Terraform variable must cost money, not availability."""
    monkeypatch.delenv("OTEL_TRACES_SAMPLER", raising=False)
    monkeypatch.delenv("OTEL_TRACES_SAMPLER_ARG", raising=False)
    for bad in ("", "  ", "not-a-number", "-0.5", "1.5"):
        monkeypatch.setenv(SAMPLE_RATIO_ENV, bad)
        assert resolve_sample_ratio() == pytest.approx(1.0)
