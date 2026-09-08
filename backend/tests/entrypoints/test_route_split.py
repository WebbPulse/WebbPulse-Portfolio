"""The route split, asserted rather than described.

The plan's section 1 says the 44 application routes divide 14 content, 25
resume, 1 identity and 4 public. These tests are what makes that a fact about
the code instead of a claim in a document, and they are the thing that notices
if a domain quietly re-acquires the whole router after a refactor.

## What replaced the monolith as the reference

These tests used to measure the four domains against `app.main`, the application
the retired monolith Lambda served: every domain's routes a subset of its, and
the union of the four exactly equal to it. That reference is gone. The monolith
function, its integration and `$default` were destroyed in PR #118, and this PR
deletes the source, so there is no longer a running application to compare
against and keeping a Python module purely as a test fixture would be keeping a
second composition root alive to check the first one.

`tests/fixtures/route_contract.json` took its place. It is the recorded
contract: the 44 (method, path) pairs and the 42 documented operations with
their ids and tags, generated from the union the monolith published and pinned
to a file. That is a stronger reference than the module was, not a weaker one.
`app.main` was code, so a change that broke the contract could be made to both
sides at once and the equality would still hold; the fixture cannot be edited by
a refactor, only by someone deciding on purpose to move the published contract.

The four properties are otherwise unchanged, and each still catches a different
mistake:

- **Subset.** Every route a domain serves is in the recorded contract, with the
  same path, method, operation id and tags. A path that drifts here breaks a
  generated client, and nothing before production would notice.
- **No overlap.** No two domains serve the same method and path. Two functions
  answering one route means API Gateway picks and the other is dead code that
  still gets deployed, patched and paid for.
- **Union.** The four together serve exactly the recorded 44. A route in none of
  them is unreachable: with `default_integration = null` there is no `$default`
  to fall through to, so it is an API Gateway 404 to every caller.
- **Counts.** The split is 14/25/1/4, which is what the Terraform route map in
  section 3.5 is written against.
"""

import json
from pathlib import Path

import pytest

from app.composition.wiring import DOMAIN_NAMES, DOMAINS, build_domain_app

# FastAPI serves these itself; they are not application routes and each domain
# app declares its own copy.
DOCUMENTATION_PATHS = {"/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"}

CONTRACT_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "route_contract.json"
CONTRACT = json.loads(CONTRACT_PATH.read_text())

#: The 44 (method, path) pairs the four functions have to serve between them.
CONTRACT_PAIRS = {(entry["method"], entry["path"]) for entry in CONTRACT["routes"]}

#: The 42 documented operations, with the ids and tags generated clients key on.
#: Two of the 44 routes are absent by design: `/sitemap.xml` and `/robots.txt`
#: carry `include_in_schema=False`, so they are served but never documented.
CONTRACT_OPERATIONS = {
    (entry["method"], entry["path"], entry["operationId"], tuple(entry["tags"]))
    for entry in CONTRACT["operations"]
}

# The plan's section 1 domain map.
EXPECTED_COUNTS = CONTRACT["counts"]


def _route_pairs(app):
    """(method, path) for every application route, documentation excluded."""
    return {
        (method, route.path)
        for route in app.routes
        for method in getattr(route, "methods", ()) or ()
        if method not in ("HEAD", "OPTIONS") and route.path not in DOCUMENTATION_PATHS
    }


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
    """A domain's application routes, minus the shared liveness `/health`.

    `create_app` adds `GET /health` to every application, because the Web
    Adapter polls that path as its readiness check on every cold start and a
    function that does not answer it never starts. It is therefore infrastructure
    rather than one domain's route, and it is excluded everywhere except
    `public`, which declares the database-reporting `/health` the contract
    records and takes the shared one's place.
    """
    pairs = _route_pairs(build_domain_app(name))
    return pairs if name == "public" else pairs - {("GET", "/health")}


def test_the_four_domains_are_the_ones_the_plan_names():
    assert sorted(DOMAIN_NAMES) == ["content", "identity", "public", "resume"]


def test_the_recorded_contract_is_the_shape_the_plan_describes():
    """The fixture itself, checked before anything is measured against it.

    A silently truncated or hand-edited contract would make every assertion
    below pass against the wrong reference, and that is the one failure mode a
    recorded fixture has that a live module did not.
    """
    assert len(CONTRACT_PAIRS) == 44
    assert len(CONTRACT_OPERATIONS) == 42
    assert sum(EXPECTED_COUNTS.values()) == 44
    # Every documented operation is one of the served routes.
    assert {(m, p) for m, p, _, _ in CONTRACT_OPERATIONS} <= CONTRACT_PAIRS
    # The two that are served but deliberately undocumented.
    assert CONTRACT_PAIRS - {(m, p) for m, p, _, _ in CONTRACT_OPERATIONS} == {
        ("GET", "/sitemap.xml"),
        ("GET", "/robots.txt"),
    }


