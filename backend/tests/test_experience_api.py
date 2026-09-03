"""
Tests for the experience API endpoints
"""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient


class TestExperienceAPI:
    """Test class for experience API endpoints"""

    @pytest.mark.api
    def test_get_experience_public(self, client: TestClient, test_experience):
        """Test getting all active experience entries (public endpoint)"""
        response = client.get("/api/v1/experience/")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["title"] == "Test Position"
        assert data[0]["company"] == "Test Company"

    @pytest.mark.api
    def test_get_experience_with_pagination(self, client: TestClient, test_experience):
        """Test getting experience entries with pagination"""
        response = client.get("/api/v1/experience/?skip=0&limit=10")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) <= 10

    @pytest.mark.api
    def test_get_single_experience(self, client: TestClient, test_experience):
        """Test getting a single experience entry by ID"""
        response = client.get(f"/api/v1/experience/{test_experience["id"]}")
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == test_experience["title"]
        assert data["company"] == test_experience["company"]
        assert data["location"] == test_experience["location"]
        assert data["technologies"] == test_experience["technologies"]
        # Check that end_date matches (it will be a string in the response)
        assert data["end_date"] == "2023-12-31"

    @pytest.mark.api
    def test_get_nonexistent_experience(self, client: TestClient):
        """Test getting an experience entry that doesn't exist"""
        response = client.get("/api/v1/experience/999")
        assert response.status_code == 404
        assert "Experience entry not found" in response.json()["detail"]

    @pytest.mark.api
    def test_get_inactive_experience_fails(self, client: TestClient):
        """Inactive experience entries are not accessible via public endpoint"""
        # Create an inactive experience entry
        from app.db.entities import experience

        inactive_experience = experience.create(
            {
                "title": "Inactive Position",
                "company": "Inactive Company",
                "location": "Inactive City, State",
                "period": "Jan 2020 - Dec 2021",
                "start_date": datetime(2020, 1, 1).date(),
                "end_date": datetime(2021, 12, 31).date(),
                "description": "An inactive experience entry",
                "technologies": ["Python"],
                "achievements": [],
                "is_active": False,
            }
        )

        response = client.get(f"/api/v1/experience/{inactive_experience['id']}")
        assert response.status_code == 404
        assert "Experience entry not found" in response.json()["detail"]


