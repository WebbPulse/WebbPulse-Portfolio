"""The gateway's route keys against the routes the applications actually serve."""

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
    """Every route key in `apigateway.tf` that sets `require_identity_jwt = true`."""
    return set(IDENTITY_JWT_ROUTE_ENTRY.findall(_terraform_source()))


def _terraform_source() -> str:
    """The apigateway.tf file as text."""
    return APIGATEWAY_TF.read_text(encoding="utf-8")


def _strip_comments(source: str) -> str:
    """The file with `#` comment lines removed, for checks about configuration."""
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
    """The resume collection names the route keys interpolate over."""
    collections = _locals_lists(_terraform_source())["resume_collections"]
    assert collections, "local.resume_collections is empty or was renamed"
    return collections


def content_prefixes() -> list[str]:
    """The content path prefixes the route keys interpolate over."""
    prefixes = _locals_lists(_terraform_source())["content_prefixes"]
    assert prefixes, "local.content_prefixes is empty or was renamed"
    return prefixes


def expand_for_expression_keys(integration: str) -> set[str]:
    """Route keys written inside a `for collection in local.<list>` expression."""
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
    """The application paths a domain serves, documentation and /health aside."""
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
    """Does an API Gateway route key match this request path?"""
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
    """The Terraform file this module parses is where it expects it."""
    assert APIGATEWAY_TF.is_file(), APIGATEWAY_TF


def test_public_route_keys_are_the_four_literal_paths():
    """The public integration is wired to exactly its four literal paths."""
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
    """API Gateway rejects a route key whose path ends in a slash."""
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
    """Every resume path is reachable through some resume route key."""
    keys = expand_for_expression_keys("resume")
    assert any(matches(key, path) for key in keys), path


def test_the_bare_collection_key_covers_the_trailing_slash_under_normalisation():
    """The modelled reading, pinned as a property of `matches`."""
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
    """The other direction: a key the resume function would 404."""
    paths = domain_paths("resume")
    bare_collections = {f"/api/v1/{c}" for c in resume_collections()}

    for key in expand_for_expression_keys("resume"):
        key_path = key.split(" ", 1)[1]
        if key_path in bare_collections or key_path.endswith("/{proxy+}"):
            continue
        assert any(matches(key, path) for path in paths), key


def test_routed_domains_and_route_keys_move_together():
    """`local.routed_lambda_domains` gates the integrations map."""
    routed = _locals_lists(_terraform_source())["routed_lambda_domains"]
    keyed = set(gateway_route_keys()) | {"resume", "content"}

    assert routed == ["public", "resume", "content", "identity"]
    for domain in routed:
        assert domain in keyed, domain
    assert "legacy" not in routed


def test_no_default_route():
    """`default_integration` is null: section 6's retirement of the monolith."""
    source = _terraform_source()

    assert re.search(r"^\s*default_integration\s*=\s*null\s*$", source, re.MULTILINE), (
        "default_integration must be null: the monolith is retired and there is "
        "no integration left to serve $default."
    )
    assert not re.search(r'^\s*default_integration\s*=\s*"', source, re.MULTILINE), (
        "default_integration names an integration, which re-creates $default."
    )


def test_no_legacy_integration():
    """The monolith's integration is gone from the integrations map."""
    source = _strip_comments(_terraform_source())

    assert "legacy" not in source, (
        "apigateway.tf still configures `legacy`, the retired monolith integration."
    )
    assert "lambda_api" not in source, (
        "apigateway.tf still references module.lambda_api, the retired monolith."
    )


def test_content_has_two_route_keys_per_mounted_prefix():
    """Two, not the three cut 2 used. The trailing-slash key cannot exist."""
    prefixes = content_prefixes()
    keys = expand_for_expression_keys("content")

    assert sorted(prefixes) == ["posts", "site-content"]
    for prefix in prefixes:
        assert f"ANY /api/v1/{prefix}" in keys
        assert f"ANY /api/v1/{prefix}/{{proxy+}}" in keys
        assert f"ANY /api/v1/{prefix}/" not in keys
    assert len(keys) == 2 * len(prefixes) == 4


