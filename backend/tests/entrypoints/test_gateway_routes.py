"""The gateway's route keys against the routes the applications actually serve.

`test_route_split.py` proves the four domain applications carve the monolith up
correctly. That is a fact about Python, and it stays true no matter what
`terraform/apigateway.tf` says. This file is the other half: that the route keys
API Gateway is configured with actually reach the paths those applications
declare.

The failure this catches is the quiet one section 6 warns about, and it is quiet
in both directions:

- **A path with no key** is now unreachable. While the monolith existed it fell
  through to `$default`, everything returned 200, the cut read as applied and
  nothing had moved. Section 6's retirement set `default_integration = null`, so
  there is no `$default`: a path no key matches gets API Gateway's own 404 and
  reaches no function at all. `scripts/verify_route_cut.sh` catches this too,
  but only after an apply and only for the paths someone remembered to list in
  it. This catches it in CI, before the apply, which matters more now that the
  consequence is a 404 to every caller rather than a routing smell.
- **A key with no path** is a route pointing at a function that will 404 it.

Both directions are exhaustiveness claims, and with `$default` gone the first
one is what makes `default_integration = null` safe. `test_no_default_route`
asserts the null directly, so the two halves cannot drift: a `$default` quietly
re-added would make an unrouted path look fine again, and an unrouted path added
while `$default` is null is an outage.

The specific edge this exists for is the trailing slash. `build_crud_router`
mounts its collection operations at `/`, so the served path is
`/api/v1/projects/`. A literal `ANY /api/v1/projects/` key cannot exist: the
first cut 2 apply proved API Gateway rejects any route key ending in a slash
("Part of the given route key path is empty"). So the trailing-slash path can
only be reached through the bare key or the greedy key, and AWS documents
neither trailing-slash normalisation nor whether `{proxy+}` may capture an empty
remainder.

`matches` below therefore models the reading the routes map depends on: a
trailing slash on the request is normalised away before comparison, so the bare
collection key covers `/api/v1/projects/`, and a greedy variable needs at least
one character. That reading is an assumption, not a promise from AWS, and it is
checked against the real gateway after every deploy by the verify-route-cuts job,
which probes both slash forms of every collection.

Terraform is parsed rather than planned. A plan needs credentials and a
workspace; the route keys are static text in the module call, and a regex over
them is enough to compare two sets of strings.

Almost all of them are in `terraform/apigateway.tf`. The identity standard's M0
spike puts one route, `whoami`, in `terraform/identity_spike.tf` instead, as its
own `aws_apigatewayv2_route` rather than a routes-map entry, because it has to
be created after the JWT authorizer while the rest of the route set has to be
created before it. `standalone_route_keys` reads that file, and the tests around
it pin the split so it cannot be tidied away.
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

# The same entry, but only when it goes on to set `authorization_type = "NONE"`.
# Every other entry in the map omits the argument and takes the module's CUSTOM
# default, which is the staging access gate, so this reads the map's whole
# anonymous surface.
# `test_the_anonymous_surface_is_exactly_the_two_discovery_documents` is what it
# exists for.
ANONYMOUS_ROUTE_ENTRY = re.compile(
    r'"((?:ANY|GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS) /[^"]*)"\s*='
    r'\s*\{\s*integration\s*=\s*"[^"]+"\s*'
    r'authorization_type\s*=\s*"NONE"'
)

# The `local.<name> = [ "a", "b" ]` lists the route keys interpolate over.
COLLECTION_LIST = re.compile(
    r"^\s*(?P<name>\w+)\s*=\s*\[(?P<body>[^\]]*)\]", re.MULTILINE
)


def _terraform_source() -> str:
    return APIGATEWAY_TF.read_text(encoding="utf-8")


def _strip_comments(source: str) -> str:
    """The file with `#` comment lines removed, for checks about configuration.

    apigateway.tf carries a lot of narrative about how the strangler ran, which
    names things that no longer exist in the configuration. A test asserting a
    name is gone has to look at what Terraform reads, not at what the file says.
    Only whole-line comments are stripped, which is every comment in this file.
    """
    return "\n".join(
        line for line in source.splitlines() if not line.lstrip().startswith("#")
    )


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


def content_prefixes() -> list[str]:
    prefixes = _locals_lists(_terraform_source())["content_prefixes"]
    assert prefixes, "local.content_prefixes is empty or was renamed"
    return prefixes


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

    # The modelled assumption: a trailing slash on the request is normalised
    # away before route selection. A key can never carry one, so without this
    # the served collection path could match nothing. Verified against the real
    # gateway by scripts/verify_route_cut.sh, not by this test.
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]

    if key_path.endswith("/{proxy+}"):
        prefix = key_path[: -len("{proxy+}")]
        # Greedy, and it needs at least one character to capture.
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


def test_resume_has_two_route_keys_per_collection():
    """Two, as section 3.5 lists. A trailing-slash key is not a legal route key."""
    collections = resume_collections()
    keys = expand_for_expression_keys("resume")

    assert sorted(collections) == sorted(
        ["projects", "experience", "skills", "education", "certifications"]
    )
    for collection in collections:
        assert f"ANY /api/v1/{collection}" in keys
        assert f"ANY /api/v1/{collection}/{{proxy+}}" in keys
    assert len(keys) == 2 * len(collections) == 10


def test_no_route_key_ends_in_a_slash():
    """API Gateway rejects a route key whose path ends in a slash.

    "BadRequestException: Part of the given route key path is empty" on every
    `ANY /api/v1/<collection>/` key in the first cut 2 apply. The root `GET /`
    is the one legal exception, because its path is only the slash.
    """
    for domain, keys in gateway_route_keys().items():
        for key in expand_for_expression_keys(domain) if domain == "resume" else keys:
            key_path = key.split(" ", 1)[1]
            assert key_path == "/" or not key_path.endswith("/"), key


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


def test_the_bare_collection_key_covers_the_trailing_slash_under_normalisation():
    """The modelled reading, pinned as a property of `matches`.

    This asserts what `matches` models, not what AWS promises: the trailing
    slash is normalised away, so the bare key covers the served collection path
    and the greedy key still needs a non-empty remainder. If the CI probe ever
    shows the gateway sending `/api/v1/projects/` to the monolith, this model is
    wrong and the fix is in the application (serve the bare path), not here.
    """
    assert matches("ANY /api/v1/projects", "/api/v1/projects/")
    assert not matches("ANY /api/v1/projects/{proxy+}", "/api/v1/projects/")
    assert matches("ANY /api/v1/projects/{proxy+}", "/api/v1/projects/1")


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

    Since the monolith was retired this list is the whole integrations map, not
    the part of it that had been carved off, so `legacy` being absent is the
    retirement rather than a domain awaiting its cut.
    """
    routed = _locals_lists(_terraform_source())["routed_lambda_domains"]
    keyed = set(gateway_route_keys()) | {"resume", "content"}

    assert routed == ["public", "resume", "content", "identity"]
    for domain in routed:
        assert domain in keyed, domain
    assert "legacy" not in routed


