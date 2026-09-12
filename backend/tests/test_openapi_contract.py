"""The public API contract, pinned."""

from app.composition.app import build_app

from .routes import method_path_pairs

app = build_app()

EXPECTED_OPERATIONS = [
    ("GET", "/api/v1/posts/", "get_posts_api_v1_posts__get", ["posts"]),
    ("GET", "/api/v1/posts/admin", "get_all_posts_api_v1_posts_admin_get", ["posts"]),
    ("POST", "/api/v1/posts/admin", "create_post_api_v1_posts_admin_post", ["posts"]),
    (
        "GET",
        "/api/v1/posts/categories",
        "get_categories_api_v1_posts_categories_get",
        ["posts"],
    ),
    (
        "POST",
        "/api/v1/posts/categories",
        "create_category_api_v1_posts_categories_post",
        ["posts"],
    ),
    ("GET", "/api/v1/posts/{slug}", "get_post_api_v1_posts__slug__get", ["posts"]),
    (
        "GET",
        "/api/v1/posts/category/{category_slug}",
        "get_posts_by_category_api_v1_posts_category__category_slug__get",
        ["posts"],
    ),
    (
        "PUT",
        "/api/v1/posts/admin/{post_id}",
        "update_post_api_v1_posts_admin__post_id__put",
        ["posts"],
    ),
    (
        "DELETE",
        "/api/v1/posts/admin/{post_id}",
        "delete_post_api_v1_posts_admin__post_id__delete",
        ["posts"],
    ),
    (
        "POST",
        "/api/v1/posts/admin/{post_id}/publish",
        "publish_post_api_v1_posts_admin__post_id__publish_post",
        ["posts"],
    ),
    (
        "PUT",
        "/api/v1/posts/categories/{category_id}",
        "update_category_api_v1_posts_categories__category_id__put",
        ["posts"],
    ),
    (
        "DELETE",
        "/api/v1/posts/categories/{category_id}",
        "delete_category_api_v1_posts_categories__category_id__delete",
        ["posts"],
    ),
    ("POST", "/api/v1/admin/login", "login_api_v1_admin_login_post", ["admin"]),
    (
        "GET",
        "/api/v1/projects/{item_id}",
        "get_item_api_v1_projects__item_id__get",
        ["projects"],
    ),
    (
        "PUT",
        "/api/v1/projects/{item_id}",
        "update_item_api_v1_projects__item_id__put",
        ["projects"],
    ),
    (
        "DELETE",
        "/api/v1/projects/{item_id}",
        "delete_item_api_v1_projects__item_id__delete",
        ["projects"],
    ),
    ("POST", "/api/v1/projects/", "create_item_api_v1_projects__post", ["projects"]),
    ("GET", "/api/v1/projects/", "get_projects_api_v1_projects__get", ["projects"]),
    ("GET", "/api/v1/experience/", "list_items_api_v1_experience__get", ["experience"]),
    (
        "POST",
        "/api/v1/experience/",
        "create_item_api_v1_experience__post",
        ["experience"],
    ),
    (
        "GET",
        "/api/v1/experience/{item_id}",
        "get_item_api_v1_experience__item_id__get",
        ["experience"],
    ),
    (
        "PUT",
        "/api/v1/experience/{item_id}",
        "update_item_api_v1_experience__item_id__put",
        ["experience"],
    ),
    (
        "DELETE",
        "/api/v1/experience/{item_id}",
        "delete_item_api_v1_experience__item_id__delete",
        ["experience"],
    ),
    ("GET", "/api/v1/skills/", "list_items_api_v1_skills__get", ["skills"]),
    ("POST", "/api/v1/skills/", "create_item_api_v1_skills__post", ["skills"]),
    (
        "GET",
        "/api/v1/skills/{item_id}",
        "get_item_api_v1_skills__item_id__get",
        ["skills"],
    ),
    (
        "PUT",
        "/api/v1/skills/{item_id}",
        "update_item_api_v1_skills__item_id__put",
        ["skills"],
    ),
    (
        "DELETE",
        "/api/v1/skills/{item_id}",
        "delete_item_api_v1_skills__item_id__delete",
        ["skills"],
    ),
    ("GET", "/api/v1/education/", "list_items_api_v1_education__get", ["education"]),
    ("POST", "/api/v1/education/", "create_item_api_v1_education__post", ["education"]),
    (
        "GET",
        "/api/v1/education/{item_id}",
        "get_item_api_v1_education__item_id__get",
        ["education"],
    ),
    (
        "PUT",
        "/api/v1/education/{item_id}",
        "update_item_api_v1_education__item_id__put",
        ["education"],
    ),
    (
        "DELETE",
        "/api/v1/education/{item_id}",
        "delete_item_api_v1_education__item_id__delete",
        ["education"],
    ),
    (
        "GET",
        "/api/v1/certifications/",
        "list_items_api_v1_certifications__get",
        ["certifications"],
    ),
    (
        "POST",
        "/api/v1/certifications/",
        "create_item_api_v1_certifications__post",
        ["certifications"],
    ),
    (
        "GET",
        "/api/v1/certifications/{item_id}",
        "get_item_api_v1_certifications__item_id__get",
        ["certifications"],
    ),
    (
        "PUT",
        "/api/v1/certifications/{item_id}",
        "update_item_api_v1_certifications__item_id__put",
        ["certifications"],
    ),
    (
        "DELETE",
        "/api/v1/certifications/{item_id}",
        "delete_item_api_v1_certifications__item_id__delete",
        ["certifications"],
    ),
    (
        "GET",
        "/api/v1/site-content/",
        "get_site_content_api_v1_site_content__get",
        ["site-content"],
    ),
    (
        "PUT",
        "/api/v1/site-content/",
        "update_site_content_api_v1_site_content__put",
        ["site-content"],
    ),
    ("GET", "/", "root__get", []),
    ("GET", "/health", "health_check_health_get", []),
]

