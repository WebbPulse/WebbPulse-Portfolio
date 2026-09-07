"""The route split, asserted rather than described.

The plan's section 1 says the 44 application routes divide 14 content, 25
resume, 1 identity and 4 public. These tests are what makes that a fact about
the code instead of a claim in a document, and they are the thing that notices
if a domain quietly re-acquires the whole router after a refactor.

Four properties, and each one catches a different mistake:

- **Subset.** Every route a domain serves is a route the monolith serves, with
  the same path, method, operation id and tags. A path that drifts here breaks a
  generated client the moment the gateway routes that prefix away from the
  monolith, and nothing before production would notice.
- **No overlap.** No two domains serve the same method and path. Two functions
  answering one route means API Gateway picks and the other is dead code that
  still gets deployed, patched and paid for.
- **Union.** The four together serve exactly the monolith's 44. A route in none
  of them 404s the moment `default_integration` stops pointing at the monolith,
  which is section 6's last step.
- **Counts.** The split is 14/25/1/4, which is what the Terraform route map in
  section 3.5 is written against.
"""

import pytest

from app.composition.wiring import DOMAIN_NAMES, DOMAINS, build_domain_app
from app.main import app as monolith

# FastAPI serves these itself; they are not application routes and each domain
# app declares its own copy.
DOCUMENTATION_PATHS = {"/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"}

# The plan's section 1 domain map.
EXPECTED_COUNTS = {"content": 14, "resume": 25, "identity": 1, "public": 4}


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
    `public`, which declares the database-reporting `/health` the monolith has
    always served and takes the shared one's place.
    """
    pairs = _route_pairs(build_domain_app(name))
    return pairs if name == "public" else pairs - {("GET", "/health")}


@pytest.fixture(scope="module")
def monolith_pairs():
    return _route_pairs(monolith)


@pytest.fixture(scope="module")
def monolith_operations():
    return _operations(monolith)


def test_the_four_domains_are_the_ones_the_plan_names():
    assert sorted(DOMAIN_NAMES) == ["content", "identity", "public", "resume"]


@pytest.mark.parametrize("name", sorted(DOMAIN_NAMES))
def test_a_domain_serves_only_routes_the_monolith_serves(name, monolith_pairs):
    assert _domain_pairs(name) - monolith_pairs == set()


@pytest.mark.parametrize("name", sorted(DOMAIN_NAMES))
def test_a_domain_documents_the_same_operations_as_the_monolith(
    name, monolith_operations
):
    """Same operation id and same tags, not merely the same path.

    Operation ids are what a generated client keys on, so a rename is a breaking
    change even when every path is untouched.
    """
    documented = _operations(build_domain_app(name))
    # The shared `/health` carries `include_in_schema=False`, so nothing from it
    # reaches the document; `public`'s own `/health` does and is in the monolith.
    assert documented - monolith_operations == set()


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


def test_the_union_of_the_four_is_exactly_the_monolith(monolith_pairs):
    union = set()
    for name in DOMAIN_NAMES:
        union |= _domain_pairs(name)
    assert union == monolith_pairs
    assert len(union) == sum(EXPECTED_COUNTS.values()) == 44


def test_the_union_of_the_documented_operations_is_the_monolith_document(
    monolith_operations,
):
    union = set()
    for name in DOMAIN_NAMES:
        union |= _operations(build_domain_app(name))
    assert union == monolith_operations


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
