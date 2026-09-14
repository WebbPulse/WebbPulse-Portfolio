"""The rules the domain packages exist to enforce."""

import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2] / "app"
DOMAINS_DIR = APP / "domains"
DOMAINS = sorted(path.name for path in DOMAINS_DIR.iterdir() if path.is_dir() and not path.name.startswith("__"))

COMMON_DIR = APP / "common"

COMPOSITION_ROOT = {
    COMMON_DIR / "composition" / "wiring.py",
    COMMON_DIR / "composition" / "app.py",
}


def _domain_files(domain):
    """Every Python file under one domain package."""
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
    """The domain packages are exactly content, identity, public and resume."""
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

    `entrypoint.py` is the exception, and the reason the rule can hold for every
    other file: it is the domain's own composition root, so it is the single
    place allowed to read the shared wiring.
    """
    forbidden = ("app.common.composition", "app.main", "app.api", "app.lambda_handler")
    offences = [
        (str(path.relative_to(APP.parent)), module)
        for path in _domain_files(domain)
        if path.name != "entrypoint.py"
        for module in _imported_modules(path)
        if any(module == name or module.startswith(f"{name}.") for name in forbidden)
    ]
    assert offences == []


def test_only_the_composition_root_assembles_more_than_one_domain():
    """Only the composition root, and the recorded exception, touches two domains."""
    offenders = []
    for path in APP.rglob("*.py"):
        if path in COMPOSITION_ROOT or DOMAINS_DIR in path.parents:
            continue
        modules = _imported_modules(path)
        touched = {
            domain
            for domain in DOMAINS
            for module in modules
            if module == f"app.domains.{domain}" or module.startswith(f"app.domains.{domain}.")
        }
        if len(touched) > 1:
            offenders.append((str(path.relative_to(APP.parent)), sorted(touched)))
    assert offenders == [("app/common/core/middleware.py", ["content", "identity"])]


@pytest.mark.parametrize("domain", DOMAINS)
def test_only_router_modules_import_fastapi(domain):
    """FastAPI stays at the domain's edge, so the rest of it stays testable."""
    allowed = {
        "entrypoint.py",
        "package_glue.py",
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
        and any(module == "fastapi" or module.startswith("fastapi.") for module in _imported_modules(path))
    ]
    assert offences == []


LAZY_DOMAIN_HOSTS = {
    COMMON_DIR / "composition" / "wiring.py": "the per-domain router loaders",
    COMMON_DIR / "core" / "middleware.py": "the per-domain seeders",
}
"""The only files under `app/common` allowed to name a domain, and why. Each
imports one domain inside a function body, so importing the module itself still
imports no domain package."""


def _module_level_imports(path):
    """Every module this file imports at module level, function bodies excluded."""
    package = path.relative_to(APP.parent).with_suffix("").parts
    if package[-1] == "__init__":
        package = package[:-1]
    tree = ast.parse(path.read_text(), filename=str(path))
    modules = []

    def visit(node, in_function):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                visit(child, True)
                continue
            if not in_function:
                if isinstance(child, ast.Import):
                    modules.extend(alias.name for alias in child.names)
                elif isinstance(child, ast.ImportFrom):
                    if child.level:
                        base = package[: len(package) - child.level]
                        prefix = ".".join(base + ((child.module,) if child.module else ()))
                    else:
                        prefix = child.module or ""
                    modules.append(prefix)
                    modules.extend(f"{prefix}.{alias.name}" for alias in child.names)
            visit(child, in_function)

    visit(tree, False)
    return modules


def test_common_never_imports_a_domain_at_module_level():
    """Rule 1. `app.common` is the non-domain half, so importing it costs no domain.

    Only the lazy per-domain loaders may name a domain at all, and only from
    inside a function body, which this asserts by reading module level alone.
    """
    offenders = []
    for path in sorted(COMMON_DIR.rglob("*.py")):
        for module in _module_level_imports(path):
            if module == "app.domains" or module.startswith("app.domains."):
                offenders.append((str(path.relative_to(APP.parent)), module))
    assert offenders == []


def test_only_the_recorded_hosts_name_a_domain_at_all():
    """Rule 1's exception list, so a new common-to-domain edge has to be declared."""
    offenders = sorted(
        str(path.relative_to(APP.parent))
        for path in COMMON_DIR.rglob("*.py")
        if path not in LAZY_DOMAIN_HOSTS
        and any(module == "app.domains" or module.startswith("app.domains.") for module in _imported_modules(path))
    )
    assert offenders == []


@pytest.mark.parametrize("domain", DOMAINS)
def test_a_domain_imports_only_common_and_itself(domain):
    """Rule 2. A domain's only `app` dependencies are `app.common` and its own package."""
    allowed = ("app.common", f"app.domains.{domain}", "app.domains", "app")
    offences = [
        (str(path.relative_to(APP.parent)), module)
        for path in _domain_files(domain)
        for module in _imported_modules(path)
        if module.startswith("app") and not any(module == name or module.startswith(f"{name}.") for name in allowed)
    ]
    assert offences == []