def test_no_route_key_anywhere_in_the_file_ends_in_a_trailing_slash():
    """The rejection is a property of API Gateway, so it binds every domain."""
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
    """Every content path is reachable through some content route key."""
    keys = expand_for_expression_keys("content")
    assert any(matches(key, path) for key in keys), path


def test_the_greedy_posts_key_covers_the_whole_subtree_however_deep():
    """`{proxy+}` captures the remainder, not one segment."""
    key = "ANY /api/v1/posts/{proxy+}"
    assert matches(key, "/api/v1/posts/admin")
    assert matches(key, "/api/v1/posts/admin/1/publish")
    assert not matches(key, "/api/v1/posts")


def test_every_content_route_the_app_serves_has_a_gateway_route_key():
    """The cut is complete: no content path is left falling through to $default."""
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
    """The other direction: a key the content function would 404."""
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
    """Cut 4's keys, which are literal rather than generated."""
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
    """M1's three keys exist in every environment."""
    assert IDENTITY_M1_ROUTE_KEYS <= gateway_route_keys()["identity"]


def test_the_m1_keys_are_literal_and_do_not_end_in_a_slash():
    """No `{proxy+}` and no trailing slash on any permanent identity key."""
    for key in IDENTITY_M1_ROUTE_KEYS:
        path = key.split(" ", 1)[1]
        assert "{" not in key, key
        assert not path.endswith("/"), key


def test_the_m2_flow_keys_are_present_unconditionally():
    """M2's six flow routes exist in every environment."""
    assert IDENTITY_M2_ROUTE_KEYS <= gateway_route_keys()["identity"]


def test_the_m2_keys_are_literal_and_do_not_end_in_a_slash():
    """No `{proxy+}` and no trailing slash, exactly as M1's are checked."""
    for key in IDENTITY_M2_ROUTE_KEYS:
        path = key.split(" ", 1)[1]
        assert "{" not in key, key
        assert not path.endswith("/"), key


def test_every_m2_key_is_a_post():
    """All six are state changing, which is why none of them is anonymous."""
    for key in IDENTITY_M2_ROUTE_KEYS:
        assert key.startswith("POST "), key


def test_no_m2_flow_route_is_anonymous():
    """The staging access gate stays exactly two documents wide."""
    anonymous = set(ANONYMOUS_ROUTE_ENTRY.findall(_terraform_source()))

    assert IDENTITY_M2_ROUTE_KEYS & anonymous == set(), sorted(
        IDENTITY_M2_ROUTE_KEYS & anonymous
    )


def test_the_m2_keys_route_to_the_identity_function():
    """Not to `content`, which owns the neighbouring `/api/v1/admin` surface."""
    for key in IDENTITY_M2_ROUTE_KEYS:
        assert key in gateway_route_keys()["identity"], key


def test_the_m3_email_keys_are_present_unconditionally():
    """M3's four keys exist whether or not the sender is configured."""
    assert IDENTITY_M3_ROUTE_KEYS <= gateway_route_keys()["identity"]


def test_the_m3_keys_are_literal_and_do_not_end_in_a_slash():
    """No `{proxy+}` and no trailing slash, exactly as M1's and M2's are checked."""
    for key in IDENTITY_M3_ROUTE_KEYS:
        path = key.split(" ", 1)[1]
        assert "{" not in key, key
        assert not path.endswith("/"), key


def test_every_m3_key_is_a_post():
    """All four are POSTs, including the two confirmations."""
    for key in IDENTITY_M3_ROUTE_KEYS:
        assert key.startswith("POST "), key


