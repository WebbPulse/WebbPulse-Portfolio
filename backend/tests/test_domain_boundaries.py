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

COMPOSITION_ROOT = {
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
    """A domain never reaches back up into the thing that assembles it.

    `app.composition` is the live root. The other three named here are the
    monolith's deleted modules, kept in the list so an import of one is caught
    as a boundary violation rather than as a bare `ModuleNotFoundError` if
    somebody restores them.
    """
    forbidden = ("app.composition", "app.main", "app.api", "app.lambda_handler")
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
    assert offenders == [("app/core/middleware.py", ["content", "identity"])]


@pytest.mark.parametrize("domain", DOMAINS)
def test_only_router_modules_import_fastapi(domain):
    """FastAPI stays at the domain's edge, so the rest of it stays testable."""
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
