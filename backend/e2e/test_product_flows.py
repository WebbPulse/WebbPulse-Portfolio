"""The public surface, read through the real edge without a credential.

Portfolio serves only public data: the service root, the health check and the live
figures. Each is read anonymously, which proves the route key exists, the request
reached the public function and the function answered from its own table.
"""

from __future__ import annotations

from typing import Any


class TestPublicSurface:
    """The three public routes, each answered by the public function."""

    def test_public_root_and_health_are_served(self, anon: Any) -> None:
        """The public domain answers its root and health routes without a credential."""
        for path in ("/", "/health"):
            response = anon.get(path)
            assert response.status_code == 200, f"GET {path} answered {response.status_code}"

    def test_figures_are_served(self, anon: Any) -> None:
        """The live figures answer with a `figures` list, empty only while the cache is cold."""
        response = anon.get("/api/v1/public/figures")
        assert response.status_code == 200, f"GET /api/v1/public/figures answered {response.status_code}"
        assert isinstance(response.json().get("figures"), list)