def test_no_m3_email_route_is_anonymous():
    """The staging access gate stays exactly two documents wide, again."""
    anonymous = set(ANONYMOUS_ROUTE_ENTRY.findall(_terraform_source()))

    assert IDENTITY_M3_ROUTE_KEYS & anonymous == set(), sorted(
        IDENTITY_M3_ROUTE_KEYS & anonymous
    )


def test_the_m3_keys_route_to_the_identity_function():
    """Not to `content`, and not to `public` because they are signed out flows."""
    for key in IDENTITY_M3_ROUTE_KEYS:
        assert key in gateway_route_keys()["identity"], key


def test_the_reset_pair_does_not_collide_with_the_verify_pair():
    """Four distinct keys, two prefixes, no key that is a prefix of another."""
    assert len(IDENTITY_M3_ROUTE_KEYS) == 4
    assert len(IDENTITY_M2_ROUTE_KEYS & IDENTITY_M3_ROUTE_KEYS) == 0


def test_the_m4_mfa_keys_are_present_unconditionally():
    """M4's six keys exist whether or not anybody has enrolled a factor."""
    assert IDENTITY_M4_ROUTE_KEYS <= gateway_route_keys()["identity"]


def test_the_m4_keys_are_literal_and_do_not_end_in_a_slash():
    """No `{proxy+}` and no trailing slash, exactly as M1, M2 and M3 are checked."""
    for key in IDENTITY_M4_ROUTE_KEYS:
        path = key.split(" ", 1)[1]
        assert "{" not in key, key
        assert not path.endswith("/"), key


def test_every_m4_key_is_a_post():
    """All six are POSTs, including `step-up` and `recovery-codes`."""
    for key in IDENTITY_M4_ROUTE_KEYS:
        assert key.startswith("POST "), key


def test_no_m4_mfa_route_is_anonymous():
    """The staging access gate stays exactly two documents wide, a third time."""
    anonymous = set(ANONYMOUS_ROUTE_ENTRY.findall(_terraform_source()))

    assert IDENTITY_M4_ROUTE_KEYS & anonymous == set(), sorted(
        IDENTITY_M4_ROUTE_KEYS & anonymous
    )


def test_the_m4_keys_route_to_the_identity_function():
    """Not to `public`, and not to `content`."""
    for key in IDENTITY_M4_ROUTE_KEYS:
        assert key in gateway_route_keys()["identity"], key


def test_the_totp_login_key_does_not_collide_with_the_login_key():
    """`login` and `login/totp` are two distinct literal keys, not one plus a typo."""
    assert "POST /api/auth/login" in gateway_route_keys()["identity"]
    assert "POST /api/auth/login/totp" in gateway_route_keys()["identity"]
    assert len(IDENTITY_M4_ROUTE_KEYS) == 6
    assert IDENTITY_M4_ROUTE_KEYS & IDENTITY_M2_ROUTE_KEYS == set()
    assert IDENTITY_M4_ROUTE_KEYS & IDENTITY_M3_ROUTE_KEYS == set()
    assert IDENTITY_M4_ROUTE_KEYS & IDENTITY_M1_ROUTE_KEYS == set()


def test_the_m4_keys_match_the_paths_the_package_declares():
    """The six keys are the package's own suffixes under the issuer's path."""
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
    """M1's hole in the staging access gate, held to exactly two documents."""
    anonymous = set(ANONYMOUS_ROUTE_ENTRY.findall(_terraform_source()))
    assert IDENTITY_M1_ANONYMOUS_KEYS <= anonymous, sorted(anonymous)
    assert "GET /api/auth/health" not in anonymous


def test_the_anonymous_surface_is_exactly_the_two_discovery_documents():
    """The whole gate hole, across every file, in one place."""
    anonymous = set(ANONYMOUS_ROUTE_ENTRY.findall(_terraform_source()))
    assert anonymous == IDENTITY_M1_ANONYMOUS_KEYS, sorted(anonymous)