def test_no_default_route():
    """`default_integration` is null: section 6's retirement of the monolith.

    This is the assertion the rest of the file leans on. Every other test here
    proves the route keys cover the paths the applications serve, and that only
    matters because there is nothing behind them: with a `$default` an uncovered
    path is served by whatever it names, and the exhaustiveness tests become
    advisory. With null it is a 404.

    It also pins the direction of the change. Re-adding a `default_integration`
    is a deliberate rollback of the retirement, and it should fail here rather
    than quietly restore a fall-through the four cuts spent their whole design
    removing.
    """
    source = _terraform_source()

    assert re.search(r"^\s*default_integration\s*=\s*null\s*$", source, re.MULTILINE), (
        "default_integration must be null: the monolith is retired and there is "
        "no integration left to serve $default."
    )
    assert not re.search(r'^\s*default_integration\s*=\s*"', source, re.MULTILINE), (
        "default_integration names an integration, which re-creates $default."
    )


def test_no_legacy_integration():
    """The monolith's integration is gone from the integrations map.

    `legacy` was the only entry that named `module.lambda_api`, and it carried
    the one `lambda_permission_statement_id` override in the module call, so its
    absence is what retires both the integration and the bare
    `AllowAPIGatewayInvoke` permission. A route key naming it would fail the
    plan on the module's own precondition, but the integrations map itself is
    not otherwise covered by any test here.

    Comments are stripped before the check. The file still explains what
    `legacy` was and why retiring it renames no other permission, and that prose
    should stay readable without failing a test about configuration.
    """
    source = _strip_comments(_terraform_source())

    assert "legacy" not in source, (
        "apigateway.tf still configures `legacy`, the retired monolith integration."
    )
    assert "lambda_api" not in source, (
        "apigateway.tf still references module.lambda_api, the retired monolith."
    )


def test_content_has_two_route_keys_per_mounted_prefix():
    """Two, not the three cut 2 used. The trailing-slash key cannot exist.

    Cut 2 added a literal `ANY /api/v1/<collection>/` key per collection to
    settle an ambiguity the AWS documentation leaves open. Applying it settled
    the ambiguity a different way: API Gateway rejected every one of those keys
    with "BadRequestException: Part of the given route key path is empty". A
    route key path segment may not be empty, so the trailing-slash form is not a
    key that can be created at all, and `content` is written to two keys per
    prefix from the start. This test is what stops it being reintroduced.
    """
    prefixes = content_prefixes()
    keys = expand_for_expression_keys("content")

    assert sorted(prefixes) == ["posts", "site-content"]
    for prefix in prefixes:
        assert f"ANY /api/v1/{prefix}" in keys
        assert f"ANY /api/v1/{prefix}/{{proxy+}}" in keys
        assert f"ANY /api/v1/{prefix}/" not in keys
    assert len(keys) == 2 * len(prefixes) == 4


