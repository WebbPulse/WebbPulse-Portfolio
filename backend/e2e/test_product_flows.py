"""One authenticated round trip per domain that accepts writes, through the real edge.

A read proves something answered; only a write that is read back and then deleted proves
the authorizer attached, the route carried the claims, and the row reached the table the
function actually owns. Every name carries this run's prefix, so a flow that dies midway
leaves something the next run's sweep can find and delete.

The identity and public domains declare no writes: identity serves only `POST
/api/v1/admin/login`, which the plugin's own identity group already exercises, and public
is read only by design. Both are covered here by the reads that prove they are served.
"""

from __future__ import annotations

from typing import Any

import pytest

from e2e.resources import CREATED_CATEGORY, CREATED_CERTIFICATION, CREATED_POST


def _created(response: Any, path: str) -> dict[str, Any]:
    """Assert a create succeeded and return its body.

    A 401 or 403 here means the user this run signed in as is not an admin, which every
    write route requires, so it is called out rather than left as a bare status mismatch.
    """
    if response.status_code in (401, 403):
        pytest.fail(
            f"POST {path} answered {response.status_code}. Every write route in this "
            "product is admin only, so the user this run signed in as needs its admin "
            "flag set. An ephemeral user gets it from the on_user_created hook, and the "
            "durable one carries it on its row."
        )
    assert response.status_code in (200, 201), f"POST {path} answered {response.status_code}: {response.text[:300]}"
    return response.json()


@pytest.mark.e2e_writes
class TestResumeWrites:
    """The resume domain: create a certification, read it back, delete it."""

    def test_certification_round_trip(self, api: Any, e2e_env: Any, created_resources: list[Any]) -> None:
        """A certification survives a create, a read by id and a delete.

        Certifications are the cleanest of the five resume collections: a create needs no
        reference to another row, and the delete is reachable without one.
        """
        name = f"{e2e_env.resource_prefix}certification"
        payload = {
            "name": name,
            "issuer": f"{e2e_env.resource_prefix}issuer",
            "issued_date": "2024-01-01",
            "order": 0,
        }

        body = _created(api.post("/api/v1/certifications", json=payload), "/api/v1/certifications")
        identifier = body["id"]
        created_resources.append((CREATED_CERTIFICATION, identifier))
        assert body["name"] == name

        read = api.get(f"/api/v1/certifications/{identifier}")
        assert read.status_code == 200, f"the certification just created read back {read.status_code}"
        assert read.json()["name"] == name

        deleted = api.delete(f"/api/v1/certifications/{identifier}")
        assert deleted.status_code in (200, 204), f"delete answered {deleted.status_code}"

        listed = api.get("/api/v1/certifications")
        assert listed.status_code == 200
        assert not [row for row in listed.json() if row.get("id") == identifier], (
            "the deleted certification is still listed. The delete is a soft delete, so "
            "the row remains, but it must drop out of the collection."
        )


@pytest.mark.e2e_writes
class TestContentWrites:
    """The content domain: a category, a post inside it, and the site content singleton."""

    def test_category_round_trip(self, api: Any, e2e_env: Any, created_resources: list[Any]) -> None:
        """A category survives a create, a read through the listing and a delete."""
        name = f"{e2e_env.resource_prefix}category"
        body = _created(
            api.post("/api/v1/posts/categories", json={"name": name}),
            "/api/v1/posts/categories",
        )
        identifier = body["id"]
        created_resources.append((CREATED_CATEGORY, identifier))

        listed = api.get("/api/v1/posts/categories")
        assert listed.status_code == 200
        assert [row for row in listed.json() if row.get("id") == identifier], (
            "the category just created is absent from the listing"
        )

        deleted = api.delete(f"/api/v1/posts/categories/{identifier}")
        assert deleted.status_code in (200, 204), f"delete answered {deleted.status_code}"

    def test_post_round_trip(self, api: Any, e2e_env: Any, created_resources: list[Any]) -> None:
        """A post survives a create, a read through the admin listing and a delete.

        Read back through the admin listing rather than `GET /api/v1/posts/{slug}`,
        which serves published posts only and would 404 a fresh draft.
        """
        title = f"{e2e_env.resource_prefix}post"
        body = _created(
            api.post("/api/v1/posts/admin", json={"title": title, "content": "Created by the e2e suite."}),
            "/api/v1/posts/admin",
        )
        identifier = body["id"]
        created_resources.append((CREATED_POST, identifier))

        listed = api.get("/api/v1/posts/admin")
        assert listed.status_code == 200
        rows = listed.json()
        rows = rows if isinstance(rows, list) else rows.get("items", [])
        assert [row for row in rows if row.get("id") == identifier], (
            "the post just created is absent from the admin listing"
        )

        deleted = api.delete(f"/api/v1/posts/admin/{identifier}")
        assert deleted.status_code in (200, 204), f"delete answered {deleted.status_code}"

    def test_site_content_write_restores_what_it_read(self, api: Any, e2e_env: Any) -> None:
        """The site content singleton accepts a write and keeps it.

        A singleton with no create and no delete, so the round trip is read, write a
        prefixed value, read it back and put the original value back. The restore runs
        even when the assertion fails, so a red run does not leave the site altered.
        """
        original = api.get("/api/v1/site-content")
        assert original.status_code == 200, f"site content read answered {original.status_code}"
        before = original.json()
        tagline = before.get("footer_tagline")

        written = f"{e2e_env.resource_prefix}tagline"
        try:
            update = api.request("PUT", "/api/v1/site-content", json={"footer_tagline": written})
            assert update.status_code == 200, f"site content write answered {update.status_code}"

            read = api.get("/api/v1/site-content")
            assert read.status_code == 200
            assert read.json().get("footer_tagline") == written, "the site content write did not persist"
        finally:
            api.request("PUT", "/api/v1/site-content", json={"footer_tagline": tagline})


class TestReadOnlyDomains:
    """The two domains that declare no writes, proven to be served by their own function."""

    def test_public_root_and_health_are_served(self, anon: Any) -> None:
        """The public domain answers its two routes without a credential."""
        for path in ("/", "/health"):
            response = anon.get(path)
            assert response.status_code == 200, f"GET {path} answered {response.status_code}"

    def test_identity_login_route_is_reachable(self, anon: Any) -> None:
        """The legacy admin login route is routed rather than answered by the gateway.

        Sent deliberately empty, so the answer is the application's own validation
        refusal. A 404 here would mean the route key is missing and the request reached
        no function at all, which is the failure this whole suite exists to catch.
        """
        response = anon.request("POST", "/api/v1/admin/login", json={}, retry_on_429=False)
        assert response.status_code in (400, 401, 422, 429), (
            f"POST /api/v1/admin/login answered {response.status_code}, which suggests the "
            "request never reached the identity function"
        )
