"""
Tests for the projects API endpoints
"""

import pytest
from fastapi.testclient import TestClient


class TestProjectsAPI:
    """Test class for projects API endpoints"""

    @pytest.mark.api
    def test_get_projects_public(self, client: TestClient, test_project):
        """Test getting all active projects (public endpoint)"""
        response = client.get("/api/v1/projects/")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["title"] == "Test Project"
        assert data[0]["description"] == "A test project description"

    @pytest.mark.api
    def test_get_projects_with_pagination(self, client: TestClient, test_project):
        """Test getting projects with pagination"""
        response = client.get("/api/v1/projects/?skip=0&limit=10")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) <= 10

    @pytest.mark.api
    def test_get_projects_featured_only(self, client: TestClient, test_project):
        """Test getting only featured projects"""
        response = client.get("/api/v1/projects/?featured_only=true")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        if data:
            assert all(project["featured"] for project in data)

    @pytest.mark.api
    def test_get_single_project(self, client: TestClient, test_project):
        """Test getting a single project by ID"""
        response = client.get(f"/api/v1/projects/{test_project["id"]}")
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == test_project["title"]
        assert data["description"] == test_project["description"]
        assert data["technologies"] == test_project["technologies"]
        assert data["github_url"] == test_project["github_url"]
        assert data["live_url"] == test_project["live_url"]

    @pytest.mark.api
    def test_get_nonexistent_project(self, client: TestClient):
        """Test getting a project that doesn't exist"""
        response = client.get("/api/v1/projects/999")
        assert response.status_code == 404
        assert "Project not found" in response.json()["detail"]

    @pytest.mark.api
    def test_get_inactive_project_fails(self, client: TestClient):
        """Test that inactive projects are not accessible via public endpoint"""
        # Create an inactive project
        from app.db.entities import projects

        inactive_project = projects.create(
            {
                "title": "Inactive Project",
                "description": "An inactive project",
                "technologies": ["Python"],
                "github_url": "https://github.com/test/inactive",
                "live_url": "https://inactive-project.com",
                "is_active": False,
            }
        )

        response = client.get(f"/api/v1/projects/{inactive_project['id']}")
        assert response.status_code == 404
        assert "Project not found" in response.json()["detail"]