def test_no_route_key_anywhere_in_the_file_ends_in_a_trailing_slash():
    """The rejection is a property of API Gateway, so it binds every domain.

    Scoped to the whole routes map rather than to `content`, because the next
    cut copies whatever shape it finds here and the apply-time failure is the
    same for `identity` as it was for `resume`.
    """
    offenders = sorted(
        key
        for keys in gateway_route_keys().values()
        for key in keys
        if key.endswith("/") and key.split(" ", 1)[1] != "/"
    )
    assert offenders == []


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/posts",
        "/api/v1/posts/admin",
        "/api/v1/posts/admin/1",
        "/api/v1/posts/admin/1/publish",
        "/api/v1/posts/categories",
        "/api/v1/posts/categories/2",
        "/api/v1/posts/category/engineering",
        "/api/v1/posts/some-slug",
        "/api/v1/site-content",
    ],
)
def test_a_content_path_is_matched_by_some_content_route_key(path):
    keys = expand_for_expression_keys("content")
    assert any(matches(key, path) for key in keys), path


def test_the_greedy_posts_key_covers_the_whole_subtree_however_deep():
    """`{proxy+}` captures the remainder, not one segment.

    This is why `content`'s deep tree needs no more keys than `resume`'s flat
    collections: `/admin/{post_id}/publish` is three segments below the prefix
    and still lands on the same key.
    """
    key = "ANY /api/v1/posts/{proxy+}"
    assert matches(key, "/api/v1/posts/admin")
    assert matches(key, "/api/v1/posts/admin/1/publish")
    assert not matches(key, "/api/v1/posts")


def test_every_content_route_the_app_serves_has_a_gateway_route_key():
    """The cut is complete: no content path is left falling through to $default.

    Split in two, because the two mounted prefixes serve two kinds of path and
    only one kind can be settled by reading text.

    Every path with at least one segment below its prefix is matched by that
    prefix's greedy key under any reading of route matching, so those are
    asserted unconditionally.

    The two collection roots, `/api/v1/posts/` and `/api/v1/site-content/`, are
    the open case. No literal key can cover them: API Gateway rejects a route
    key ending in a slash. So each is served by the bare key or by the greedy
    one, and which is a question about the gateway that no amount of parsing
    answers. `matches` encodes the strict reading, in which neither matches, and
    this test does not assert that reading either way. What it does assert is
    that the only paths left over are those two, so a genuinely missing key
    still fails here. `scripts/verify_route_cut.sh` probes both slash forms
    against the real gateway and is what closes this gap after the apply.
    """
    keys = expand_for_expression_keys("content")
    collection_roots = {f"/api/v1/{prefix}/" for prefix in content_prefixes()}

    unrouted = sorted(
        path
        for path in domain_paths("content")
        if not any(matches(k, path) for k in keys)
    )
    assert set(unrouted) <= collection_roots, unrouted


def test_the_deep_content_paths_are_routed_under_any_reading():
    """The part of the cut that does not depend on the trailing-slash question."""
    keys = expand_for_expression_keys("content")
    deep = [
        path
        for path in domain_paths("content")
        if not path.endswith("/") and path.startswith("/api/v1/")
    ]
    assert deep, "content serves no path below a prefix, which cannot be right"
    for path in deep:
        assert any(matches(key, path) for key in keys), path


def test_no_content_route_key_points_at_a_path_the_app_does_not_serve():
    """The other direction: a key the content function would 404.

    The bare prefix keys are the deliberate exception, as they are for `resume`:
    their path component is what a request whose slash lands in the query string
    arrives as, and `TrailingSlashMiddleware` is what makes it reach the
    handler. `site-content`'s greedy key is the second exception. The singleton
    declares no sub-path today, so the key matches nothing the application
    serves; it is kept so that adding one cannot silently leave it on the
    monolith.
    """
    paths = domain_paths("content")
    bare_prefixes = {f"/api/v1/{prefix}" for prefix in content_prefixes()}

    for key in expand_for_expression_keys("content"):
        key_path = key.split(" ", 1)[1]
        if key_path in bare_prefixes or key_path.endswith("/{proxy+}"):
            continue
        assert any(matches(key, path) for path in paths), key


#: Route keys served by the `identity` integration that belong to the identity
#: standard's M0 spike rather than to cut 4. Every one of them is gated behind
#: `local.identity_spike_enabled`, which is false by default, so they exist in
#: no plan unless the spike has been switched on.
#:
#: The two `.well-known` keys and the mint route are entries in
#: `apigateway.tf`'s routes map. `whoami` is not, and that split is the spike's
#: whole ordering fix rather than a filing preference: `whoami` is the one route
#: that names the JWT authorizer, API Gateway validates the issuer by fetching
#: the discovery document when the authorizer is created, and a routes-map entry
#: naming the authorizer would make every route on the API wait on an authorizer
#: that needs two of those routes to already answer. So `whoami` is a standalone
#: `aws_apigatewayv2_route` in `identity_spike.tf`. `spike_route_keys()` below
#: reads both files, and `test_the_spike_keys_are_the_two_expected_ones` pins
#: which file each key has to come from.
#:
#: The mint route is in the map rather than beside `whoami` because it names no
#: authorizer at all: it sets no `authorization_type`, so it takes the module's
#: CUSTOM default and sits behind the staging access gate, which is the only
#: thing standing in front of a route that signs a token for an arbitrary
#: subject. It was missing from the map entirely when the spike first went live,
#: which made `POST /api/identity/spike/token` a gateway 404 with a handler
#: behind it that nothing could reach.
#:
#: They are excluded from `identity_route_keys()` rather than folded into it
#: because every assertion that helper feeds is about cut 4's permanent shape:
#: two keys, both `ANY`, both under `/api/v1/admin`. The spike is deliberately
#: none of those things, and widening those assertions to accommodate it would
#: retire exactly the invariants they exist to hold. `test_the_spike_keys_are_
#: the_two_expected_ones` below pins the spike's own shape instead, so the
#: exclusion cannot quietly grow.
#:
#: This set goes when the spike does.
IDENTITY_SPIKE_ROUTE_KEYS = {
    "POST /api/identity/spike/token",
    "GET /api/identity/spike/whoami",
}

