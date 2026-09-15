"""Rules 3 and 4: what each entrypoint's import closure may contain, and that
every file under `app/` is in some closure.

The closure is computed statically rather than by importing, so it holds for the
deployed image without needing AWS or an environment. Module level imports and
function body imports are both followed, except that the per-domain lazy loaders
are attributed only to the domain they load, which is the property that lets one
`app/` tree ship as four single-domain functions.
"""

import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2] / "app"
COMMON_DIR = APP / "common"
DOMAINS_DIR = APP / "domains"
DOMAINS = sorted(path.name for path in DOMAINS_DIR.iterdir() if path.is_dir() and not path.name.startswith("__"))

LAZY_DOMAIN_HOSTS = (
    COMMON_DIR / "composition" / "wiring.py",
    COMMON_DIR / "core" / "middleware.py",
)
"""Files whose function body `app.domains.<name>` imports belong to `<name>` alone."""

SHARED = {DOMAINS_DIR / "__init__.py"}
"""Files under `app/domains` that belong to no single domain, so reaching one is
not reaching another domain."""

UNREACHED_ALLOW_LIST = {
    "app/common/composition/app.py": (
        "Root A, the whole-surface app. The test suite's `client` fixture and a "
        "local `uvicorn app.common.composition.app:app` import it; nothing deploys it."
    ),
}
"""Files no entrypoint reaches, each with the reason it still belongs in the tree."""

ALL_FILES = {path for path in APP.rglob("*.py") if "__pycache__" not in path.parts}


def _rel(path):
    """A file's path relative to the backend directory, as the allow list spells it."""
    return str(path.relative_to(APP.parent))


def _module_files(module):
    """Every file that importing the dotted module `module` executes."""
    if not module.startswith("app"):
        return []
    parts = module.split(".")
    found = []
    for index in range(1, len(parts) + 1):
        init = APP.parent.joinpath(*parts[:index], "__init__.py")
        if init in ALL_FILES:
            found.append(init)
    leaf = APP.parent.joinpath(*parts).with_suffix(".py")
    if leaf in ALL_FILES:
        found.append(leaf)
    return found


def _edges(path):
    """This file's module level and function body `app` imports, kept apart.

    `TYPE_CHECKING` blocks are skipped: they run under a type checker, never at
    runtime, so they cannot pull a domain into a deployed function.
    """
    parts = path.relative_to(APP.parent).with_suffix("").parts
    package = parts[:-1]
    """The package a relative import counts levels from. For `pkg/__init__.py`
    that is `pkg` itself, which dropping the final part gives in both cases."""
    eager, lazy = set(), set()

    def resolve(node):
        """Every `app` file this import node reaches."""
        found = []
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.extend(_module_files(alias.name))
        else:
            if node.level:
                base = package[: len(package) - node.level + 1]
                prefix = ".".join(base + ((node.module,) if node.module else ()))
            else:
                prefix = node.module or ""
            if prefix.startswith("app"):
                found.extend(_module_files(prefix))
                for alias in node.names:
                    found.extend(_module_files(f"{prefix}.{alias.name}"))
        return found

    def visit(node, in_function):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                visit(child, True)
                continue
            if isinstance(child, ast.If) and isinstance(child.test, ast.Name) and child.test.id == "TYPE_CHECKING":
                continue
            if isinstance(child, (ast.Import, ast.ImportFrom)):
                target = lazy if in_function else eager
                target.update(resolve(child))
            visit(child, in_function)

    visit(ast.parse(path.read_text(), filename=str(path)), False)
    return eager, lazy


EAGER, LAZY = {}, {}
for _path in ALL_FILES:
    EAGER[_path], LAZY[_path] = _edges(_path)


def _domain_of(path):
    """The domain a file belongs to, or `None` for common and shared files."""
    if DOMAINS_DIR not in path.parents or path in SHARED:
        return None
    return path.relative_to(DOMAINS_DIR).parts[0]


LOADER_EDGES = {domain: set() for domain in DOMAINS}
for _host in LAZY_DOMAIN_HOSTS:
    for _target in LAZY[_host]:
        _owner = _domain_of(_target)
        if _owner is not None:
            LOADER_EDGES[_owner].add(_target)


def _eager_closure(seeds):
    """Everything reachable from `seeds` by module level imports alone."""
    seen, stack = set(), list(seeds)
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        stack.extend(EAGER[current])
    return seen


def _closure(domain):
    """Every file this domain's entrypoint executes, lazy imports included.

    A lazy import inside one of the per-domain hosts counts only for the domain
    it loads; every other lazy import counts for whoever reaches the file.
    """
    entry = DOMAINS_DIR / domain / "entrypoint.py"
    reached = _eager_closure({entry} | LOADER_EDGES[domain])
    while True:
        extra = set()
        for path in reached:
            if path in LAZY_DOMAIN_HOSTS:
                extra |= {target for target in LAZY[path] if _domain_of(target) is None}
            else:
                extra |= LAZY[path]
        grown = _eager_closure(reached | extra)
        if grown == reached:
            return reached
        reached = grown


CLOSURES = {domain: _closure(domain) for domain in DOMAINS}


def test_the_domains_each_have_an_entrypoint():
    """Every domain package carries the module its image runs."""
    missing = [domain for domain in DOMAINS if not (DOMAINS_DIR / domain / "entrypoint.py").is_file()]
    assert missing == []


@pytest.mark.parametrize("domain", DOMAINS)
def test_an_entrypoint_reaches_no_other_domain(domain):
    """Rule 3. The claim that lets one tree deploy as four single-domain functions."""
    foreign = sorted(_rel(path) for path in CLOSURES[domain] if (_domain_of(path) or domain) != domain)
    assert foreign == []


@pytest.mark.parametrize("domain", DOMAINS)
def test_an_entrypoint_reaches_its_own_router(domain):
    """The closure is real: each entrypoint does reach the domain it serves."""
    assert (DOMAINS_DIR / domain / "router.py") in CLOSURES[domain]


def test_every_file_is_reachable_or_allow_listed():
    """Rule 4. Nothing sits in the tree unreached without a recorded reason."""
    reached = set().union(*CLOSURES.values())
    unreached = sorted(_rel(path) for path in ALL_FILES - reached)
    assert unreached == sorted(UNREACHED_ALLOW_LIST)


def test_the_allow_list_has_no_stale_entry():
    """An allow-listed file that became reachable should leave the list."""
    reached = {_rel(path) for path in set().union(*CLOSURES.values())}
    assert sorted(name for name in UNREACHED_ALLOW_LIST if name in reached) == []