def test_identity_has_two_route_keys_for_its_single_prefix():
    """The prefix is `/api/v1/admin`, and it takes the same two keys as cut 3."""
    assert identity_route_keys() == {
        "ANY /api/v1/admin",
        "ANY /api/v1/admin/{proxy+}",
    }


def test_identity_serves_exactly_one_route_and_it_is_the_login_post():
    """The premise the two keys are sized against."""
    assert domain_paths("identity") == {"/api/v1/admin/login"}


def test_every_identity_route_the_app_serves_has_a_gateway_route_key():
    """The cut is complete: no identity path falls through to `$default`."""
    keys = identity_route_keys()
    unrouted = sorted(
        path
        for path in domain_paths("identity")
        if not any(matches(k, path) for k in keys)
    )
    assert unrouted == []


def test_the_greedy_admin_key_is_what_carries_the_login_route():
    """Which of the two keys does the work, stated rather than implied."""
    assert matches("ANY /api/v1/admin/{proxy+}", "/api/v1/admin/login")
    assert not matches("ANY /api/v1/admin", "/api/v1/admin/login")


def test_the_bare_admin_key_is_deliberate_and_matches_nothing_served():
    """The one identity key that points at no served path, kept on purpose."""
    paths = domain_paths("identity")
    assert not any(matches("ANY /api/v1/admin", path) for path in paths)
    assert "/api/v1/admin" not in paths
    assert "/api/v1/admin/" not in paths


def test_no_identity_route_key_reaches_outside_the_admin_prefix():
    """The other direction, in the form that is meaningful for this domain."""
    for key in identity_route_keys():
        key_path = key.split(" ", 1)[1]
        assert key_path == "/api/v1/admin" or key_path.startswith("/api/v1/admin/"), key


def test_the_identity_keys_use_any_rather_than_post():
    """ANY, so a wrong method answers 405 from `identity`, not from the monolith."""
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
    """Every `(method, path)` the identity application mounts under `/api/auth`."""
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
    """The assertion whose absence let M5 and M6 ship unreachable."""
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
    """M5's eight keys exist, and their suffixes are the package's own."""
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
    """No `{proxy+}`, no trailing slash, on the same rule every milestone follows."""
    for key in IDENTITY_M5_ROUTE_KEYS | IDENTITY_M6_ROUTE_KEYS:
        path = key.split(" ", 1)[1]
        assert "{proxy+}" not in key, key
        assert not path.endswith("/"), key
        for segment in path.split("/"):
            assert "{" not in segment or segment.endswith("}"), key


def test_no_m5_or_m6_route_is_anonymous():
    """The staging access gate still stays exactly two documents wide."""
    anonymous = set(ANONYMOUS_ROUTE_ENTRY.findall(_terraform_source()))

    overlap = (IDENTITY_M5_ROUTE_KEYS | IDENTITY_M6_ROUTE_KEYS) & anonymous
    assert overlap == set(), sorted(overlap)


def test_the_anonymous_login_legs_are_not_behind_the_identity_jwt_authorizer():
    """The four routes a caller reaches with no token of ours, stated as a set."""
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
    """The other half of the split: every route that reads a verified subject."""
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
    """The brace-balanced block that `opening` starts, `opening` included."""
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
    """`local.domain_identity_jwt_route_paths`, per domain, as plain sets."""
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
    """Every dependency callable's name in this route's tree, however deep."""
    names = set()
    stack = list(dependant.dependencies)
    while stack:
        sub = stack.pop()
        if sub.call is not None:
            names.add(getattr(sub.call, "__name__", ""))
        stack.extend(sub.dependencies)
    return names


def _api_routes(app):
    """Every route the application serves, flattened, across two FastAPI shapes."""
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
    """The route keys this domain's application will not serve anonymously."""
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
    """The guard on the guard."""
    for domain in PROTECTED_DOMAINS:
        served = _api_routes(build_domain_app(domain))
        assert len(served) > 5, f"{domain}: route walk found {len(served)} routes"
        assert routes_requiring_a_caller(domain), f"{domain}: no protected routes found"