class TestExperienceAdminAPI:
    """Test class for admin-only experience API endpoints"""

    @pytest.mark.api
    @pytest.mark.auth
    def test_create_experience_admin(
        self, client: TestClient, admin_auth_headers, sample_experience_data
    ):
        """Test creating a new experience entry as admin"""
        response = client.post(
            "/api/v1/experience/",
            json=sample_experience_data,
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == sample_experience_data["title"]
        assert data["company"] == sample_experience_data["company"]
        assert data["location"] == sample_experience_data["location"]
        assert data["technologies"] == sample_experience_data["technologies"]
        assert data["end_date"] == sample_experience_data["end_date"]

    @pytest.mark.api
    @pytest.mark.auth
    def test_create_experience_unauthorized(
        self, client: TestClient, auth_headers, sample_experience_data
    ):
        """Test creating an experience entry without admin privileges"""
        response = client.post(
            "/api/v1/experience/", json=sample_experience_data, headers=auth_headers
        )
        assert response.status_code == 403
        assert "Not enough permissions" in response.json()["detail"]

    @pytest.mark.api
    @pytest.mark.auth
    def test_create_experience_no_auth(
        self, client: TestClient, sample_experience_data
    ):
        """Test creating an experience entry without authentication"""
        response = client.post("/api/v1/experience/", json=sample_experience_data)
        assert response.status_code == 403

    @pytest.mark.api
    @pytest.mark.auth
    def test_create_current_experience(self, client: TestClient, admin_auth_headers):
        """Test creating a current experience entry (no end date)"""
        current_experience_data = {
            "title": "Current Position",
            "company": "Current Company",
            "location": "Current City, State",
            "period": "Jan 2023 - Present",
            "start_date": "2023-01-01",
            "description": "A current position",
            "technologies": ["Python", "FastAPI"],
            "end_date": None,
        }
        response = client.post(
            "/api/v1/experience/",
            json=current_experience_data,
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["end_date"] is None

    @pytest.mark.api
    @pytest.mark.auth
    def test_update_experience_admin(
        self, client: TestClient, admin_auth_headers, test_experience
    ):
        """Test updating an experience entry as admin"""
        update_data = {
            "title": "Updated Test Position",
            "company": "Updated Test Company",
            "technologies": ["Python", "FastAPI", "React", "TypeScript"],
        }
        response = client.put(
            f"/api/v1/experience/{test_experience["id"]}",
            json=update_data,
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == update_data["title"]
        assert data["company"] == update_data["company"]
        assert data["technologies"] == update_data["technologies"]

    @pytest.mark.api
    @pytest.mark.auth
    def test_update_experience_unauthorized(
        self, client: TestClient, auth_headers, test_experience
    ):
        """Test updating an experience entry without admin privileges"""
        update_data = {"title": "Updated Title"}
        response = client.put(
            f"/api/v1/experience/{test_experience["id"]}",
            json=update_data,
            headers=auth_headers,
        )
        assert response.status_code == 403
        assert "Not enough permissions" in response.json()["detail"]

    @pytest.mark.api
    @pytest.mark.auth
    def test_update_nonexistent_experience(
        self, client: TestClient, admin_auth_headers
    ):
        """Test updating an experience entry that doesn't exist"""
        update_data = {"title": "Updated Title"}
        response = client.put(
            "/api/v1/experience/999", json=update_data, headers=admin_auth_headers
        )
        assert response.status_code == 404
        assert "Experience entry not found" in response.json()["detail"]

    @pytest.mark.api
    @pytest.mark.auth
    def test_delete_experience_admin(
        self, client: TestClient, admin_auth_headers, test_experience
    ):
        """Test soft deleting an experience entry as admin"""
        response = client.delete(
            f"/api/v1/experience/{test_experience["id"]}", headers=admin_auth_headers
        )
        assert response.status_code == 200
        assert "deleted successfully" in response.json()["message"]

        # Verify experience entry is no longer accessible via public endpoint
        get_response = client.get(f"/api/v1/experience/{test_experience["id"]}")
        assert get_response.status_code == 404

    @pytest.mark.api
    @pytest.mark.auth
    def test_delete_experience_unauthorized(
        self, client: TestClient, auth_headers, test_experience
    ):
        """Test deleting an experience entry without admin privileges"""
        response = client.delete(
            f"/api/v1/experience/{test_experience["id"]}", headers=auth_headers
        )
        assert response.status_code == 403
        assert "Not enough permissions" in response.json()["detail"]

    @pytest.mark.api
    @pytest.mark.auth
    def test_delete_nonexistent_experience(
        self, client: TestClient, admin_auth_headers
    ):
        """Test deleting an experience entry that doesn't exist"""
        response = client.delete("/api/v1/experience/999", headers=admin_auth_headers)
        assert response.status_code == 404
        assert "Experience entry not found" in response.json()["detail"]


class TestExperienceAPIValidation:
    """Test class for API validation and edge cases"""

    @pytest.mark.api
    def test_get_experience_invalid_pagination(self, client: TestClient):
        """Test getting experience entries with invalid pagination parameters"""
        response = client.get("/api/v1/experience/?skip=-1")
        assert response.status_code == 422

        response = client.get("/api/v1/experience/?limit=0")
        assert response.status_code == 422

        response = client.get("/api/v1/experience/?limit=101")
        assert response.status_code == 422

    @pytest.mark.api
    @pytest.mark.auth
    def test_create_experience_invalid_data(
        self, client: TestClient, admin_auth_headers
    ):
        """Test creating an experience entry with invalid data"""
        # Missing required fields
        response = client.post(
            "/api/v1/experience/", json={}, headers=admin_auth_headers
        )
        assert response.status_code == 422

        # Invalid date format
        experience_data = {
            "title": "Test Position",
            "company": "Test Company",
            "start_date": "invalid-date",
        }
        response = client.post(
            "/api/v1/experience/", json=experience_data, headers=admin_auth_headers
        )
        assert response.status_code == 422

        # End date before start date
        experience_data = {
            "title": "Test Position",
            "company": "Test Company",
            "start_date": "2023-01-01",
            "end_date": "2022-12-31",
        }
        response = client.post(
            "/api/v1/experience/", json=experience_data, headers=admin_auth_headers
        )
        assert response.status_code == 422

    @pytest.mark.api
    @pytest.mark.auth
    def test_create_experience_minimal_data(
        self, client: TestClient, admin_auth_headers
    ):
        """Test creating an experience entry with minimal required data"""
        experience_data = {
            "title": "Minimal Position",
            "company": "Minimal Company",
            "location": "Minimal City, State",
            "period": "Jan 2023 - Present",
            "start_date": "2023-01-01",
            "description": "A minimal position",
        }
        response = client.post(
            "/api/v1/experience/", json=experience_data, headers=admin_auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == experience_data["title"]
        assert data["company"] == experience_data["company"]
        assert data["technologies"] == []  # Should default to empty list
        assert data["end_date"] is None  # Should default to None for current positions

    @pytest.mark.api
    @pytest.mark.auth
    def test_update_experience_date_validation(
        self, client: TestClient, admin_auth_headers, test_experience
    ):
        """Test updating experience entry with date validation"""
        # Test setting end date
        update_data = {"end_date": "2024-12-31"}
        response = client.put(
            f"/api/v1/experience/{test_experience["id"]}",
            json=update_data,
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["end_date"] == "2024-12-31"

        # Test clearing end date (making it current)
        update_data = {"end_date": None}
        response = client.put(
            f"/api/v1/experience/{test_experience["id"]}",
            json=update_data,
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["end_date"] is None


class TestExperienceAPIPerformance:
    """Test class for performance-related scenarios"""

    @pytest.mark.api
    @pytest.mark.slow
    def test_get_experience_large_dataset(self, client: TestClient):
        """Test getting experience entries with a large dataset"""
        # Create multiple test experience entries
        from app.db.entities import experience

        for i in range(25):
            experience.create(
                {
                    "title": f"Test Position {i}",
                    "company": f"Test Company {i}",
                    "location": f"Test City {i}, State",
                    "period": f"Jan {2020 + i} - Dec {2021 + i}",
                    "start_date": datetime(2020 + i, 1, 1).date(),
                    "end_date": datetime(2021 + i, 12, 31).date(),
                    "description": f"Description for position {i}",
                    "technologies": ["Python", "FastAPI"],
                    "achievements": ["Achievement 1", "Achievement 2"],
                }
            )

        # Test pagination with large dataset
        response = client.get("/api/v1/experience/?skip=0&limit=10")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 10

        # Test ordering by start_date (should be descending)
        response = client.get("/api/v1/experience/?skip=0&limit=5")
        assert response.status_code == 200
        data = response.json()
        if len(data) > 1:
            # Check that dates are in descending order
            dates = [
                datetime.fromisoformat(exp["start_date"].replace("Z", "+00:00"))
                for exp in data
            ]
            assert dates == sorted(dates, reverse=True)
