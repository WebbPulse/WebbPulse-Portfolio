"""What each entrypoint may import, and what it may need to start."""

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
    """Build one entrypoint's app in a fresh interpreter with an empty environment."""
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
    """The `env -i` run already asserted this by not raising; this names it."""
    assert probes[domain]["routes"] > 0


@pytest.mark.parametrize("domain", sorted(DOMAIN_NAMES))
def test_an_entrypoint_imports_only_its_own_domain(domain, probes):
    """The claim that makes four images smaller than four copies of one image."""
    assert probes[domain]["domains"] == [domain]


@pytest.mark.parametrize("domain", sorted(DOMAIN_NAMES))
def test_an_entrypoint_reports_its_own_service_name(domain, probes):
    """Each entrypoint reports the service name Terraform expects for it."""
    assert probes[domain]["service_name"] == f"webbpulse-portfolio-{domain}"


@pytest.mark.parametrize("domain", sorted(DOMAIN_NAMES))
def test_an_entrypoint_exposes_the_runtime_wiring(domain):
    """`main` is what the image runs, and it wires the four shared helpers."""
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
    """A deployed entrypoint builds one domain, never all four."""
    for domain in DOMAIN_NAMES:
        source = (BACKEND / "app" / "entrypoints" / f"{domain}.py").read_text()
        for forbidden in ("app.main", "from ..main", "composition.app", "from .app"):
            assert forbidden not in source, f"{domain} imports {forbidden}"
