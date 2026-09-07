"""The rules the domain packages exist to enforce.

These are structural tests, not behavioural ones. They read the source with
``ast`` rather than importing it, so a violation is reported as the file and
the import that broke the rule instead of as an import cycle.
"""

import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "app"
DOMAINS_DIR = APP / "domains"
DOMAINS = sorted(
    path.name
    for path in DOMAINS_DIR.iterdir()
    if path.is_dir() and not path.name.startswith("__")
)

# The composition roots: the only places allowed to assemble routers from more
# than one domain.
#
# `app/main.py` and `app/api/v1/api.py` are the monolith's, kept exactly as they
# were so its published OpenAPI document does not move. `app/composition/` is
# the split's: `wiring.py` names all four domains and `app.py` walks them, which
# is what makes root A and the four root B entrypoints two views of one list
# rather than two lists that can drift.
COMPOSITION_ROOT = {
    APP / "main.py",
    APP / "api" / "v1" / "api.py",
    APP / "composition" / "wiring.py",
    APP / "composition" / "app.py",
}


def _domain_files(domain):
    return sorted((DOMAINS_DIR / domain).rglob("*.py"))


def _imported_modules(path):
    """Every absolute module path this file imports, relative imports resolved."""
    package = path.relative_to(APP.parent).with_suffix("").parts
    if package[-1] == "__init__":
        package = package[:-1]
    tree = ast.parse(path.read_text(), filename=str(path))
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package[: len(package) - node.level]
                prefix = ".".join(base + ((node.module,) if node.module else ()))
            else:
                prefix = node.module or ""
            modules.append(prefix)
            modules.extend(f"{prefix}.{alias.name}" for alias in node.names)
    return modules


def test_domains_are_the_four_the_plan_names():
    assert DOMAINS == ["content", "identity", "public", "resume"]


@pytest.mark.parametrize("domain", DOMAINS)
def test_no_cross_domain_imports(domain):
    """No file under domains/<name>/ may import from domains/<other>/."""
    others = [f"app.domains.{other}" for other in DOMAINS if other != domain]
    offences = [
        (str(path.relative_to(APP.parent)), module)
        for path in _domain_files(domain)
        for module in _imported_modules(path)
        if any(module == other or module.startswith(f"{other}.") for other in others)
    ]
    assert offences == []


@pytest.mark.parametrize("domain", DOMAINS)
def test_domains_do_not_import_the_composition_root(domain):
    """A domain never reaches back up into the thing that assembles it."""
    forbidden = ("app.main", "app.api", "app.lambda_handler")
    offences = [
        (str(path.relative_to(APP.parent)), module)
        for path in _domain_files(domain)
        for module in _imported_modules(path)
        if any(module == name or module.startswith(f"{name}.") for name in forbidden)
    ]
    assert offences == []


def test_only_the_composition_root_assembles_more_than_one_domain():
    offenders = []
    for path in APP.rglob("*.py"):
        if path in COMPOSITION_ROOT or DOMAINS_DIR in path.parents:
            continue
        modules = _imported_modules(path)
        touched = {
            domain
            for domain in DOMAINS
            for module in modules
            if module == f"app.domains.{domain}"
            or module.startswith(f"app.domains.{domain}.")
        }
        if len(touched) > 1:
            offenders.append((str(path.relative_to(APP.parent)), sorted(touched)))
    # `app.core.middleware` is the one shared module that reaches into two
    # domains, and it is listed here deliberately rather than exempted: when
    # the seeding moves out of the middleware stack in a later PR, this
    # assertion is what notices.
    #
    # Its two imports sit inside `SeedMiddleware.__call__`, not at module
    # scope, and that placement is what keeps the rule honest at runtime as
    # well as in the source. `TrailingSlashMiddleware` lives in the same module
    # and every domain application adds it, so a module-level import would put
    # `content` and `identity` in all four images.
    # `tests/entrypoints/test_entrypoint_isolation.py` asserts the consequence
    # directly, by reading `sys.modules` after each entrypoint builds.
    assert offenders == [("app/core/middleware.py", ["content", "identity"])]


@pytest.mark.parametrize("domain", DOMAINS)
def test_only_router_modules_import_fastapi(domain):
    """FastAPI stays at the domain's edge, so the rest of it stays testable."""
    # Every module here declares routes: they are the domain's HTTP edge. The
    # point of the assertion is that nothing else in a domain grows one.
    allowed = {
        "certifications.py",
        "crud_router.py",
        "education.py",
        "experience.py",
        "posts.py",
        "projects.py",
        "router.py",
        "seo.py",
        "site_content.py",
        "skills.py",
    }
    offences = [
        str(path.relative_to(APP.parent))
        for path in _domain_files(domain)
        if path.name not in allowed
        and any(
            module == "fastapi" or module.startswith("fastapi.")
            for module in _imported_modules(path)
        )
    ]
    assert offences == []
