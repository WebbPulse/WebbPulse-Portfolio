"""The route split, asserted rather than described."""

import json
from pathlib import Path

import pytest

from app.common.composition.wiring import DOMAIN_NAMES, DOMAINS, build_domain_app

from ..routes import method_path_pairs

CONTRACT_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "route_contract.json"
CONTRACT = json.loads(CONTRACT_PATH.read_text())

CONTRACT_PAIRS = {(entry["method"], entry["path"]) for entry in CONTRACT["routes"]}

CONTRACT_OPERATIONS = {
    (entry["method"], entry["path"], entry["operationId"], tuple(entry["tags"])) for entry in CONTRACT["operations"]
}

EXPECTED_COUNTS = CONTRACT["counts"]


def _route_pairs(app):
    """(method, path) for every application route, documentation excluded."""
    return method_path_pairs(app)


def _operations(app):
    """(method, path, operationId, tags) for every documented operation."""
    document = app.openapi()
    return {
        (
            method.upper(),
            path,
            operation["operationId"],
            tuple(operation.get("tags", ())),
        )
        for path, item in document["paths"].items()
        for method, operation in item.items()
    }


def _domain_pairs(name):
    """A domain's application routes, minus the shared liveness `/health`."""
    pairs = _route_pairs(build_domain_app(name))
    return pairs if name == "public" else pairs - {("GET", "/health")}


def test_public_is_the_only_wired_domain():
    """The site serves only public data, so public is the only wired domain."""
    assert sorted(DOMAIN_NAMES) == ["public"]


def test_the_recorded_contract_is_the_shape_the_plan_describes():
    """The fixture itself, checked before anything is measured against it."""
    assert len(CONTRACT_PAIRS) == 3
    assert len(CONTRACT_OPERATIONS) == 3
    assert sum(EXPECTED_COUNTS.values()) == 3
    assert {(m, p) for m, p, _, _ in CONTRACT_OPERATIONS} == CONTRACT_PAIRS


@pytest.mark.parametrize("name", sorted(DOMAIN_NAMES))
def test_a_domain_serves_only_routes_the_contract_records(name):
    """A domain serves nothing the recorded contract does not list."""
    assert _domain_pairs(name) - CONTRACT_PAIRS == set()


@pytest.mark.parametrize("name", sorted(DOMAIN_NAMES))
def test_a_domain_documents_the_same_operations_as_the_contract(name):
    """Same operation id and same tags, not merely the same path."""
    documented = _operations(build_domain_app(name))
    assert documented - CONTRACT_OPERATIONS == set()


@pytest.mark.parametrize("name", sorted(DOMAIN_NAMES))
def test_a_domain_serves_exactly_its_own_count(name):
    """A domain serves the number of routes the contract assigns it."""
    assert len(_domain_pairs(name)) == EXPECTED_COUNTS[name]


def test_no_two_domains_serve_the_same_route():
    """No route is served by more than one domain."""
    seen = {}
    collisions = []
    for name in DOMAIN_NAMES:
        for pair in _domain_pairs(name):
            if pair in seen:
                collisions.append((pair, seen[pair], name))
            seen[pair] = name
    assert collisions == []


def test_the_union_of_the_domains_is_exactly_the_contract():
    """The domains together serve exactly the contract."""
    union = set()
    for name in DOMAIN_NAMES:
        union |= _domain_pairs(name)
    assert union == CONTRACT_PAIRS
    assert len(union) == sum(EXPECTED_COUNTS.values()) == 3


def test_the_union_of_the_documented_operations_is_the_contract_document():
    """The documented operations across the domains are exactly the contract's."""
    union = set()
    for name in DOMAIN_NAMES:
        union |= _operations(build_domain_app(name))
    assert union == CONTRACT_OPERATIONS


def test_root_a_serves_the_same_surface_as_the_domains_together():
    """Root A and root B, still two views of one list."""
    from app.common.composition.app import build_app

    union = set()
    for name in DOMAIN_NAMES:
        union |= _domain_pairs(name)
    assert _route_pairs(build_app()) == union == CONTRACT_PAIRS


@pytest.mark.parametrize("name", sorted(DOMAIN_NAMES))
def test_every_domain_answers_the_adapter_readiness_path(name):
    """`AWS_LWA_READINESS_CHECK_PATH=/health`, so every function must serve it."""
    assert ("GET", "/health") in _route_pairs(build_domain_app(name))


def test_public_serves_the_database_reporting_health():
    """The public function's own `/health` reads DynamoDB and is documented."""
    assert "/health" in build_domain_app("public").openapi()["paths"]


def test_public_reads_no_secret():
    """The least-privilege claim the whole split rests on."""
    assert DOMAINS["public"].requires_secrets == ()


def test_service_names_match_what_terraform_sets():
    """Each domain's service name is the one Terraform sets."""
    assert {name: DOMAINS[name].service_name for name in DOMAIN_NAMES} == {
        "public": "webbpulse-portfolio-public",
    }
