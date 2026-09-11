"""
Tests for the site content singleton API.
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.db import entities
from app.domains.content.defaults import SITE_CONTENT_DEFAULTS
from app.domains.content.service import (
    ensure_site_content_seeded,
    reset_seed_state,
    seed_site_content,
)


class TestSiteContentSeeding:
    """Seeding the site content singleton."""

    @pytest.mark.admin
    def test_seeds_defaults_when_absent(self):
        """Seeding an empty table writes the defaults."""
        assert entities.site_content.get(entities.SITE_CONTENT_ID) is None
        seed_site_content()
        content = entities.site_content.get(entities.SITE_CONTENT_ID)
        assert content["hero_title"] == SITE_CONTENT_DEFAULTS["hero_title"]
        assert content["github_url"] == "https://github.com/TW-WebbPulse"
        assert content["resume_url"] == "/Profile.pdf"
        assert content["project_sort_mode"] == "manual"
        assert len(content["about_values"]) == 3
        assert content["created_at"]

    @pytest.mark.admin
    def test_does_not_overwrite_existing_content(self, test_site_content):
        """Seeding leaves an existing row untouched."""
        seed_site_content()
        reset_seed_state()
        ensure_site_content_seeded()
        content = entities.site_content.get(entities.SITE_CONTENT_ID)
        assert content["hero_title"] == "Hi, I'm Test"
        assert content["about_paragraphs"] == ["Paragraph one", "Paragraph two"]
        assert entities.site_content.count() == 1

    @pytest.mark.admin
    def test_lost_race_keeps_existing_content(self, test_site_content):
        """Losing the seed race keeps the row the winner wrote."""
        with patch.object(
            entities.site_content, "get", side_effect=[None, test_site_content]
        ):
            seed_site_content()
        content = entities.site_content.get(entities.SITE_CONTENT_ID)
        assert content["hero_title"] == "Hi, I'm Test"

    @pytest.mark.admin
    def test_seeding_is_idempotent(self):
        """Repeated seeding still leaves exactly one row."""
        seed_site_content()
        seed_site_content()
        ensure_site_content_seeded()
        assert entities.site_content.count() == 1

    @pytest.mark.api
    def test_first_request_seeds_site_content(self, client: TestClient):
        """The first public read seeds the singleton and returns it."""
        assert entities.site_content.get(entities.SITE_CONTENT_ID) is None
        response = client.get("/api/v1/site-content/")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == entities.SITE_CONTENT_ID
        assert data["hero_title"] == SITE_CONTENT_DEFAULTS["hero_title"]
        assert data["email"] == "tyler@webbpulse.com"
        assert data["footer_tagline"] == SITE_CONTENT_DEFAULTS["footer_tagline"]


class TestSiteContentAPI:
    """The public site content endpoint."""

    @pytest.mark.api
    def test_get_site_content(self, client: TestClient, test_site_content):
        """The public read returns the singleton with its list fields."""
        response = client.get("/api/v1/site-content/")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["hero_title"] == "Hi, I'm Test"
        assert isinstance(data["about_paragraphs"], list)
        assert len(data["about_paragraphs"]) == 2
        assert isinstance(data["about_values"], list)
        assert data["about_values"][0]["title"] == "Test Value"

    @pytest.mark.api
    def test_get_site_content_uninitialized(self, client: TestClient):
        """If the singleton row is missing after seeding, return 500."""
        client.get("/health")
        entities.site_content.hard_delete(entities.SITE_CONTENT_ID)
        response = client.get("/api/v1/site-content/")
        assert response.status_code == 500


class TestSiteContentAdminAPI:
    """The admin-only site content endpoint."""

    @pytest.mark.api
    @pytest.mark.auth
    def test_update_site_content_admin(
        self, client: TestClient, admin_auth_headers, test_site_content
    ):
        """An admin can update a field, leaving the others alone."""
        response = client.put(
            "/api/v1/site-content/",
            json={"hero_title": "Updated Title"},
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["hero_title"] == "Updated Title"
        assert data["hero_subtitle"] == "Test Subtitle"

    @pytest.mark.api
    @pytest.mark.auth
    def test_update_site_content_replaces_arrays(
        self, client: TestClient, admin_auth_headers, test_site_content
    ):
        """List fields are replaced wholesale rather than merged."""
        new_paragraphs = ["Only one paragraph now."]
        new_values = [
            {"title": "New", "description": "Replaced wholesale", "icon": "🔥"},
        ]
        response = client.put(
            "/api/v1/site-content/",
            json={
                "about_paragraphs": new_paragraphs,
                "about_values": new_values,
            },
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["about_paragraphs"] == new_paragraphs
        assert len(data["about_values"]) == 1
        assert data["about_values"][0]["title"] == "New"

    @pytest.mark.api
    @pytest.mark.auth
    def test_update_site_content_unauthorized(
        self, client: TestClient, auth_headers, test_site_content
    ):
        """A non-admin user cannot update site content."""
        response = client.put(
            "/api/v1/site-content/",
            json={"hero_title": "X"},
            headers=auth_headers,
        )
        assert response.status_code == 403

    @pytest.mark.api
    @pytest.mark.auth
    def test_update_site_content_no_auth(self, client: TestClient, test_site_content):
        """Updating site content without credentials is refused."""
        response = client.put("/api/v1/site-content/", json={"hero_title": "X"})
        assert response.status_code == 403

    @pytest.mark.api
    @pytest.mark.auth
    def test_update_site_content_uninitialized(
        self, client: TestClient, admin_auth_headers
    ):
        """PUT without a seeded row should fail."""
        client.get("/health")
        entities.site_content.hard_delete(entities.SITE_CONTENT_ID)
        response = client.put(
            "/api/v1/site-content/",
            json={"hero_title": "X"},
            headers=admin_auth_headers,
        )
        assert response.status_code == 500