#: The spike's routes-map keys: just the mint route now. The rest of
#: `IDENTITY_SPIKE_ROUTE_KEYS` is the standalone `whoami`.
IDENTITY_SPIKE_ROUTES_MAP_KEYS = {
    "POST /api/identity/spike/token",
}

#: M1's permanent identity keys, which are excluded from `identity_route_keys()`
#: for the same reason the spike's are: every assertion that helper feeds is
#: about cut 4's shape, which is two `ANY` keys under `/api/v1/admin`, and M1 is
#: deliberately none of those things.
#:
#: Unlike the spike's, these are unconditional. They are created whether or not
#: `identity_spike_enabled` is set, because M2 creates a JWT authorizer whose
#: CreateAuthorizer call fetches the discovery document before the authorizer
#: exists, so the two documents have to already be live on their own apply. The
#: spike used to own the `.well-known` pair and gated it behind its own flag,
#: which would have made M2's first apply depend on a spike nobody wants to keep
#: switched on. `terraform/identity.tf` and `build_identity_router` own them now.
#:
#: All three sit under `/api/auth`, which is the issuer's path. API Gateway
#: appends the discovery path to the issuer with its path included, and follows
#: the `jwks_uri` the returned document advertises, which `IdentitySettings`
#: builds from the issuer too. So the documents answer under the issuer or they
#: answer nowhere the authorizer looks.
#:
#: `GET /api/auth/health` is the identity function's own health route, which is
#: the router's `/health` seen through that same mount. It is not `GET /health`,
#: which already belongs to the `public` domain.
IDENTITY_M1_ROUTE_KEYS = {
    "GET /api/auth/.well-known/jwks.json",
    "GET /api/auth/.well-known/openid-configuration",
    "GET /api/auth/health",
}

#: The M1 keys that carry `authorization_type = "NONE"`, which is a deliberate
#: hole in the staging access gate and should stay exactly two documents wide.
#: The health route is pointedly not in here: nothing outside the gate needs it,
#: so it takes the module's CUSTOM default like every other gated route.
IDENTITY_M1_ANONYMOUS_KEYS = {
    "GET /api/auth/.well-known/jwks.json",
    "GET /api/auth/.well-known/openid-configuration",
}

#: M2's six flow keys, excluded from `identity_route_keys()` for exactly the
#: reason M1's three are: that helper's assertions are about cut 4's shape, two
#: `ANY` keys under `/api/v1/admin`, and these are not that.
#:
#: They sit under `/api/auth` for the same reason M1's do. `build_identity_router`
#: mounts every route it declares under the issuer's path, so a key here is the
#: served path rather than a rewrite of one.
#:
#: None of them is anonymous. They take the module's CUSTOM default like
#: `GET /api/auth/health`, so `test_the_anonymous_surface_is_exactly_the_two_
#: discovery_documents` still holds at exactly two documents: these are state
#: changing routes, and the gate hole exists only because API Gateway fetches
#: those two documents itself at CreateAuthorizer time.
IDENTITY_M2_ROUTE_KEYS = {
    "POST /api/auth/register",
    "POST /api/auth/login",
    "POST /api/auth/password",
    "POST /api/auth/refresh",
    "POST /api/auth/logout",
    "POST /api/auth/logout-all",
}

#: M3's four email keys, excluded from `identity_route_keys()` for the same
#: reason M1's three and M2's six are.
#:
#: Two request routes and two confirm routes, one pair for verifying an address
#: and one pair for resetting a password. `build_identity_router` mounts them
#: only when it is handed both an `EmailSender` and an identity-tokens store,
#: which `composition/identity.py` supplies whenever `IDENTITY_EMAIL_FROM` is
#: set. The route keys are unconditional anyway: a key with no path behind it is
#: a 404 from the function, while a path with no key is a gateway 404 that
#: reaches no function at all, and the second is the worse failure.
#:
#: None of them is anonymous, for the same reason none of M2's is. Both request
#: routes answer 200 for any address by design, which is section 5.4's
#: enumeration rule and not a reason to put them outside the staging gate.
IDENTITY_M3_ROUTE_KEYS = {
    "POST /api/auth/verify-email",
    "POST /api/auth/verify-email/confirm",
    "POST /api/auth/reset",
    "POST /api/auth/reset/confirm",
}