@pytest.mark.parametrize("name", sorted(DOMAIN_NAMES))
def test_a_domain_serves_only_routes_the_contract_records(name):
    assert _domain_pairs(name) - CONTRACT_PAIRS == set()


@pytest.mark.parametrize("name", sorted(DOMAIN_NAMES))
def test_a_domain_documents_the_same_operations_as_the_contract(name):
    """Same operation id and same tags, not merely the same path.

    Operation ids are what a generated client keys on, so a rename is a breaking
    change even when every path is untouched.
    """
    documented = _operations(build_domain_app(name))
    # The shared `/health` carries `include_in_schema=False`, so nothing from it
    # reaches the document; `public`'s own `/health` does and is in the contract.
    assert documented - CONTRACT_OPERATIONS == set()


@pytest.mark.parametrize("name", sorted(DOMAIN_NAMES))
def test_a_domain_serves_exactly_its_own_count(name):
    assert len(_domain_pairs(name)) == EXPECTED_COUNTS[name]


def test_no_two_domains_serve_the_same_route():
    seen = {}
    collisions = []
    for name in DOMAIN_NAMES:
        for pair in _domain_pairs(name):
            if pair in seen:
                collisions.append((pair, seen[pair], name))
            seen[pair] = name
    assert collisions == []


def test_the_union_of_the_four_is_exactly_the_contract():
    union = set()
    for name in DOMAIN_NAMES:
        union |= _domain_pairs(name)
    assert union == CONTRACT_PAIRS
    assert len(union) == sum(EXPECTED_COUNTS.values()) == 44


def test_the_union_of_the_documented_operations_is_the_contract_document():
    union = set()
    for name in DOMAIN_NAMES:
        union |= _operations(build_domain_app(name))
    assert union == CONTRACT_OPERATIONS


def test_root_a_serves_the_same_surface_as_the_four_together():
    """Root A and root B, still two views of one list.

    `app.composition.app` is what the test client is built from and what a
    developer runs locally, and the four entrypoints are what production runs.
    Both walk `wiring.DOMAINS`, so this is the assertion that notices if one
    grows a router the other does not have. It is also what makes the local
    application a faithful stand-in for the deployed split, which is the role
    `app.main` used to be trusted with and was never actually checked for.
    """
    from app.composition.app import build_app

    union = set()
    for name in DOMAIN_NAMES:
        union |= _domain_pairs(name)
    # Root A sets `include_health=False` and takes `public`'s database-reading
    # `/health`, so its route set needs no liveness adjustment.
    assert _route_pairs(build_app()) == union == CONTRACT_PAIRS


@pytest.mark.parametrize("name", sorted(DOMAIN_NAMES))
def test_every_domain_answers_the_adapter_readiness_path(name):
    """`AWS_LWA_READINESS_CHECK_PATH=/health`, so every function must serve it.

    The adapter polls this on every cold start and the function does not start
    until it answers, so a domain that does not declare it times out with no
    application logs at all, which is the least diagnosable Web Adapter failure.
    """
    assert ("GET", "/health") in _route_pairs(build_domain_app(name))


def test_only_public_serves_the_database_reporting_health():
    """The other three get the liveness-only route, which does no I/O.

    Portfolio's `/health` reads the site-content singleton to report
    `database`. On the adapter path that would put a DynamoDB read in every cold
    start and fail the function to start when the table is briefly unavailable,
    so the shared liveness route is what the other three answer with.
    """
    assert "/health" in build_domain_app("public").openapi()["paths"]
    for name in ("content", "resume", "identity"):
        assert "/health" not in build_domain_app(name).openapi()["paths"]


def test_public_reads_no_secret():
    """The least-privilege claim the whole split rests on.

    `public` is the one function with no `secretsmanager:GetSecretValue`. If it
    ever names a required secret, that IAM statement has to come back.
    """
    assert DOMAINS["public"].requires_secrets == ()


def test_service_names_match_what_terraform_sets():
    assert {name: DOMAINS[name].service_name for name in DOMAIN_NAMES} == {
        "content": "webbpulse-portfolio-content",
        "resume": "webbpulse-portfolio-resume",
        "identity": "webbpulse-portfolio-identity",
        "public": "webbpulse-portfolio-public",
    }
