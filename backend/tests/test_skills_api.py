"""
Tests for the skills API endpoints
"""

import pytest
from fastapi.testclient import TestClient


class TestSkillsAPI:
    """Test class for skills API endpoints"""

    @pytest.mark.api
    def test_get_skills_public(self, client: TestClient, test_skill):
        """Test getting all active skills (public endpoint)"""
        response = client.get("/api/v1/skills/")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["name"] == "Test Skill"
        assert data[0]["category"] == "frontend"
        assert data[0]["tier"] == "working"

    @pytest.mark.api
    def test_get_skills_ordering(self, client: TestClient):
        """Skills should be ordered by (order asc, name asc)."""
        from app.db.entities import skills

        for name, order in (("Zeta", 10), ("Alpha", 20), ("Beta", 10)):
            skills.create(
                {
                    "name": name,
                    "category": "frontend",
                    "tier": "working",
                    "order": order,
                }
            )

        response = client.get("/api/v1/skills/")
        assert response.status_code == 200
        data = response.json()
        names = [s["name"] for s in data]
        assert names == ["Beta", "Zeta", "Alpha"]

    @pytest.mark.api
    def test_get_single_skill(self, client: TestClient, test_skill):
        """Test getting a single skill by ID"""
        response = client.get(f"/api/v1/skills/{test_skill["id"]}")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == test_skill["name"]
        assert data["category"] == test_skill["category"]

    @pytest.mark.api
    def test_get_nonexistent_skill(self, client: TestClient):
        response = client.get("/api/v1/skills/999")
        assert response.status_code == 404
        assert "Skill not found" in response.json()["detail"]

    @pytest.mark.api
    def test_inactive_skill_hidden(self, client: TestClient):
        from app.db.entities import skills

        inactive = skills.create(
            {
                "name": "Hidden",
                "category": "frontend",
                "tier": "working",
                "order": 10,
                "is_active": False,
            }
        )
        response = client.get(f"/api/v1/skills/{inactive['id']}")
        assert response.status_code == 404


class TestSkillsAdminAPI:
    """Test class for admin-only skills API endpoints"""

    @pytest.mark.api
    @pytest.mark.auth
    def test_create_skill_admin(
        self, client: TestClient, admin_auth_headers, sample_skill_data
    ):
        response = client.post(
            "/api/v1/skills/",
            json=sample_skill_data,
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == sample_skill_data["name"]
        assert data["category"] == sample_skill_data["category"]
        assert data["tier"] == sample_skill_data["tier"]

    @pytest.mark.api
    @pytest.mark.auth
    def test_create_skill_unauthorized(
        self, client: TestClient, auth_headers, sample_skill_data
    ):
        response = client.post(
            "/api/v1/skills/", json=sample_skill_data, headers=auth_headers
        )
        assert response.status_code == 403

    @pytest.mark.api
    @pytest.mark.auth
    def test_create_skill_no_auth(self, client: TestClient, sample_skill_data):
        response = client.post("/api/v1/skills/", json=sample_skill_data)
        assert response.status_code == 403

    @pytest.mark.api
    @pytest.mark.auth
    def test_create_skill_invalid_category(
        self, client: TestClient, admin_auth_headers
    ):
        response = client.post(
            "/api/v1/skills/",
            json={"name": "Bad", "category": "nope", "tier": "working"},
            headers=admin_auth_headers,
        )
        assert response.status_code == 422

    @pytest.mark.api
    @pytest.mark.auth
    def test_create_skill_invalid_tier(self, client: TestClient, admin_auth_headers):
        response = client.post(
            "/api/v1/skills/",
            json={"name": "Bad", "category": "frontend", "tier": "expert"},
            headers=admin_auth_headers,
        )
        assert response.status_code == 422

    @pytest.mark.api
    @pytest.mark.auth
    def test_update_skill_admin(
        self, client: TestClient, admin_auth_headers, test_skill
    ):
        response = client.put(
            f"/api/v1/skills/{test_skill["id"]}",
            json={"name": "Renamed", "tier": "core"},
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Renamed"
        assert data["tier"] == "core"
        # Untouched field preserved
        assert data["category"] == "frontend"

    @pytest.mark.api
    @pytest.mark.auth
    def test_update_skill_unauthorized(
        self, client: TestClient, auth_headers, test_skill
    ):
        response = client.put(
            f"/api/v1/skills/{test_skill["id"]}",
            json={"name": "X"},
            headers=auth_headers,
        )
        assert response.status_code == 403

    @pytest.mark.api
    @pytest.mark.auth
    def test_update_nonexistent_skill(self, client: TestClient, admin_auth_headers):
        response = client.put(
            "/api/v1/skills/999",
            json={"name": "X"},
            headers=admin_auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.api
    @pytest.mark.auth
    def test_delete_skill_admin(
        self, client: TestClient, admin_auth_headers, test_skill
    ):
        response = client.delete(
            f"/api/v1/skills/{test_skill["id"]}", headers=admin_auth_headers
        )
        assert response.status_code == 200
        assert "deleted successfully" in response.json()["message"]

        # Soft delete: GET returns 404
        get_response = client.get(f"/api/v1/skills/{test_skill["id"]}")
        assert get_response.status_code == 404

    @pytest.mark.api
    @pytest.mark.auth
    def test_delete_skill_unauthorized(
        self, client: TestClient, auth_headers, test_skill
    ):
        response = client.delete(
            f"/api/v1/skills/{test_skill["id"]}", headers=auth_headers
        )
        assert response.status_code == 403

    @pytest.mark.api
    @pytest.mark.auth
    def test_delete_nonexistent_skill(self, client: TestClient, admin_auth_headers):
        response = client.delete("/api/v1/skills/999", headers=admin_auth_headers)
        assert response.status_code == 404


class TestSkillsAPIValidation:
    """Test class for API validation and edge cases"""

    @pytest.mark.api
    def test_get_skills_invalid_pagination(self, client: TestClient):
        response = client.get("/api/v1/skills/?skip=-1")
        assert response.status_code == 422

        response = client.get("/api/v1/skills/?limit=0")
        assert response.status_code == 422

        response = client.get("/api/v1/skills/?limit=201")
        assert response.status_code == 422

    @pytest.mark.api
    @pytest.mark.auth
    def test_create_skill_minimal(self, client: TestClient, admin_auth_headers):
        response = client.post(
            "/api/v1/skills/",
            json={"name": "Minimal", "category": "other"},
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Minimal"
        assert data["tier"] == "working"  # default
        assert data["order"] == 0  # default
        assert data["icon"] is None