IDENTITY_SPIKE_TF = REPO / "terraform" / "identity_spike.tf"

# `route_key = "<METHOD> <path>"` on a standalone aws_apigatewayv2_route. The
# routes-map form is a map key rather than an argument, so `ROUTE_ENTRY` does
# not match this and this does not match those.
STANDALONE_ROUTE_KEY = re.compile(
    r'^\s*route_key\s*=\s*"'
    r'(?P<key>(?:ANY|GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS) /[^"]*)"',
    re.MULTILINE,
)


def standalone_route_keys() -> set[str]:
    """Route keys declared as their own resource rather than in the routes map.

    Today this is the spike's `whoami` and nothing else. Standalone routes are
    the exception in this repository, for the reason `apigateway.tf` gives at
    length: a route in the map is addressed by its key and its authorization is
    resolved by the module, and both of those are worth keeping. `whoami` is out
    of the map only because it has to be created after an authorizer that has to
    be created after the map's own routes.
    """
    return {
        match.group("key")
        for match in STANDALONE_ROUTE_KEY.finditer(
            IDENTITY_SPIKE_TF.read_text(encoding="utf-8")
        )
    }


def spike_route_keys() -> set[str]:
    """Every M0 spike route key Terraform will create, from both files."""
    return (
        gateway_route_keys()["identity"] & IDENTITY_SPIKE_ROUTE_KEYS
    ) | standalone_route_keys()


def identity_route_keys() -> set[str]:
    """Cut 4's keys, which are literal rather than generated.

    Cuts 2 and 3 loop over a local, so their keys have to be expanded with
    `expand_for_expression_keys`. Cut 4 covers one prefix and writes both keys
    out, so `gateway_route_keys` reads them straight from the file.

    The M0 spike's keys, M1's permanent identity keys, M2's six flow keys and
    M3's four email keys are all subtracted. See `IDENTITY_SPIKE_ROUTE_KEYS`,
    `IDENTITY_M1_ROUTE_KEYS`, `IDENTITY_M2_ROUTE_KEYS` and
    `IDENTITY_M3_ROUTE_KEYS`.
    """
    keys = (
        gateway_route_keys()["identity"]
        - IDENTITY_SPIKE_ROUTE_KEYS
        - IDENTITY_M1_ROUTE_KEYS
        - IDENTITY_M2_ROUTE_KEYS
        - IDENTITY_M3_ROUTE_KEYS
    )
    assert keys, "no identity route keys were parsed out of apigateway.tf"
    return keys


def test_the_spike_keys_are_the_two_expected_ones():
    """The M0 spike's route keys, pinned so the exclusion above cannot grow.

    Either both are present, because the spike is switched on in the
    configuration, or neither is, because it has been removed with the rest of
    the spike. A partial set means somebody edited one and not the other, which
    is exactly what happened when the spike first went live: `spike.py` declared
    the mint handler and no route key was ever created for it, so the endpoint
    was a gateway 404 and no token could be obtained to exercise `whoami`.

    This was four keys through M0. The two `.well-known` documents moved to
    `IDENTITY_M1_ROUTE_KEYS` when M1 made them permanent, so what is left here
    is the spike's own two application routes.

    The shape of each one matters, and it is the reason these are pinned rather
    than merely excluded:

    - Both are literal, with no `{proxy+}`. A greedy key under
      `/api/identity/spike/` would claim `whoami`, whose authorization is
      supposed to come from the JWT authorizer rather than from the gate.
    - The methods are the served methods rather than `ANY`, because the spike's
      two routes split their authorization across two different authorizers and
      neither one owns the prefix.
    - Both spike paths are outside `/api/v1` so a throwaway experiment stays out
      of the published contract in `tests/fixtures/route_contract.json`.
    """
    present = spike_route_keys()
    assert present in (set(), IDENTITY_SPIKE_ROUTE_KEYS), sorted(present)


def test_the_m1_keys_are_present_unconditionally():
    """M1's three keys exist whether or not the spike does.

    This is the load-bearing difference between M1 and the M0 spike it grew out
    of, and it is what `IDENTITY_M1_ROUTE_KEYS` exists to hold. The spike gated
    the `.well-known` pair behind `identity_spike_enabled`; M1 does not gate it
    behind anything, because M2's `CreateAuthorizer` fetches the discovery
    document during the apply that creates the authorizer, and a document that
    only exists when a throwaway flag is on is a document M2 cannot rely on.
    """
    assert IDENTITY_M1_ROUTE_KEYS <= gateway_route_keys()["identity"]


def test_the_m1_keys_are_literal_and_do_not_end_in_a_slash():
    """No `{proxy+}` and no trailing slash on any permanent identity key.

    Literal, because two of the three carry `authorization_type = "NONE"` and a
    greedy key would widen that hole in the staging access gate from two
    documents to anything under `/.well-known/`.

    No trailing slash, because a route key that ends in one is rejected at apply
    time with a BadRequestException saying part of the path is empty, while the
    plan stays green. That is an apply-time failure this file exists to catch at
    test time.
    """
    for key in IDENTITY_M1_ROUTE_KEYS:
        path = key.split(" ", 1)[1]
        assert "{" not in key, key
        assert not path.endswith("/"), key


