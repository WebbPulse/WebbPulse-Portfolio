"""The gateway's route keys against the routes the applications actually serve.

`test_route_split.py` proves the four domain applications carve the monolith up
correctly. That is a fact about Python, and it stays true no matter what
`terraform/apigateway.tf` says. This file is the other half: that the route keys
API Gateway is configured with actually reach the paths those applications
declare.

The failure this catches is the quiet one section 6 warns about, and it is quiet
in both directions:

- **A path with no key** falls through to `$default` and the monolith answers
  it. Everything returns 200, the cut reads as applied, and nothing has moved.
  `scripts/verify_route_cut.sh` catches this too, but only after an apply and
  only for the paths someone remembered to list in it. This catches it in CI,
  before the apply.
- **A key with no path** is a route pointing at a function that will 404 it, and
  the monolith no longer gets a chance because an explicit key outranks
  `$default`.

The specific edge this exists for is the trailing slash. `build_crud_router`
mounts its collection operations at `/`, so the served path is
`/api/v1/projects/`, and whether either of section 3.5's two keys matches that
path is undocumented: AWS does not say that a trailing slash is normalised away
before route selection, and does not say whether `{proxy+}` can capture an empty
remainder. So the routes map carries an explicit `ANY /api/v1/projects/` key and
these tests hold it in place, because the alternative is a cut that depends on
unspecified behaviour and fails silently by falling through to the monolith.

`matches` below therefore encodes the *conservative* reading, the one the extra
route key makes irrelevant: no normalisation, and a greedy variable needs at
least one character. If AWS is in fact more lenient the extra key is harmless,
since a full match outranks a greedy one either way.

Terraform is parsed rather than planned. A plan needs credentials and a
workspace; the route keys are static text in the module call, and a regex over
them is enough to compare two sets of strings.
"""

import re
from pathlib import Path

import pytest
from starlette.routing import Route

from app.composition.wiring import build_domain_app

REPO = Path(__file__).resolve().parents[3]
APIGATEWAY_TF = REPO / "terraform" / "apigateway.tf"

# Excluded from the comparison for the same reason test_route_split.py excludes
# them: FastAPI serves them itself and every domain application declares its own
# copy, so they are not routed per domain.
DOCUMENTATION_PATHS = {"/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"}

# `<METHOD> <path> = { integration = "<name>" }`, including the interpolated
# form the resume collections are generated with. The interpolation is resolved
# against local.resume_collections below rather than being evaluated, because
# the point is to read what Terraform will build without running Terraform.
ROUTE_ENTRY = re.compile(
    r'"(?P<key>(?:ANY|GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS) /[^"]*)"\s*='
    r'\s*\{\s*integration\s*=\s*"(?P<integration>[^"]+)"'
)

# The `local.<name> = [ "a", "b" ]` lists the route keys interpolate over.
COLLECTION_LIST = re.compile(
    r"^\s*(?P<name>\w+)\s*=\s*\[(?P<body>[^\]]*)\]", re.MULTILINE
)


def _terraform_source() -> str:
    return APIGATEWAY_TF.read_text(encoding="utf-8")


def _locals_lists(source: str) -> dict[str, list[str]]:
    """Every `name = [ "a", "b" ]` list in the file, as plain Python lists."""
    return {
        match.group("name"): re.findall(r'"([^"]+)"', match.group("body"))
        for match in COLLECTION_LIST.finditer(source)
    }


def gateway_route_keys() -> dict[str, set[str]]:
    """Route keys per integration, with `${local.<list>}` expanded.

    Returns e.g. {"resume": {"ANY /api/v1/projects/", ...}, "public": {...}}.
    """
    source = _terraform_source()
    lists = _locals_lists(source)

    keys: dict[str, set[str]] = {}
    for match in ROUTE_ENTRY.finditer(source):
        key = match.group("key")
        integration = match.group("integration")

        interpolations = re.findall(r"\$\{local\.(\w+)\}", key)
        if not interpolations:
            keys.setdefault(integration, set()).add(key)
            continue

        # One loop variable per key in practice. Expand it over its list.
        (name,) = set(interpolations)
        # `${collection}` inside a for expression over local.resume_collections
        # is written `${collection}`, not `${local.resume_collections}`, so this
        # branch only fires if a future key interpolates a local directly.
        for value in lists[name]:
            keys.setdefault(integration, set()).add(
                key.replace("${local.%s}" % name, value)
            )
    return keys


def resume_collections() -> list[str]:
    collections = _locals_lists(_terraform_source())["resume_collections"]
    assert collections, "local.resume_collections is empty or was renamed"
    return collections


def expand_for_expression_keys(integration: str) -> set[str]:
    """Route keys written inside a `for collection in local.<list>` expression.

    The generated keys use the loop variable, `${collection}`, so they cannot be
    expanded by looking the name up in locals. The list they iterate is named on
    the `for` line, which is what this reads.
    """
    source = _terraform_source()
    expanded: set[str] = set()

    for block in re.finditer(
        r"for\s+(?P<var>\w+)\s+in\s+local\.(?P<list>\w+)\s*:(?P<body>.*?)\n\s*\}\s*\n",
        source,
        re.DOTALL,
    ):
        values = _locals_lists(source)[block.group("list")]
        for match in ROUTE_ENTRY.finditer(block.group("body")):
            if match.group("integration") != integration:
                continue
            for value in values:
                expanded.add(
                    match.group("key").replace("${%s}" % block.group("var"), value)
                )
    return expanded


