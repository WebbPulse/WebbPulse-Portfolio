"""Guards against a product copy of something `webbpulse` already ships.

Each deleted module was replaced by a shared implementation. A file reappearing
under that name is how a product quietly forks the package again, so the names
are pinned here rather than left to review.
"""

from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2] / "app"

DELETED_MODULES = (
    "identity_claims",
    "secrets",
)
"""Module basenames removed in favour of `webbpulse.identity.claims` and
`webbpulse.security`. A file of this name anywhere under `app/` is a regression."""

FORBIDDEN_IMPORTS = ("webbpulse.ci",)
"""Modules `webbpulse` no longer ships. An import of one fails at runtime."""


def app_sources():
    """Every Python source file under `app/`, excluding caches."""
    return [path for path in APP.rglob("*.py") if "__pycache__" not in path.parts]


@pytest.mark.unit
@pytest.mark.parametrize("name", DELETED_MODULES)
def test_a_deleted_module_has_not_reappeared(name):
    """The product copy was deleted; the shared implementation is the only one."""
    found = [str(path.relative_to(APP)) for path in app_sources() if path.stem == name]
    assert not found, f"app/{name}.py was deleted in favour of the shared package: {found}"


@pytest.mark.unit
@pytest.mark.parametrize("module", FORBIDDEN_IMPORTS)
def test_nothing_imports_a_removed_shared_module(module):
    """`webbpulse.ci` was removed in 0.29.0, so importing it cannot resolve."""
    offenders = [
        str(path.relative_to(APP))
        for path in app_sources()
        if f"import {module}" in path.read_text() or f"from {module}" in path.read_text()
    ]
    assert not offenders, f"{module} no longer exists in webbpulse: {offenders}"


@pytest.mark.unit
def test_the_repository_marshals_through_the_shared_package():
    """`marshal` and its `TypeSerializer` went with the shared action builders."""
    source = (APP / "common" / "db" / "repository.py").read_text()
    assert "TypeSerializer" not in source
    assert "def marshal(" not in source


@pytest.mark.unit
def test_the_repository_pages_through_the_shared_helpers():
    """Hand-rolled `LastEvaluatedKey` loops are what the shared helpers replaced."""
    source = (APP / "common" / "db" / "repository.py").read_text()
    assert "LastEvaluatedKey" not in source
    assert "UnprocessedKeys" not in source