def test_the_m2_flow_keys_are_present_unconditionally():
    """M2's six flow routes exist, whether or not the spike does.

    Unconditional for the same reason M1's three are, and for one more: the
    identity function serves them from the moment `composition/identity.py`
    hands `build_identity_router` hooks and a credential store, so a route key
    that was gated behind a flag would be a live route with no way to reach it.
    """
    assert IDENTITY_M2_ROUTE_KEYS <= gateway_route_keys()["identity"]


def test_the_m2_keys_are_literal_and_do_not_end_in_a_slash():
    """No `{proxy+}` and no trailing slash, exactly as M1's are checked.

    A greedy key here would be worse than a greedy one on the documents: these
    are state changing routes, and `POST /api/auth/{proxy+}` would hand the
    identity function every path under `/api/auth` including ones no milestone
    has written yet.

    The trailing slash is the same apply-time BadRequestException M1's test
    catches, and it stays green in a plan.
    """
    for key in IDENTITY_M2_ROUTE_KEYS:
        path = key.split(" ", 1)[1]
        assert "{" not in key, key
        assert not path.endswith("/"), key


def test_every_m2_key_is_a_post():
    """All six are state changing, which is why none of them is anonymous.

    Spelled out because the method is what the next test's argument rests on: a
    GET added to this set would be a read that somebody might reasonably think
    belongs outside the gate, and it does not.
    """
    for key in IDENTITY_M2_ROUTE_KEYS:
        assert key.startswith("POST "), key


def test_no_m2_flow_route_is_anonymous():
    """The staging access gate stays exactly two documents wide.

    `GET /api/auth/health` is the precedent these follow: they omit
    `authorization_type` and take the module's CUSTOM default, which is the gate
    authorizer in staging and nothing in production. Marking a login or a
    refresh `NONE` would put a state changing route outside the gate, and the
    gate hole exists only because API Gateway fetches the two discovery
    documents itself, from its own infrastructure, with no cookie to present.
    """
    anonymous = set(ANONYMOUS_ROUTE_ENTRY.findall(_terraform_source()))

    assert IDENTITY_M2_ROUTE_KEYS & anonymous == set(), sorted(
        IDENTITY_M2_ROUTE_KEYS & anonymous
    )


def test_the_m2_keys_route_to_the_identity_function():
    """Not to `content`, which owns the neighbouring `/api/v1/admin` surface.

    A flow route pointed at another domain's function is a 404 the frontend
    reads as a broken login, and the integration name is the only thing in the
    map that decides it.
    """
    for key in IDENTITY_M2_ROUTE_KEYS:
        assert key in gateway_route_keys()["identity"], key


def test_the_m3_email_keys_are_present_unconditionally():
    """M3's four keys exist whether or not the sender is configured.

    The routes themselves are conditional inside the package: no
    `IDENTITY_EMAIL_FROM` means no `SesV2EmailSender`, which means
    `build_identity_router` declines to mount them. The keys are not, and the
    asymmetry is deliberate. A key whose path the function does not serve is a
    404 from a function that answered; a path with no key is API Gateway's own
    404 with `default_integration = null`, and no request ever reaches the
    function. Keys that appear and disappear with a deployment profile are also
    keys `test_route_keys_and_served_paths_agree` cannot check.
    """
    assert IDENTITY_M3_ROUTE_KEYS <= gateway_route_keys()["identity"]


def test_the_m3_keys_are_literal_and_do_not_end_in_a_slash():
    """No `{proxy+}` and no trailing slash, exactly as M1's and M2's are checked.

    The trailing slash matters more here than anywhere else in the identity set,
    because two of the four are nested one segment deeper than their siblings.
    `POST /api/auth/reset/confirm` is a sibling path of `POST /api/auth/reset`
    rather than a child route of it, and writing the parent as
    `POST /api/auth/reset/` to distinguish them is the exact mistake that
    applies green and fails with a BadRequestException saying part of the given
    route key path is empty.
    """
    for key in IDENTITY_M3_ROUTE_KEYS:
        path = key.split(" ", 1)[1]
        assert "{" not in key, key
        assert not path.endswith("/"), key


def test_every_m3_key_is_a_post():
    """All four are POSTs, including the two confirmations.

    The confirm routes take the mailed token in a body rather than in a query
    string, so the token stays out of access logs, out of `Referer` headers and
    out of browser history. A GET here would be a link that leaks the credential
    it carries to every intermediary that logs a URL.
    """
    for key in IDENTITY_M3_ROUTE_KEYS:
        assert key.startswith("POST "), key


def test_no_m3_email_route_is_anonymous():
    """The staging access gate stays exactly two documents wide, again.

    Worth stating separately from M2's version because the argument for making
    these anonymous is more tempting: a password reset is by definition
    something a signed out person does. It is still wrong. The staging access
    gate is not authentication, it is the fence around a non production
    environment, and a reset flow inside it is reached by someone who already
    got through the fence.
    """
    anonymous = set(ANONYMOUS_ROUTE_ENTRY.findall(_terraform_source()))

    assert IDENTITY_M3_ROUTE_KEYS & anonymous == set(), sorted(
        IDENTITY_M3_ROUTE_KEYS & anonymous
    )