def domain_paths(domain: str) -> set[str]:
    """The application paths a domain serves, documentation and /health aside.

    `app.routes` is typed `list[BaseRoute]`, and only the `Route` subclass
    carries `path` and `methods`, so the isinstance narrowing is what lets
    Pyright read either attribute. It also drops `Mount` and `WebSocketRoute`,
    neither of which is a gateway route, which is the same set the plain
    `methods` truthiness check happened to exclude.
    """
    app = build_domain_app(domain)
    return {
        route.path
        for route in app.routes
        if isinstance(route, Route)
        and route.methods
        and route.path not in DOCUMENTATION_PATHS
        and not (domain != "public" and route.path == "/health")
    }


def matches(route_key: str, path: str) -> bool:
    """Does an API Gateway route key match this request path?

    The three shapes in use, and only those: a literal path, a path ending in a
    greedy `{proxy+}`, and a path with a `{name}` variable segment. API Gateway
    matches a full route first, then a greedy variable, then `$default`; this is
    about whether a key can match at all, not which key wins.
    """
    key_path = route_key.split(" ", 1)[1]

    if key_path.endswith("/{proxy+}"):
        prefix = key_path[: -len("{proxy+}")]
        # Greedy, and it needs at least one character to capture. This is the
        # whole reason the collection needs its own trailing-slash key.
        return path.startswith(prefix) and len(path) > len(prefix)

    key_segments = key_path.split("/")
    path_segments = path.split("/")
    if len(key_segments) != len(path_segments):
        return False
    return all(
        key_segment.startswith("{") or key_segment == path_segment
        for key_segment, path_segment in zip(key_segments, path_segments)
    )


def test_the_terraform_file_is_where_the_test_thinks_it_is():
    assert APIGATEWAY_TF.is_file(), APIGATEWAY_TF


def test_public_route_keys_are_the_four_literal_paths():
    assert gateway_route_keys()["public"] == {
        "GET /health",
        "GET /",
        "GET /sitemap.xml",
        "GET /robots.txt",
    }


def test_resume_has_three_route_keys_per_collection():
    """Three, not section 3.5's two. The third is the trailing-slash form."""
    collections = resume_collections()
    keys = expand_for_expression_keys("resume")

    assert sorted(collections) == sorted(
        ["projects", "experience", "skills", "education", "certifications"]
    )
    for collection in collections:
        assert f"ANY /api/v1/{collection}" in keys
        assert f"ANY /api/v1/{collection}/" in keys
        assert f"ANY /api/v1/{collection}/{{proxy+}}" in keys
    assert len(keys) == 3 * len(collections) == 15


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/projects/",
        "/api/v1/projects",
        "/api/v1/projects/1",
        "/api/v1/certifications/",
        "/api/v1/certifications/42",
    ],
)
def test_a_resume_path_is_matched_by_some_resume_route_key(path):
    keys = expand_for_expression_keys("resume")
    assert any(matches(key, path) for key in keys), path


def test_the_bare_collection_key_does_not_cover_the_trailing_slash():
    """The conservative reading of route matching, pinned as a property of `matches`.

    This asserts what `matches` models, not what AWS promises. AWS documents
    neither trailing-slash normalisation nor whether a greedy variable may
    capture an empty remainder, so the routes map is written to be correct under
    the strictest reading and this pins that reading in place. It is why the
    explicit trailing-slash key exists and why removing it has to fail a test.
    """
    assert not matches("ANY /api/v1/projects", "/api/v1/projects/")
    assert not matches("ANY /api/v1/projects/{proxy+}", "/api/v1/projects/")
    assert matches("ANY /api/v1/projects/", "/api/v1/projects/")


def test_every_resume_route_the_app_serves_has_a_gateway_route_key():
    """The cut is complete: no resume path is left falling through to $default."""
    keys = expand_for_expression_keys("resume")
    unrouted = sorted(
        path
        for path in domain_paths("resume")
        if not any(matches(k, path) for k in keys)
    )
    assert unrouted == []


def test_no_resume_route_key_points_at_a_path_the_app_does_not_serve():
    """The other direction: a key the resume function would 404.

    The bare collection key is the deliberate exception. Its path component is
    what the frontend's `getProjects(true)` requests, because that call emits
    `/projects?featured_only=true/` and the slash lands in the query string;
    `TrailingSlashMiddleware` is what makes it reach the handler.
    """
    paths = domain_paths("resume")
    bare_collections = {f"/api/v1/{c}" for c in resume_collections()}

    for key in expand_for_expression_keys("resume"):
        key_path = key.split(" ", 1)[1]
        if key_path in bare_collections or key_path.endswith("/{proxy+}"):
            continue
        assert any(matches(key, path) for path in paths), key


def test_routed_domains_and_route_keys_move_together():
    """`local.routed_lambda_domains` gates the integrations map.

    The module's `every_integration_is_routed` check fails a plan on an
    integration no route can reach, so a domain listed there without route keys
    breaks the plan, and route keys without the listing break it on the
    integration lookup. Both halves of a cut land in one commit or neither does.
    """
    routed = _locals_lists(_terraform_source())["routed_lambda_domains"]
    keyed = set(gateway_route_keys()) | {"resume"}

    assert routed == ["public", "resume"]
    for domain in routed:
        assert domain in keyed, domain
    assert "legacy" not in routed