class TestProjectsAdminAPI:
    """Test class for admin-only projects API endpoints"""

    @pytest.mark.api
    @pytest.mark.auth
    def test_create_project_admin(
        self, client: TestClient, admin_auth_headers, sample_project_data
    ):
        """Test creating a new project as admin"""
        response = client.post(
            "/api/v1/projects/", json=sample_project_data, headers=admin_auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == sample_project_data["title"]
        assert data["description"] == sample_project_data["description"]
        assert data["technologies"] == sample_project_data["technologies"]
        assert data["github_url"] == sample_project_data["github_url"]
        assert data["live_url"] == sample_project_data["live_url"]
        assert data["featured"] == sample_project_data["featured"]

    @pytest.mark.api
    @pytest.mark.auth
    def test_create_project_unauthorized(
        self, client: TestClient, auth_headers, sample_project_data
    ):
        """Test creating a project without admin privileges"""
        response = client.post(
            "/api/v1/projects/", json=sample_project_data, headers=auth_headers
        )
        assert response.status_code == 403
        assert "Not enough permissions" in response.json()["detail"]

    @pytest.mark.api
    @pytest.mark.auth
    def test_create_project_no_auth(self, client: TestClient, sample_project_data):
        """Test creating a project without authentication"""
        response = client.post("/api/v1/projects/", json=sample_project_data)
        assert response.status_code == 403

    @pytest.mark.api
    @pytest.mark.auth
    def test_update_project_admin(
        self, client: TestClient, admin_auth_headers, test_project
    ):
        """Test updating a project as admin"""
        update_data = {
            "title": "Updated Test Project",
            "description": "Updated project description",
            "technologies": ["Python", "FastAPI", "React", "TypeScript"],
        }
        response = client.put(
            f"/api/v1/projects/{test_project["id"]}",
            json=update_data,
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == update_data["title"]
        assert data["description"] == update_data["description"]
        assert data["technologies"] == update_data["technologies"]

    @pytest.mark.api
    @pytest.mark.auth
    def test_update_project_unauthorized(
        self, client: TestClient, auth_headers, test_project
    ):
        """Test updating a project without admin privileges"""
        update_data = {"title": "Updated Title"}
        response = client.put(
            f"/api/v1/projects/{test_project["id"]}",
            json=update_data,
            headers=auth_headers,
        )
        assert response.status_code == 403
        assert "Not enough permissions" in response.json()["detail"]

    @pytest.mark.api
    @pytest.mark.auth
    def test_update_nonexistent_project(self, client: TestClient, admin_auth_headers):
        """Test updating a project that doesn't exist"""
        update_data = {"title": "Updated Title"}
        response = client.put(
            "/api/v1/projects/999", json=update_data, headers=admin_auth_headers
        )
        assert response.status_code == 404
        assert "Project not found" in response.json()["detail"]

    @pytest.mark.api
    @pytest.mark.auth
    def test_delete_project_admin(
        self, client: TestClient, admin_auth_headers, test_project
    ):
        """Test soft deleting a project as admin"""
        response = client.delete(
            f"/api/v1/projects/{test_project["id"]}", headers=admin_auth_headers
        )
        assert response.status_code == 200
        assert "deleted successfully" in response.json()["message"]

        # Verify project is no longer accessible via public endpoint
        get_response = client.get(f"/api/v1/projects/{test_project["id"]}")
        assert get_response.status_code == 404

    @pytest.mark.api
    @pytest.mark.auth
    def test_delete_project_unauthorized(
        self, client: TestClient, auth_headers, test_project
    ):
        """Test deleting a project without admin privileges"""
        response = client.delete(
            f"/api/v1/projects/{test_project["id"]}", headers=auth_headers
        )
        assert response.status_code == 403
        assert "Not enough permissions" in response.json()["detail"]

    @pytest.mark.api
    @pytest.mark.auth
    def test_delete_nonexistent_project(self, client: TestClient, admin_auth_headers):
        """Test deleting a project that doesn't exist"""
        response = client.delete("/api/v1/projects/999", headers=admin_auth_headers)
        assert response.status_code == 404
        assert "Project not found" in response.json()["detail"]


class TestProjectsAPIValidation:
    """Test class for API validation and edge cases"""

    @pytest.mark.api
    def test_get_projects_invalid_pagination(self, client: TestClient):
        """Test getting projects with invalid pagination parameters"""
        response = client.get("/api/v1/projects/?skip=-1")
        assert response.status_code == 422

        response = client.get("/api/v1/projects/?limit=0")
        assert response.status_code == 422

        response = client.get("/api/v1/projects/?limit=101")
        assert response.status_code == 422

    @pytest.mark.api
    @pytest.mark.auth
    def test_create_project_invalid_data(self, client: TestClient, admin_auth_headers):
        """Test creating a project with invalid data"""
        # Missing required fields
        response = client.post("/api/v1/projects/", json={}, headers=admin_auth_headers)
        assert response.status_code == 422

        # Invalid URL format (should still work since it's just a string)
        project_data = {
            "title": "Test Project",
            "description": "Test description",
            "github_url": "invalid-url",
        }
        response = client.post(
            "/api/v1/projects/", json=project_data, headers=admin_auth_headers
        )
        assert response.status_code == 200  # URL validation is not enforced in schema

    @pytest.mark.api
    @pytest.mark.auth
    def test_create_project_minimal_data(self, client: TestClient, admin_auth_headers):
        """Test creating a project with minimal required data"""
        project_data = {
            "title": "Minimal Project",
            "description": "A minimal project description",
        }
        response = client.post(
            "/api/v1/projects/", json=project_data, headers=admin_auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == project_data["title"]
        assert data["description"] == project_data["description"]
        assert data["technologies"] == []  # Should default to empty list
        assert data["featured"] is False


class TestProjectsAPIPerformance:
    """Test class for performance-related scenarios"""

    @pytest.mark.api
    @pytest.mark.slow
    def test_get_projects_large_dataset(self, client: TestClient):
        """Test getting projects with a large dataset"""
        # Create multiple test projects
        from app.db.entities import projects

        for i in range(25):
            projects.create(
                {
                    "title": f"Test Project {i}",
                    "description": f"Description for project {i}",
                    "technologies": ["Python", "FastAPI"],
                    "github_url": f"https://github.com/test/project-{i}",
                    "featured": (i % 3 == 0),
                }
            )

        # Test pagination with large dataset
        response = client.get("/api/v1/projects/?skip=0&limit=10")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 10

        # Test getting featured projects only
        response = client.get("/api/v1/projects/?featured_only=true")
        assert response.status_code == 200
        data = response.json()
        assert all(project["featured"] for project in data)