def test_the_m3_keys_route_to_the_identity_function():
    """Not to `content`, and not to `public` because they are signed out flows.

    `public` serves the routes that need no identity at all. These need the
    identity function specifically: they read and write the identity-tokens
    table, they call SES with the identity role's grant, and only that function
    has either.
    """
    for key in IDENTITY_M3_ROUTE_KEYS:
        assert key in gateway_route_keys()["identity"], key


def test_the_reset_pair_does_not_collide_with_the_verify_pair():
    """Four distinct keys, two prefixes, no key that is a prefix of another.

    API Gateway routes a literal key by exact match, so `POST /api/auth/reset`
    and `POST /api/auth/reset/confirm` coexist without either shadowing the
    other. This pins that they really are four separate keys rather than three
    plus a typo, which is the shape a copied line produces.
    """
    assert len(IDENTITY_M3_ROUTE_KEYS) == 4
    assert len(IDENTITY_M2_ROUTE_KEYS & IDENTITY_M3_ROUTE_KEYS) == 0


def test_the_well_known_pair_is_anonymous_and_the_health_route_is_gated():
    """M1's hole in the staging access gate, held to exactly two documents.

    The two `.well-known` routes must be `NONE`: API Gateway fetches them from
    its own infrastructure with no gate cookie when M2 creates the JWT
    authorizer, so gating them fails verification closed and the authorizer
    cannot be created at all.

    `GET /api/auth/health` must not be `NONE`. Nothing outside the gate
    needs it, and the anonymous surface should be as small as the thing that
    forces it to exist, which is the discovery pair and nothing else.
    """
    anonymous = set(ANONYMOUS_ROUTE_ENTRY.findall(_terraform_source()))
    assert IDENTITY_M1_ANONYMOUS_KEYS <= anonymous, sorted(anonymous)
    assert "GET /api/auth/health" not in anonymous


def test_the_mint_route_is_behind_the_gate():
    """The spike's entire safety story, in one assertion.

    `POST /api/identity/spike/token` signs a token for whatever subject the
    caller names and authenticates nobody. `spike.py` says in as many words that
    a route like that is acceptable here only because the staging access gate
    stands in front of it, so the gate is not a detail of this route, it is the
    reason the route is allowed to exist. It is gated by setting no
    `authorization_type` at all and taking the module's CUSTOM default, so the
    way this can regress is by somebody adding `authorization_type = "NONE"` to
    it the way M1's two `.well-known` entries have, which would leave an
    unauthenticated token mint open to the internet.
    """
    if not spike_route_keys():
        pytest.skip("the M0 spike has been removed")

    anonymous = set(ANONYMOUS_ROUTE_ENTRY.findall(_terraform_source()))
    assert "POST /api/identity/spike/token" not in anonymous


def test_the_anonymous_surface_is_exactly_the_two_discovery_documents():
    """The whole gate hole, across every file, in one place.

    The two tests above each check one side. This one checks the total: whatever
    else is added to any routes map, the set of keys that opt out of the staging
    access gate stays the two documents API Gateway has to be able to read
    anonymously, and nothing else ever joins them without this failing.
    """
    anonymous = set(ANONYMOUS_ROUTE_ENTRY.findall(_terraform_source()))
    assert anonymous == IDENTITY_M1_ANONYMOUS_KEYS, sorted(anonymous)


def test_the_spike_splits_its_keys_across_the_two_files_for_ordering():
    """Which file each spike key lives in, which is the ordering fix itself.

    API Gateway validates a JWT authorizer's issuer at CreateAuthorizer time by
    fetching `<issuer>/.well-known/openid-configuration`, and refuses the call
    with a BadRequestException when that is not a discovery document. The first
    apply of the spike proved it. So the two `.well-known` routes have to exist
    before the authorizer, and `whoami`, which names the authorizer, after it.

    A single routes map cannot express that. Every route in it is one
    `for_each`, so a `whoami` entry referencing the authorizer's id makes the
    whole set wait on the authorizer, and the authorizer waits on a document
    only that set can serve. Moving `whoami` out is what breaks the knot, and
    this test is what keeps somebody from tidying it back in.

    The mint route stays in the map, and this test pins that too. It names no
    authorizer, so it imposes no ordering, and moving it out beside `whoami`
    would mean writing its gate authorization out by hand instead of letting the
    module resolve it, which is how a route ends up unintentionally public.
    """
    if not spike_route_keys():
        pytest.skip("the M0 spike has been removed")

    assert gateway_route_keys()["identity"] & IDENTITY_SPIKE_ROUTE_KEYS == (
        IDENTITY_SPIKE_ROUTES_MAP_KEYS
    )
    assert standalone_route_keys() == {"GET /api/identity/spike/whoami"}


