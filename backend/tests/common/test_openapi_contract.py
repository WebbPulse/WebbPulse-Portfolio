"""The public API contract, pinned."""

from app.common.composition.app import build_app
from tests.routes import method_path_pairs

app = build_app()

EXPECTED_OPERATIONS = [
    (
        "GET",
        "/api/v1/public/figures",
        "get_figures_api_v1_public_figures_get",
        ["public"],
    ),
    ("GET", "/", "root__get", []),
    ("GET", "/health", "health_check_health_get", []),
]


def _documented_operations():
    """(method, path, operationId, tags) for every documented operation."""
    document = app.openapi()
    return [
        (method.upper(), path, operation["operationId"], operation.get("tags", []))
        for path, item in document["paths"].items()
        for method, operation in item.items()
    ]


def test_openapi_operations_are_unchanged():
    """Same 3 operations, same ids, same tags."""
    documented = _documented_operations()
    hashable = {(method, path, operation_id, tuple(tags)) for method, path, operation_id, tags in documented}
    assert hashable == {
        (method, path, operation_id, tuple(tags)) for method, path, operation_id, tags in EXPECTED_OPERATIONS
    }
    assert len(documented) == len(hashable) == len(EXPECTED_OPERATIONS) == 3


def test_route_count_matches_the_domain_map():
    """3 application routes, all public, beside the 4 documentation routes."""
    pairs = method_path_pairs(app, skip_documentation=False)
    documentation = {
        (method, path)
        for method, path in pairs
        if path in ("/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json")
    }
    assert len(documentation) == 4
    assert pairs - documentation == {(method, path) for method, path, _, _ in EXPECTED_OPERATIONS}


def test_the_split_serves_this_exact_contract():
    """The whole-surface document, reassembled from the deployed domain apps."""
    from app.common.composition.wiring import DOMAIN_NAMES, build_domain_app

    union = set()
    for name in DOMAIN_NAMES:
        document = build_domain_app(name).openapi()
        for path, item in document["paths"].items():
            for method, operation in item.items():
                union.add(
                    (
                        method.upper(),
                        path,
                        operation["operationId"],
                        tuple(operation.get("tags", ())),
                    )
                )

    expected = {(method, path, operation_id, tuple(tags)) for method, path, operation_id, tags in EXPECTED_OPERATIONS}
    assert union == expected