def test_the_domain_map_lists_exactly_the_domains_it_should():
    """Only `content` and `resume` have protected `/api/v1` routes."""
    assert set(domain_identity_jwt_route_paths()) == set(PROTECTED_DOMAINS)


@pytest.mark.parametrize("domain", PROTECTED_DOMAINS)
def test_every_route_requiring_a_caller_is_flagged_in_terraform(domain):
    """Direction one: a protected route with no flag answers 401 in identity mode."""
    required = routes_requiring_a_caller(domain)
    flagged = domain_identity_jwt_route_paths()[domain]

    missing = sorted(required - flagged)
    assert missing == [], (
        f"{domain} routes requiring CurrentUser but not flagged in "
        f"apigateway.tf: {missing}"
    )


@pytest.mark.parametrize("domain", PROTECTED_DOMAINS)
def test_every_flagged_key_is_a_route_that_requires_a_caller(domain):
    """Direction two: a flag on a public read breaks the anonymous site."""
    required = routes_requiring_a_caller(domain)
    flagged = domain_identity_jwt_route_paths()[domain]

    extra = sorted(flagged - required)
    assert extra == [], (
        f"{domain} route keys flagged in apigateway.tf that the application "
        f"serves without requiring a caller: {extra}"
    )


def test_the_two_sets_are_equal_across_every_domain():
    """The same claim as the two above, stated once as the set equality."""
    derived = set().union(
        *(routes_requiring_a_caller(domain) for domain in PROTECTED_DOMAINS)
    )
    assert derived == flagged_domain_route_keys()


def test_every_flagged_key_is_routed_to_the_domain_that_serves_it():
    """Each flagged key reaches the same function it would have without the flag."""
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
    """The apply-time failure a green plan does not catch."""
    trailing = sorted(key for key in flagged_domain_route_keys() if key.endswith("/"))
    assert trailing == []


def test_no_flagged_domain_key_uses_a_greedy_segment():
    """Each flag names one route, not a subtree."""
    greedy = sorted(key for key in flagged_domain_route_keys() if "{proxy+}" in key)
    assert greedy == []


def test_no_flagged_domain_key_uses_any_as_its_method():
    """`ANY` would flag the GET alongside the write it was meant for."""
    method_less = sorted(
        key for key in flagged_domain_route_keys() if key.startswith("ANY ")
    )
    assert method_less == []


def test_the_domain_flag_is_gated_on_a_variable_rather_than_hardcoded():
    """The keys exist either way; only enforcement moves."""
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
    """The default is what an apply with no variable set does."""
    variables = (REPO / "terraform" / "variables.tf").read_text(encoding="utf-8")
    block = _block(variables, 'variable "domain_jwt_enforced" {')

    assert re.search(r"^\s*type\s*=\s*bool\s*$", block, re.MULTILINE), block
    assert re.search(r"^\s*default\s*=\s*false\s*$", block, re.MULTILINE), block


def test_the_flagged_keys_reach_the_staging_gate():
    """Gate mode enforces from `module.api.identity_jwt_route_keys`."""
    gate = (REPO / "terraform" / "staging_access_gate.tf").read_text(encoding="utf-8")
    gate = _strip_comments(gate)

    assert "module.api.identity_jwt_route_keys" in gate
    assert re.search(r"identity_jwt_route_keys\s*=", gate)


def test_the_flagged_keys_are_the_admin_surface_and_not_the_public_reads():
    """A spot check in plain terms, against the site's own anonymous pages."""
    flagged = flagged_domain_route_keys()

    must_stay_open = {
        "GET /api/v1/posts",
        "GET /api/v1/posts/{slug}",
        "GET /api/v1/posts/categories",
        "GET /api/v1/projects",
        "GET /api/v1/site-content",
    }

    assert must_stay_open & flagged == set(), sorted(must_stay_open & flagged)