def test_the_spike_authorizer_waits_for_the_routes_and_the_function():
    """The `depends_on` that orders the authorizer after what it fetches.

    Nothing the authorizer resource references implies either dependency:
    `module.api.api_id` is the API, created long before any route on it, and the
    authorizer reads nothing at all from `module.lambda_domain`. Without the
    explicit list Terraform is free to create the authorizer first, which is
    exactly what the first apply did.

    The wait resource is the third entry because `depends_on` orders API calls
    and not their effects; see its comment in `identity_spike.tf`.
    """
    source = IDENTITY_SPIKE_TF.read_text(encoding="utf-8")
    if not spike_route_keys():
        pytest.skip("the M0 spike has been removed")

    authorizer = source.split('resource "aws_apigatewayv2_authorizer"', 1)[1]
    depends = authorizer.split("depends_on", 1)[1].split("]", 1)[0]

    for required in (
        "module.api",
        "module.lambda_domain",
        "terraform_data.identity_spike_discovery_ready",
    ):
        assert required in depends, required


def test_identity_has_two_route_keys_for_its_single_prefix():
    """The prefix is `/api/v1/admin`, and it takes the same two keys as cut 3.

    Not three: a trailing-slash key is not a legal route key, as cut 2's apply
    proved. Not one: the bare key is kept even though nothing is served at the
    prefix root, for the reason spelled out in `apigateway.tf` and pinned by
    `test_the_bare_admin_key_is_deliberate_and_matches_nothing_served` below.
    """
    assert identity_route_keys() == {
        "ANY /api/v1/admin",
        "ANY /api/v1/admin/{proxy+}",
    }


def test_identity_serves_exactly_one_route_and_it_is_the_login_post():
    """The premise the two keys are sized against.

    `identity` is the smallest domain: `backend/app/domains/identity/router.py`
    declares a bare `POST /login` and the descriptor in
    `app/composition/wiring.py` mounts it under `/api/v1/admin`. If a second
    route is ever added, this fails and whoever added it has to confirm the
    greedy key still covers it, which it will for anything below the prefix.
    """
    assert domain_paths("identity") == {"/api/v1/admin/login"}


def test_every_identity_route_the_app_serves_has_a_gateway_route_key():
    """The cut is complete: no identity path falls through to `$default`.

    Unlike `content`, this one asserts an empty leftover set with no exception
    carved out for a collection root. `identity` declares no route at its prefix
    root, so there is no trailing-slash path to leave open, and the single
    served path sits one segment below the prefix where the greedy key matches
    it under every reading of route selection.
    """
    keys = identity_route_keys()
    unrouted = sorted(
        path
        for path in domain_paths("identity")
        if not any(matches(k, path) for k in keys)
    )
    assert unrouted == []


def test_the_greedy_admin_key_is_what_carries_the_login_route():
    """Which of the two keys does the work, stated rather than implied.

    `/api/v1/admin/login` has a non-empty remainder below the prefix, so the
    greedy key matches it without depending on the empty-remainder question that
    cuts 2 and 3 had to leave to the apply. This cut rests on no undocumented
    gateway behaviour, and this test is what says so.
    """
    assert matches("ANY /api/v1/admin/{proxy+}", "/api/v1/admin/login")
    assert not matches("ANY /api/v1/admin", "/api/v1/admin/login")


def test_the_bare_admin_key_is_deliberate_and_matches_nothing_served():
    """The one identity key that points at no served path, kept on purpose.

    This is cut 4's counterpart to `content`'s unmatched `site-content` greedy
    key, and it is why there is no `test_no_identity_route_key_points_at_a_path_
    the_app_does_not_serve` in the shape cuts 2 and 3 have: for `identity` the
    bare key is *expected* to match nothing. `/api/v1/admin` and
    `/api/v1/admin/` are 404s from the identity function, and the key exists so
    that they are the identity function's 404 rather than a fall-through to the
    monolith, and so that a future route at the prefix root is not left behind.
    """
    paths = domain_paths("identity")
    assert not any(matches("ANY /api/v1/admin", path) for path in paths)
    assert "/api/v1/admin" not in paths
    assert "/api/v1/admin/" not in paths


def test_no_identity_route_key_reaches_outside_the_admin_prefix():
    """The other direction, in the form that is meaningful for this domain.

    A key that claimed more than `/api/v1/admin` would take paths off the
    monolith that `identity` cannot serve, and unlike a merely unmatched key
    that is an outage rather than a 404. Both keys must stay under the prefix.
    """
    for key in identity_route_keys():
        key_path = key.split(" ", 1)[1]
        assert key_path == "/api/v1/admin" or key_path.startswith("/api/v1/admin/"), key


def test_the_identity_keys_use_any_rather_than_post():
    """ANY, so a wrong method answers 405 from `identity`, not from the monolith.

    The only served route is a POST, so a `POST` key would cover today's traffic
    exactly. ANY is still correct: the domain owns every method on this prefix,
    and the monolith serves its own copy of the same login endpoint, so a GET
    routed to `$default` would succeed in a way that makes the cut look complete
    when it is not. It is also what makes the verify script's GET probes
    meaningful, since they read the domain header off the 405.
    """
    for key in identity_route_keys():
        assert key.startswith("ANY "), key
