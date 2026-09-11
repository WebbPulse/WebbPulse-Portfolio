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

Every one of them is in `terraform/apigateway.tf`.
"""

import re
from pathlib import Path

import pytest
from starlette.routing import Route

from app.composition.wiring import build_domain_app

REPO = Path(__file__).resolve().parents[3]
APIGATEWAY_TF = REPO / "terraform" / "apigateway.tf"

DOCUMENTATION_PATHS = {"/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"}

ROUTE_ENTRY = re.compile(
    r'"(?P<key>(?:ANY|GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS) /[^"]*)"\s*='
    r'\s*\{\s*integration\s*=\s*"(?P<integration>[^"]+)"'
)

ANONYMOUS_ROUTE_ENTRY = re.compile(
    r'"((?:ANY|GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS) /[^"]*)"\s*='
    r'\s*\{\s*integration\s*=\s*"[^"]+"\s*'
    r'authorization_type\s*=\s*"NONE"'
)

COLLECTION_LIST = re.compile(
    r"^\s*(?P<name>\w+)\s*=\s*\[(?P<body>[^\]]*)\]", re.MULTILINE
)

IDENTITY_JWT_ROUTE_ENTRY = re.compile(
    r'"((?:ANY|GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS) /[^"]*)"\s*='
    r'\s*\{\s*integration\s*=\s*"[^"]+"\s*'
    r"require_identity_jwt\s*=\s*true"
)


def identity_jwt_route_keys_in_terraform() -> set[str]:
    """Every route key in `apigateway.tf` that sets `require_identity_jwt = true`.

    The Terraform-side counterpart of the module's `identity_jwt_route_keys`
    output. Parsed rather than planned, for the reason the module docstring
    gives: the keys are static text and a regex over them compares two sets of
    strings without needing credentials or a workspace.
    """
    return set(IDENTITY_JWT_ROUTE_ENTRY.findall(_terraform_source()))


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

        (name,) = set(interpolations)
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

    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]

    if key_path.endswith("/{proxy+}"):
        prefix = key_path[: -len("{proxy+}")]
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


IDENTITY_M1_ROUTE_KEYS = {
    "GET /api/auth/.well-known/jwks.json",
    "GET /api/auth/.well-known/openid-configuration",
    "GET /api/auth/health",
}

IDENTITY_M1_ANONYMOUS_KEYS = {
    "GET /api/auth/.well-known/jwks.json",
    "GET /api/auth/.well-known/openid-configuration",
}

IDENTITY_M2_ROUTE_KEYS = {
    "POST /api/auth/register",
    "POST /api/auth/login",
    "POST /api/auth/password",
    "POST /api/auth/refresh",
    "POST /api/auth/logout",
    "POST /api/auth/logout-all",
}

IDENTITY_M3_ROUTE_KEYS = {
    "POST /api/auth/verify-email",
    "POST /api/auth/verify-email/confirm",
    "POST /api/auth/reset",
    "POST /api/auth/reset/confirm",
}

IDENTITY_M4_ROUTE_KEYS = {
    "POST /api/auth/login/totp",
    "POST /api/auth/totp/enrol",
    "POST /api/auth/totp/activate",
    "POST /api/auth/totp/disable",
    "POST /api/auth/recovery-codes",
    "POST /api/auth/step-up",
}

IDENTITY_M5_ROUTE_KEYS = {
    "GET /api/auth/passkeys/availability",
    "POST /api/auth/passkeys/register/options",
    "POST /api/auth/passkeys/register/verify",
    "POST /api/auth/login/passkey/options",
    "POST /api/auth/login/passkey/verify",
    "GET /api/auth/passkeys",
    "PATCH /api/auth/passkeys/{credential_id}",
    "DELETE /api/auth/passkeys/{credential_id}",
}

IDENTITY_M5_JWT_ROUTE_KEYS = {
    "POST /api/auth/passkeys/register/options",
    "POST /api/auth/passkeys/register/verify",
    "GET /api/auth/passkeys",
    "PATCH /api/auth/passkeys/{credential_id}",
    "DELETE /api/auth/passkeys/{credential_id}",
}

IDENTITY_M6_ROUTE_KEYS = {
    "GET /api/auth/oauth/providers",
    "GET /api/auth/oauth/{provider}/start",
    "GET /api/auth/oauth/callback",
    "POST /api/auth/oauth/{provider}/link",
    "GET /api/auth/oauth/links",
    "DELETE /api/auth/oauth/{provider}/link",
}

IDENTITY_M6_JWT_ROUTE_KEYS = {
    "POST /api/auth/oauth/{provider}/link",
    "GET /api/auth/oauth/links",
    "DELETE /api/auth/oauth/{provider}/link",
}


def identity_route_keys() -> set[str]:
    """Cut 4's keys, which are literal rather than generated.

    Cuts 2 and 3 loop over a local, so their keys have to be expanded with
    `expand_for_expression_keys`. Cut 4 covers one prefix and writes both keys
    out, so `gateway_route_keys` reads them straight from the file.

    M1's permanent identity keys, M2's six flow keys, M3's four email keys,
    M4's six MFA keys, M5's seven passkey keys and M6's six OAuth keys are all
    subtracted. See `IDENTITY_M1_ROUTE_KEYS` and its five siblings.

    Every milestone needing its own subtraction here is the weakness that let
    M5 and M6 ship with no route keys at all: this helper only knows about the
    milestones somebody remembered to add, so a milestone nobody added was
    checked in neither direction.
    `test_every_identity_path_the_package_mounts_has_a_gateway_route_key` is
    the assertion that does not have that shape, and it is what makes the next
    milestone's omission a failing test rather than a staging 404.
    """
    keys = (
        gateway_route_keys()["identity"]
        - IDENTITY_M1_ROUTE_KEYS
        - IDENTITY_M2_ROUTE_KEYS
        - IDENTITY_M3_ROUTE_KEYS
        - IDENTITY_M4_ROUTE_KEYS
        - IDENTITY_M5_ROUTE_KEYS
        - IDENTITY_M6_ROUTE_KEYS
    )
    assert keys, "no identity route keys were parsed out of apigateway.tf"
    return keys


def test_the_m1_keys_are_present_unconditionally():
    """M1's three keys exist in every environment.

    This is what `IDENTITY_M1_ROUTE_KEYS` exists to hold. M1 does not gate the
    `.well-known` pair behind anything, because M2's `CreateAuthorizer` fetches
    the discovery document during the apply that creates the authorizer, and a
    document that only exists when a flag is on is one M2 cannot rely on.
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
    """M2's six flow routes exist in every environment.

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


def test_the_m4_mfa_keys_are_present_unconditionally():
    """M4's six keys exist whether or not anybody has enrolled a factor.

    The routes themselves are conditional inside the package, on `totp_enabled`
    and on all three of the factor store, the recovery code store and the
    identity-tokens store. `composition/identity.py` supplies all three with no
    switch in front of them, so the routes mount in every environment, and the
    keys are unconditional for the reason M3's are: a path with no key is a
    gateway 404 that reaches no function, which is the worse of the two
    failures.
    """
    assert IDENTITY_M4_ROUTE_KEYS <= gateway_route_keys()["identity"]


def test_the_m4_keys_are_literal_and_do_not_end_in_a_slash():
    """No `{proxy+}` and no trailing slash, exactly as M1, M2 and M3 are checked.

    `POST /api/auth/login/totp` is the key this matters most for. It is a
    sibling of `POST /api/auth/login` rather than a child of it, and writing the
    parent as `POST /api/auth/login/` to tell them apart is the mistake that
    plans green and fails at apply with a BadRequestException saying part of the
    given route key path is empty.
    """
    for key in IDENTITY_M4_ROUTE_KEYS:
        path = key.split(" ", 1)[1]
        assert "{" not in key, key
        assert not path.endswith("/"), key


def test_every_m4_key_is_a_post():
    """All six are POSTs, including `step-up` and `recovery-codes`.

    Every one of them changes state: minting a seed, activating a factor,
    spending a code, or issuing a stepped up token. A GET on any of them would
    be a state change a browser is free to prefetch.
    """
    for key in IDENTITY_M4_ROUTE_KEYS:
        assert key.startswith("POST "), key


def test_no_m4_mfa_route_is_anonymous():
    """The staging access gate stays exactly two documents wide, a third time.

    `POST /api/auth/login/totp` is where the temptation to write
    `authorization_type = "NONE"` is strongest, because the route genuinely is
    outside the identity JWT authorizer: its caller holds an MFA ticket rather
    than an access token, and the ticket's audience is `<issuer>/mfa`.

    Those are two different controls answering two different questions, and
    conflating them is what this test exists to catch. Being outside the JWT
    authorizer is a fact about the identity standard; being inside the staging
    access gate is a fact about staging being a non production environment. The
    gate is not authentication, and somebody completing a login inside it is
    somebody who already got through the fence.
    """
    anonymous = set(ANONYMOUS_ROUTE_ENTRY.findall(_terraform_source()))

    assert IDENTITY_M4_ROUTE_KEYS & anonymous == set(), sorted(
        IDENTITY_M4_ROUTE_KEYS & anonymous
    )


def test_the_m4_keys_route_to_the_identity_function():
    """Not to `public`, and not to `content`.

    All six read or write the two M4 tables and five of them call KMS to seal or
    open a seed. Only the identity function has the table grants and the
    envelope key grant, both attached to its role by `module.identity`.
    """
    for key in IDENTITY_M4_ROUTE_KEYS:
        assert key in gateway_route_keys()["identity"], key


def test_the_totp_login_key_does_not_collide_with_the_login_key():
    """`login` and `login/totp` are two distinct literal keys, not one plus a typo.

    API Gateway matches a literal key by exact match, so a key that is a string
    prefix of another shadows nothing. This pins that both really are in the map
    and that the six M4 keys are disjoint from every earlier milestone's.
    """
    assert "POST /api/auth/login" in gateway_route_keys()["identity"]
    assert "POST /api/auth/login/totp" in gateway_route_keys()["identity"]
    assert len(IDENTITY_M4_ROUTE_KEYS) == 6
    assert IDENTITY_M4_ROUTE_KEYS & IDENTITY_M2_ROUTE_KEYS == set()
    assert IDENTITY_M4_ROUTE_KEYS & IDENTITY_M3_ROUTE_KEYS == set()
    assert IDENTITY_M4_ROUTE_KEYS & IDENTITY_M1_ROUTE_KEYS == set()


def test_the_m4_keys_match_the_paths_the_package_declares():
    """The six keys are the package's own suffixes under the issuer's path.

    Read from `webbpulse.identity.router` rather than retyped, so a suffix the
    package renames is a failing test here rather than a gateway 404 in staging.
    The prefix is `/api/auth`, which is the issuer's path, and
    `build_identity_router` mounts every route it declares under it.
    """
    from webbpulse.identity.router import (
        LOGIN_TOTP_PATH,
        RECOVERY_CODES_PATH,
        STEP_UP_PATH,
        TOTP_ACTIVATE_PATH,
        TOTP_DISABLE_PATH,
        TOTP_ENROL_PATH,
    )

    expected = {
        f"POST /api/auth{suffix}"
        for suffix in (
            LOGIN_TOTP_PATH,
            TOTP_ENROL_PATH,
            TOTP_ACTIVATE_PATH,
            TOTP_DISABLE_PATH,
            RECOVERY_CODES_PATH,
            STEP_UP_PATH,
        )
    }

    assert IDENTITY_M4_ROUTE_KEYS == expected


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


def test_the_anonymous_surface_is_exactly_the_two_discovery_documents():
    """The whole gate hole, across every file, in one place.

    The two tests above each check one side. This one checks the total: whatever
    else is added to any routes map, the set of keys that opt out of the staging
    access gate stays the two documents API Gateway has to be able to read
    anonymously, and nothing else ever joins them without this failing.
    """
    anonymous = set(ANONYMOUS_ROUTE_ENTRY.findall(_terraform_source()))
    assert anonymous == IDENTITY_M1_ANONYMOUS_KEYS, sorted(anonymous)


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


IDENTITY_FULL_ENV = {
    "IDENTITY_ISSUER": "https://api.example.test/api/auth",
    "IDENTITY_AUDIENCE": "https://api.example.test",
    "IDENTITY_SIGNING_KEY_ARNS": '["arn:aws:kms:us-west-2:111122223333:key/t"]',
    "IDENTITY_EMAIL_FROM": "identity@example.test",
    "IDENTITY_PASSKEYS_ENABLED": "true",
    "IDENTITY_PASSKEYS_PASSWORDLESS": "true",
    "IDENTITY_GOOGLE_CLIENT_ID": "google-client-id",
    "IDENTITY_GITHUB_CLIENT_ID": "github-client-id",
    "AWS_DEFAULT_REGION": "us-west-2",
}


def identity_package_routes(monkeypatch) -> set[tuple[str, str]]:
    """Every `(method, path)` the identity application mounts under `/api/auth`.

    Read off the built application rather than from a list in this file, which
    is the whole point: a route the package adds appears here the moment the
    package is upgraded, with nobody having to notice.

    `HEAD` is dropped because Starlette adds it to every `GET` automatically and
    API Gateway does not need a key for it.

    The settings cache has to be dropped around this, and that is not
    incidental. `get_settings` is `lru_cache`d and `app.composition.settings`
    builds a module-level `Settings` at import, so environment variables set
    after the first import are invisible: `build_domain_app` would read
    `IDENTITY_ISSUER` as empty, skip the identity router entirely, and this
    helper would return an empty set. An empty set makes the exhaustiveness
    assertion below vacuously true, which is the one way this test could fail to
    do the only job it has. `reset_settings_cache` exists for exactly this, and
    the fresh `Settings()` is passed explicitly so the app is built from the
    environment set above rather than from whatever another test cached.

    The assertion that the set is non-empty is therefore load-bearing rather
    than defensive.
    """
    from app.composition.settings import Settings, reset_settings_cache

    for name, value in IDENTITY_FULL_ENV.items():
        monkeypatch.setenv(name, value)

    reset_settings_cache()
    identity_settings = Settings()

    app = build_domain_app("identity", settings=identity_settings)
    return {
        (method, route.path)
        for route in app.routes
        if isinstance(route, Route)
        and route.methods
        and route.path.startswith("/api/auth")
        for method in route.methods
        if method != "HEAD"
    }


def test_every_identity_path_the_package_mounts_has_a_gateway_route_key(monkeypatch):
    """The assertion whose absence let M5 and M6 ship unreachable.

    This is the identity counterpart of
    `test_every_resume_route_the_app_serves_has_a_gateway_route_key`, and the
    reason it did not exist before is that every other identity assertion in
    this file is written per milestone: a set of expected keys is typed out, and
    a milestone nobody typed out is checked in neither direction. M5's seven
    passkey routes and M6's six OAuth routes were mounted by the identity
    function and declared nowhere in `apigateway.tf`, so with
    `default_integration = null` every one of them was API Gateway's own 404.
    `GET /api/auth/oauth/providers` answering `{"message":"Not Found"}` on
    staging is what that looked like from outside.

    Written against the built application and not against a list, so M7 needs no
    new constant here to be covered. It is method-aware, which the milestone
    sets are not: a package that added a `GET` beside an existing `POST` on the
    same path would pass every other test in this file and still 404, because a
    route key is a method and a path together.
    """
    keys = gateway_route_keys()["identity"]
    package_routes = identity_package_routes(monkeypatch)

    assert len(package_routes) >= 30, sorted(package_routes)

    unrouted = sorted(
        f"{method} {path}"
        for method, path in package_routes
        if not any(
            key.split(" ", 1)[0] in (method, "ANY") and matches(key, path)
            for key in keys
        )
    )
    assert unrouted == [], (
        "these identity paths are mounted by the application and have no "
        f"gateway route key, so they are a 404 from API Gateway: {unrouted}"
    )


def test_the_m5_keys_are_present_and_match_the_paths_the_package_declares():
    """M5's eight keys exist, and their suffixes are the package's own.

    Read from `webbpulse.identity.passkey_routes` rather than retyped, exactly
    as the M4 test reads `webbpulse.identity.router`, so a path the package
    renames fails here rather than 404ing in staging.
    """
    from webbpulse.identity.passkey_routes import (
        LOGIN_PASSKEY_OPTIONS_PATH,
        LOGIN_PASSKEY_VERIFY_PATH,
        PASSKEY_AVAILABILITY_PATH,
        PASSKEY_ITEM_PATH,
        PASSKEY_REGISTER_OPTIONS_PATH,
        PASSKEY_REGISTER_VERIFY_PATH,
        PASSKEYS_PATH,
    )

    expected = {
        f"GET /api/auth{PASSKEY_AVAILABILITY_PATH}",
        f"POST /api/auth{PASSKEY_REGISTER_OPTIONS_PATH}",
        f"POST /api/auth{PASSKEY_REGISTER_VERIFY_PATH}",
        f"POST /api/auth{LOGIN_PASSKEY_OPTIONS_PATH}",
        f"POST /api/auth{LOGIN_PASSKEY_VERIFY_PATH}",
        f"GET /api/auth{PASSKEYS_PATH}",
        f"PATCH /api/auth{PASSKEY_ITEM_PATH}",
        f"DELETE /api/auth{PASSKEY_ITEM_PATH}",
    }

    assert IDENTITY_M5_ROUTE_KEYS == expected
    assert IDENTITY_M5_ROUTE_KEYS <= gateway_route_keys()["identity"]


def test_the_m6_keys_are_present_and_match_the_paths_the_package_declares():
    """M6's six keys exist, and their suffixes are the package's own."""
    from webbpulse.identity.oauth_routes import (
        OAUTH_CALLBACK_PATH,
        OAUTH_LINK_PATH,
        OAUTH_LINKS_PATH,
        OAUTH_PROVIDERS_PATH,
        OAUTH_START_PATH,
    )

    expected = {
        f"GET /api/auth{OAUTH_PROVIDERS_PATH}",
        f"GET /api/auth{OAUTH_START_PATH}",
        f"GET /api/auth{OAUTH_CALLBACK_PATH}",
        f"POST /api/auth{OAUTH_LINK_PATH}",
        f"GET /api/auth{OAUTH_LINKS_PATH}",
        f"DELETE /api/auth{OAUTH_LINK_PATH}",
    }

    assert IDENTITY_M6_ROUTE_KEYS == expected
    assert IDENTITY_M6_ROUTE_KEYS <= gateway_route_keys()["identity"]


def test_the_m5_and_m6_keys_do_not_end_in_a_slash_and_use_no_greedy_segment():
    """No `{proxy+}`, no trailing slash, on the same rule every milestone follows.

    A variable segment is allowed here and is new to this file: `{provider}` and
    `{credential_id}` are single-segment path parameters, which is a supported
    route key shape and is not the greedy `{proxy+}` the rest of this file
    avoids. The distinction is the point — `{credential_id}` matches exactly one
    segment, so it cannot route a path nobody declared, while `{proxy+}` would
    hand the identity function everything below `/api/auth/passkeys/`.
    """
    for key in IDENTITY_M5_ROUTE_KEYS | IDENTITY_M6_ROUTE_KEYS:
        path = key.split(" ", 1)[1]
        assert "{proxy+}" not in key, key
        assert not path.endswith("/"), key
        for segment in path.split("/"):
            assert "{" not in segment or segment.endswith("}"), key


def test_no_m5_or_m6_route_is_anonymous():
    """The staging access gate still stays exactly two documents wide.

    Thirteen new keys, none of them `authorization_type = "NONE"`, including
    `GET /api/auth/oauth/providers`, which is the one that most looks like it
    wants to be. It is anonymous to the *application*, because a sign-in page
    holds no token, and that is a different question from whether it sits behind
    the staging environment's fence. Somebody loading a sign-in page in staging
    is somebody who already got through the fence, exactly as with
    `POST /api/auth/login`.
    """
    anonymous = set(ANONYMOUS_ROUTE_ENTRY.findall(_terraform_source()))

    overlap = (IDENTITY_M5_ROUTE_KEYS | IDENTITY_M6_ROUTE_KEYS) & anonymous
    assert overlap == set(), sorted(overlap)


def test_the_anonymous_login_legs_are_not_behind_the_identity_jwt_authorizer():
    """The four routes a caller reaches with no token of ours, stated as a set.

    Two passkey login legs and two OAuth browser legs, plus the provider list.
    Flagging any of them would refuse the request for having nothing to present,
    which is a different failure from `POST /api/auth/login/totp`'s — that one
    carries a ticket whose `aud` a check on the API audience actively rejects.
    Same conclusion, different mechanism, and both are worth pinning because the
    next person to read the flags will reasonably wonder why a `/login/` route
    is unflagged.
    """
    flagged = identity_jwt_route_keys_in_terraform()

    must_stay_open = {
        "POST /api/auth/login/passkey/options",
        "POST /api/auth/login/passkey/verify",
        "GET /api/auth/oauth/providers",
        "GET /api/auth/oauth/{provider}/start",
        "GET /api/auth/oauth/callback",
        "POST /api/auth/login/totp",
    }

    assert must_stay_open & flagged == set(), sorted(must_stay_open & flagged)


def test_the_account_management_routes_require_an_identity_token():
    """The other half of the split: every route that reads a verified subject.

    Each of these calls `require_subject` in the package and answers 401
    NOT_AUTHENTICATED without a verified subject, so the flag makes the gateway
    refuse one hop earlier what the application already refused. The application
    check stays where it is; this is defence in depth, not a replacement.
    """
    flagged = identity_jwt_route_keys_in_terraform()
    expected = IDENTITY_M5_JWT_ROUTE_KEYS | IDENTITY_M6_JWT_ROUTE_KEYS

    missing = sorted(expected - flagged)
    assert missing == [], (
        f"these routes read a verified subject but are not flagged: {missing}"
    )


DOMAIN_LIST = re.compile(r"(?P<name>\w+)\s*=\s*\[(?P<body>[^\]]*)\]", re.DOTALL)

CALLER_DEPENDENCIES = {"CurrentUser", "get_current_user", "require_admin"}

PROTECTED_DOMAINS = ("content", "resume")


def _block(source: str, opening: str) -> str:
    """The brace-balanced block that `opening` starts, `opening` included.

    A regex cannot match nested braces, and the domain map has a level of them
    per domain. This walks the braces instead, which is enough structure for a
    file this shape without taking a dependency on an HCL parser.
    """
    start = source.index(opening)
    depth = 0
    for offset in range(start, len(source)):
        if source[offset] == "{":
            depth += 1
        elif source[offset] == "}":
            depth -= 1
            if depth == 0:
                return source[start : offset + 1]
    raise AssertionError(f"unbalanced braces after {opening!r}")


def domain_identity_jwt_route_paths() -> dict[str, set[str]]:
    """`local.domain_identity_jwt_route_paths`, per domain, as plain sets.

    The declared list rather than the generated map. Comments are stripped
    first, because the block carries the shadowing analysis in prose and a route
    key quoted inside a comment is not a route key.
    """
    source = _strip_comments(_terraform_source())
    block = _block(source, "domain_identity_jwt_route_paths = {")

    paths = {
        match.group("name"): set(re.findall(r'"([^"]+)"', match.group("body")))
        for match in DOMAIN_LIST.finditer(block)
    }
    assert paths, "local.domain_identity_jwt_route_paths is empty or was renamed"
    return paths


def flagged_domain_route_keys() -> set[str]:
    """Every `/api/v1` route key the domain map flags, across all domains."""
    return set().union(*domain_identity_jwt_route_paths().values())


def _dependency_names(dependant) -> set[str]:
    """Every dependency callable's name in this route's tree, however deep.

    `Depends(CurrentUser)` is one level, but `require_admin` depends on
    `CurrentUser` in turn and a router can carry a dependency for every route
    under it. Walking the whole tree is what makes the derivation a fact about
    what the route requires rather than about how it happens to be spelled.
    """
    names = set()
    stack = list(dependant.dependencies)
    while stack:
        sub = stack.pop()
        if sub.call is not None:
            names.add(getattr(sub.call, "__name__", ""))
        stack.extend(sub.dependencies)
    return names


def _api_routes(app):
    """Every route the application serves, flattened, across two FastAPI shapes.

    `include_router` used to copy each route onto `app.routes`, so an `APIRoute`
    isinstance check found all of them. Newer FastAPI keeps the inclusion lazy
    instead: `app.routes` holds a `_IncludedRouter` per `include_router` call and
    the real routes are behind its `effective_route_contexts()`, which yields an
    `_EffectiveRouteContext` carrying the same `path`, `methods` and `dependant`
    the route did.

    Both are handled because the pinned version in CI and the resolved version
    in a local checkout are not the same, and a derivation that silently found
    no routes would make every exhaustiveness test below pass vacuously. That is
    the failure mode worth spending a branch on: an empty derived set trivially
    satisfies "every protected route is flagged".
    """
    from fastapi.routing import APIRoute

    flat = [route for route in app.routes if isinstance(route, APIRoute)]

    try:
        from fastapi.routing import _IncludedRouter
    except ImportError:
        return flat

    for route in app.routes:
        if isinstance(route, _IncludedRouter):
            flat.extend(route.effective_route_contexts())
    return flat


def routes_requiring_a_caller(domain: str) -> set[str]:
    """The route keys this domain's application will not serve anonymously.

    Derived from the built application, not from a list here: this is the set
    `apigateway.tf` has to match, so writing it out by hand would be asserting
    the copy against itself.
    """
    keys = set()
    for route in _api_routes(build_domain_app(domain)):
        if route.path in DOCUMENTATION_PATHS or route.path == "/health":
            continue
        if not _dependency_names(route.dependant) & CALLER_DEPENDENCIES:
            continue
        for method in route.methods or set():
            if method in ("HEAD", "OPTIONS"):
                continue
            path = route.path
            if len(path) > 1 and path.endswith("/"):
                path = path[:-1]
            keys.add(f"{method} {path}")
    return keys


def test_the_route_derivation_finds_routes_at_all():
    """The guard on the guard.

    Every exhaustiveness test below compares against `routes_requiring_a_caller`,
    and an empty set would satisfy all of them while proving nothing. FastAPI
    changed how `include_router` stores routes, so this asserts the walk still
    finds them rather than trusting that it does.
    """
    for domain in PROTECTED_DOMAINS:
        served = _api_routes(build_domain_app(domain))
        assert len(served) > 5, f"{domain}: route walk found {len(served)} routes"
        assert routes_requiring_a_caller(domain), f"{domain}: no protected routes found"


def test_the_domain_map_lists_exactly_the_domains_it_should():
    """Only `content` and `resume` have protected `/api/v1` routes.

    A third domain appearing here would mean either `public` grew an admin route
    or `identity`'s login stopped being anonymous, and both deserve a failing
    test rather than a silent flag.
    """
    assert set(domain_identity_jwt_route_paths()) == set(PROTECTED_DOMAINS)


@pytest.mark.parametrize("domain", PROTECTED_DOMAINS)
def test_every_route_requiring_a_caller_is_flagged_in_terraform(domain):
    """Direction one: a protected route with no flag answers 401 in identity mode.

    This is the original bug. Without the flag the gateway puts no claims on the
    request, `get_current_user` finds neither a legacy token it can verify nor a
    subject to fall back to, and the admin panel's write fails for a caller who
    is in fact signed in.
    """
    required = routes_requiring_a_caller(domain)
    flagged = domain_identity_jwt_route_paths()[domain]

    missing = sorted(required - flagged)
    assert missing == [], (
        f"{domain} routes requiring CurrentUser but not flagged in "
        f"apigateway.tf: {missing}"
    )


@pytest.mark.parametrize("domain", PROTECTED_DOMAINS)
def test_every_flagged_key_is_a_route_that_requires_a_caller(domain):
    """Direction two: a flag on a public read breaks the anonymous site.

    Once the variable is true the gateway refuses a flagged key without a valid
    access token, before the application sees it. Flagging a route the
    application would happily serve to a visitor takes it off the public site,
    and no application test would notice.
    """
    required = routes_requiring_a_caller(domain)
    flagged = domain_identity_jwt_route_paths()[domain]

    extra = sorted(flagged - required)
    assert extra == [], (
        f"{domain} route keys flagged in apigateway.tf that the application "
        f"serves without requiring a caller: {extra}"
    )


def test_the_two_sets_are_equal_across_every_domain():
    """The same claim as the two above, stated once as the set equality.

    Kept alongside them rather than instead of them: the parametrized pair name
    the direction that broke, which is the thing a failure needs to say, and
    this one is the summary line that the whole surface agrees.
    """
    derived = set().union(
        *(routes_requiring_a_caller(domain) for domain in PROTECTED_DOMAINS)
    )
    assert derived == flagged_domain_route_keys()


def test_every_flagged_key_is_routed_to_the_domain_that_serves_it():
    """Each flagged key reaches the same function it would have without the flag.

    The keys are new route keys, not annotations on existing ones. Before this
    change `PUT /api/v1/site-content` was served through content's greedy
    `ANY /api/v1/site-content/{proxy+}`-style keys; the explicit key is more
    specific, so it wins route selection, and if it named the wrong integration
    the flag would also silently repoint the route at another domain.

    `matches` is the same reader the rest of this file uses for the question
    "could this key have carried this path", which is what makes "the existing
    routing agrees" a checkable claim rather than a reading of the diff.
    """
    declared = {
        domain: gateway_route_keys().get(domain, set())
        | expand_for_expression_keys(domain)
        for domain in ("content", "resume", "identity", "public")
    }

    for domain, keys in domain_identity_jwt_route_paths().items():
        for key in sorted(keys):
            method, path = key.split(" ", 1)

            covering = {
                other_domain
                for other_domain, other_keys in declared.items()
                for other_key in other_keys
                if "${" not in other_key
                and matches(other_key, path)
                and other_key.split(" ", 1)[0] in ("ANY", method)
            }

            assert covering == {domain}, (
                f"{key} is flagged on {domain} but the routes map serves that "
                f"path from {sorted(covering)}"
            )


def test_no_flagged_domain_key_ends_in_a_slash():
    """The apply-time failure a green plan does not catch.

    API Gateway rejects any route key whose path ends in a slash with
    "Part of the given route key path is empty". The collection routes these
    flags cover are served at a trailing slash, so the normalisation in
    `routes_requiring_a_caller` is the only reason they are spelled bare here.
    """
    trailing = sorted(key for key in flagged_domain_route_keys() if key.endswith("/"))
    assert trailing == []


def test_no_flagged_domain_key_uses_a_greedy_segment():
    """Each flag names one route, not a subtree.

    `ANY /api/v1/posts/{proxy+}` would flag the public post reads along with the
    admin writes, because a greedy key matches everything under it. The keys are
    per method and per path for that reason.
    """
    greedy = sorted(key for key in flagged_domain_route_keys() if "{proxy+}" in key)
    assert greedy == []


def test_no_flagged_domain_key_uses_any_as_its_method():
    """`ANY` would flag the GET alongside the write it was meant for.

    The admin collections are the case: `GET /api/v1/posts/admin` is flagged
    because it lists drafts, but `/api/v1/posts` is a public read one segment
    away, and a method-less key is how the two get confused.
    """
    method_less = sorted(
        key for key in flagged_domain_route_keys() if key.startswith("ANY ")
    )
    assert method_less == []


def test_the_domain_flag_is_gated_on_a_variable_rather_than_hardcoded():
    """The keys exist either way; only enforcement moves.

    This is what makes the cutover two steps instead of one. Applying the keys
    with the variable false is an adds-only plan that changes no behaviour,
    which can land while the frontend still sends the legacy session. Flipping
    the variable afterwards is the change that starts requiring a token, and it
    is a one line revert if it goes wrong.

    A literal `true` here would collapse the two into a single apply that
    refuses every admin write the moment it lands, because the frontend has not
    been redeployed yet.
    """
    block = _block(
        _strip_comments(_terraform_source()), "domain_identity_jwt_route_keys = merge("
    )

    assert "require_identity_jwt = var.domain_jwt_enforced" in block, (
        "the generated entries must take the flag from the variable"
    )
    assert "require_identity_jwt = true" not in block, (
        "hardcoding true would enforce on apply, before the frontend is ready"
    )


def test_the_domain_jwt_variable_defaults_to_off():
    """The default is what an apply with no variable set does.

    Production applies this PR with `domain_jwt_enforced` unset, and that apply
    has to be adds-only and behaviour-neutral. A default of true would make the
    first apply the cutover, with the frontend still in bearer mode.
    """
    variables = (REPO / "terraform" / "variables.tf").read_text(encoding="utf-8")
    block = _block(variables, 'variable "domain_jwt_enforced" {')

    assert re.search(r"^\s*type\s*=\s*bool\s*$", block, re.MULTILINE), block
    assert re.search(r"^\s*default\s*=\s*false\s*$", block, re.MULTILINE), block


def test_the_flagged_keys_reach_the_staging_gate():
    """Gate mode enforces from `module.api.identity_jwt_route_keys`.

    Staging runs `identity_jwt_mode = "gate"`, where every route carries the
    access gate's own Lambda authorizer, so the gate is told which keys also
    need a verified identity token. The plumbing predates this change; the point
    here is that the domain keys join the same list rather than needing their
    own, so flipping the variable is the single gate-side change.
    """
    gate = (REPO / "terraform" / "staging_access_gate.tf").read_text(encoding="utf-8")
    gate = _strip_comments(gate)

    assert "module.api.identity_jwt_route_keys" in gate
    assert re.search(r"identity_jwt_route_keys\s*=", gate)


def test_the_flagged_keys_are_the_admin_surface_and_not_the_public_reads():
    """A spot check in plain terms, against the site's own anonymous pages.

    The derivation above is exhaustive but abstract. These five are the reads
    the blog and portfolio pages make for a signed out visitor, and flagging any
    of them takes the public site down. Naming them is cheaper than reasoning
    about the dependency tree when this fails.
    """
    flagged = flagged_domain_route_keys()

    must_stay_open = {
        "GET /api/v1/posts",
        "GET /api/v1/posts/{slug}",
        "GET /api/v1/posts/categories",
        "GET /api/v1/projects",
        "GET /api/v1/site-content",
    }

    assert must_stay_open & flagged == set(), sorted(must_stay_open & flagged)
