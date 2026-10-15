"""The gateway's route keys against the routes the public application actually serves."""

import re
from pathlib import Path

from app.common.composition.wiring import build_domain_app

from ..routes import DOCUMENTATION_PATHS, served_routes

REPO = Path(__file__).resolve().parents[3]
APIGATEWAY_TF = REPO / "terraform" / "apigateway.tf"

ROUTE_ENTRY = re.compile(
    r'"(?P<key>(?:ANY|GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS) /[^"]*)"\s*='
    r'\s*\{\s*integration\s*=\s*"(?P<integration>[^"]+)"'
)

COLLECTION_LIST = re.compile(r"^\s*(?P<name>\w+)\s*=\s*\[(?P<body>[^\]]*)\]", re.MULTILINE)


def _terraform_source() -> str:
    """The apigateway.tf file as text."""
    return APIGATEWAY_TF.read_text(encoding="utf-8")


def _strip_comments(source: str) -> str:
    """The file with `#` comment lines removed, for checks about configuration."""
    return "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))


def gateway_route_keys() -> dict[str, set[str]]:
    """Route keys per integration, as written in `apigateway.tf`."""
    keys: dict[str, set[str]] = {}
    for match in ROUTE_ENTRY.finditer(_terraform_source()):
        keys.setdefault(match.group("integration"), set()).add(match.group("key"))
    return keys


def public_method_paths() -> set[str]:
    """`METHOD /path` for every application route the public domain serves."""
    app = build_domain_app("public")
    return {
        f"{method} {route.path}"
        for route in served_routes(app)
        if getattr(route, "methods", None) and route.path not in DOCUMENTATION_PATHS
        for method in route.methods
        if method not in ("HEAD", "OPTIONS")
    }


def test_the_terraform_file_is_where_the_test_thinks_it_is():
    """The Terraform file this module parses is where it expects it."""
    assert APIGATEWAY_TF.is_file(), APIGATEWAY_TF


def test_public_is_the_only_integration():
    """Every route key goes to the public function; no other domain is deployed."""
    assert set(gateway_route_keys()) == {"public"}


def test_public_route_keys_are_the_three_literal_paths():
    """The public integration is wired to exactly its three literal paths."""
    assert gateway_route_keys()["public"] == {
        "GET /health",
        "GET /",
        "GET /api/v1/public/figures",
    }


def test_route_keys_and_served_routes_are_the_same_set():
    """No served route falls through, and no key points at a path the function would 404."""
    assert gateway_route_keys()["public"] == public_method_paths()


def test_routed_domains_list_only_public():
    """`local.routed_lambda_domains` gates the integrations map."""
    match = COLLECTION_LIST.search(_terraform_source())
    assert match is not None and match.group("name") == "routed_lambda_domains"
    assert re.findall(r'"([^"]+)"', match.group("body")) == ["public"]


def test_no_route_key_ends_in_a_slash():
    """API Gateway rejects a route key whose path ends in a slash."""
    for key in gateway_route_keys()["public"]:
        key_path = key.split(" ", 1)[1]
        assert key_path == "/" or not key_path.endswith("/"), key


def test_no_default_route():
    """`default_integration` is null, so an unrouted path never reaches a function."""
    source = _terraform_source()
    assert re.search(r"^\s*default_integration\s*=\s*null\s*$", source, re.MULTILINE)
    assert not re.search(r'^\s*default_integration\s*=\s*"', source, re.MULTILINE)


def test_no_identity_jwt_authorizer():
    """Nothing on the public surface needs a caller, so the gateway carries no JWT authorizer."""
    source = _strip_comments(_terraform_source())
    assert "identity_jwt" not in source
    assert "require_identity_jwt" not in source
