"""What each entrypoint may import, and what it may need to start.

Two properties, and both are about the deployed image rather than the response
a route returns.

**A domain image carries one domain.** `test_domain_boundaries.py` proves no
file under `domains/<name>/` imports another domain. That is a rule about the
source tree, and it stays true even if the composition code drags all four in
anyway: `app.core.middleware` imports `content`'s and `identity`'s seeders, so a
single module-level import in the wiring puts both domains in the `public`
image. These tests run each entrypoint in a fresh interpreter and read
`sys.modules`, which is the only way to see what actually got imported.

**A domain image starts with nothing.** The functions run with no AWS
credentials during a cold start's import phase, and `public` runs with no
`secretsmanager:GetSecretValue` at all. If building the application reads a
secret, the function does not start, and it does not start in a way that
produces no application logs, because it fails before logging is configured.
So the subprocesses run under `env -i`: no `AWS_*`, no `APP_SECRETS_ARN`, no
`DYNAMODB_TABLE_PREFIX`, nothing but what the settings class defaults.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.composition.wiring import DOMAIN_NAMES

BACKEND = Path(__file__).resolve().parents[2]

PROBE = """
import json, sys
from app.entrypoints import {domain} as entrypoint

app = entrypoint.build_app()
domains = sorted(
    name.split(".")[2]
    for name in sys.modules
    if name.startswith("app.domains.") and name.count(".") == 2
)
print(json.dumps({{
    "domains": domains,
    "routes": len(app.routes),
    "service_name": entrypoint.DOMAIN.service_name,
}}))
"""


def _probe(domain, env=None):
    """Build one entrypoint's app in a fresh interpreter with an empty environment.

    `env -i` is the point of the test, so the only variables set are the two
    the interpreter itself needs: `PATH` to find nothing in particular, and
    `PYTHONPATH` so `app` is importable without an installed distribution.
    """
    environment = {
        "PATH": "/usr/bin:/bin",
        "PYTHONPATH": str(BACKEND),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    environment.update(env or {})
    result = subprocess.run(
        [sys.executable, "-c", PROBE.format(domain=domain)],
        cwd=BACKEND,
        env=environment,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, (
        f"{domain} failed to build with an empty environment:\n{result.stderr}"
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def probes():
    """One subprocess per domain, reused across the tests in this module."""
    return {domain: _probe(domain) for domain in DOMAIN_NAMES}


@pytest.mark.parametrize("domain", sorted(DOMAIN_NAMES))
def test_an_entrypoint_builds_with_no_credentials_and_no_environment(domain, probes):
    """The `env -i` run already asserted this by not raising; this names it.

    A failure here is a function that cannot cold start, so it is worth being
    its own test rather than an implicit precondition of the next one.
    """
    assert probes[domain]["routes"] > 0


@pytest.mark.parametrize("domain", sorted(DOMAIN_NAMES))
def test_an_entrypoint_imports_only_its_own_domain(domain, probes):
    """The claim that makes four images smaller than four copies of one image.

    A regression here is silent: every route still answers, the tests still
    pass, and the only symptom is that `public` pays `content`'s import on
    every cold start and ships code it has no IAM to use.
    """
    assert probes[domain]["domains"] == [domain]


@pytest.mark.parametrize("domain", sorted(DOMAIN_NAMES))
def test_an_entrypoint_reports_its_own_service_name(domain, probes):
    assert probes[domain]["service_name"] == f"webbpulse-portfolio-{domain}"


@pytest.mark.parametrize("domain", sorted(DOMAIN_NAMES))
def test_an_entrypoint_exposes_the_runtime_wiring(domain):
    """`main` is what the image runs, and it wires the four shared helpers.

    Asserted by reading the module rather than calling it, because
    `configure_logging` replaces the root handlers and `configure_tracing`
    installs a global tracer provider, and a test that ran them would leave
    both in place for every test after it. `instrument_fastapi` is here because
    tail sampling exports nothing without the per-request flush it installs, so
    an entrypoint that drops it still starts, still answers, and emits no
    traces at all.
    """
    module = __import__(f"app.entrypoints.{domain}", fromlist=["main"])
    source = Path(module.__file__).read_text()
    for helper in (
        "configure_logging",
        "configure_tracing",
        "instrument_fastapi",
        "run_uvicorn",
    ):
        assert helper in source, f"{domain} entrypoint does not call {helper}"
    assert callable(module.main)
    assert callable(module.build_app)


def test_no_entrypoint_imports_a_whole_surface_root():
    """A deployed entrypoint builds one domain, never all four.

    `app.composition.app` is root A, the whole surface on one application. It is
    what local development and the test client run, and importing it from an
    entrypoint would make every domain image build all four domains at import
    time, so the isolation above would be accidental rather than structural.

    `app.main` was the monolith's root and is deleted. It stays in this list so
    a restored import is caught here, with the reason, rather than as a bare
    `ModuleNotFoundError` from an image build.
    """
    for domain in DOMAIN_NAMES:
        source = (BACKEND / "app" / "entrypoints" / f"{domain}.py").read_text()
        for forbidden in ("app.main", "from ..main", "composition.app", "from .app"):
            assert forbidden not in source, f"{domain} imports {forbidden}"