UNDOCUMENTED_ROUTES = [("GET", "/sitemap.xml"), ("GET", "/robots.txt")]


def _documented_operations():
    """(method, path, operationId, tags) for every documented operation."""
    document = app.openapi()
    return [
        (method.upper(), path, operation["operationId"], operation.get("tags", []))
        for path, item in document["paths"].items()
        for method, operation in item.items()
    ]


def test_openapi_operations_are_unchanged():
    """Same 42 operations, same ids, same tags. Order is asserted separately."""
    documented = _documented_operations()
    hashable = {
        (method, path, operation_id, tuple(tags))
        for method, path, operation_id, tags in documented
    }
    assert hashable == {
        (method, path, operation_id, tuple(tags))
        for method, path, operation_id, tags in EXPECTED_OPERATIONS
    }
    assert len(documented) == len(hashable) == len(EXPECTED_OPERATIONS) == 42


def test_the_whole_surface_orders_paths_by_domain():
    """Root A groups each domain's paths together. The monolith interleaved two."""
    paths = []
    for _, path, _, _ in _documented_operations():
        if path not in paths:
            paths.append(path)

    def domain_of(path):
        """The domain that owns a path, by prefix."""
        if path.startswith("/api/v1/admin"):
            return "identity"
        if path.startswith(("/api/v1/posts", "/api/v1/site-content")):
            return "content"
        if path.startswith("/api/v1/"):
            return "resume"
        return "public"

    runs = []
    for path in paths:
        domain = domain_of(path)
        if not runs or runs[-1] != domain:
            runs.append(domain)
    assert len(runs) == len(set(runs)) == 4, runs
    assert runs == ["content", "resume", "identity", "public"]

    from app.composition.wiring import build_domain_app

    for name in ("content", "resume", "identity", "public"):
        served = [p for p in paths if domain_of(p) == name]
        own = [
            p
            for p in build_domain_app(name).openapi()["paths"]
            if p not in ("/docs", "/redoc", "/openapi.json")
        ]
        assert served == own, name


def test_undocumented_routes_are_still_served():
    """The deliberately undocumented routes are served but stay out of the schema."""
    served = method_path_pairs(app, skip_documentation=False, skip_methods=())
    for method, path in UNDOCUMENTED_ROUTES:
        assert (method, path) in served
        assert path not in app.openapi()["paths"]


def test_route_count_matches_the_domain_map():
    """44 application routes: 14 content, 25 resume, 1 identity, 4 public."""
    pairs = method_path_pairs(app, skip_documentation=False)
    documentation = {
        (method, path)
        for method, path in pairs
        if path in ("/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json")
    }
    assert len(documentation) == 4
    application = pairs - documentation
    assert len(application) == 44

    content = {
        p
        for _, p in application
        if p.startswith(("/api/v1/posts", "/api/v1/site-content"))
    }
    resume_prefixes = (
        "/api/v1/projects",
        "/api/v1/experience",
        "/api/v1/skills",
        "/api/v1/education",
        "/api/v1/certifications",
    )
    counts = {
        "content": len(
            [
                1
                for _, p in application
                if p.startswith(("/api/v1/posts", "/api/v1/site-content"))
            ]
        ),
        "resume": len([1 for _, p in application if p.startswith(resume_prefixes)]),
        "identity": len([1 for _, p in application if p.startswith("/api/v1/admin")]),
        "public": len([1 for _, p in application if not p.startswith("/api/v1/")]),
    }
    assert counts == {"content": 14, "resume": 25, "identity": 1, "public": 4}
    assert content


def test_the_split_serves_this_exact_contract():
    """The monolith's pinned document, reassembled from the four domain apps."""
    from app.composition.wiring import DOMAIN_NAMES, build_domain_app

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

    expected = {
        (method, path, operation_id, tuple(tags))
        for method, path, operation_id, tags in EXPECTED_OPERATIONS
    }
    assert union == expected
