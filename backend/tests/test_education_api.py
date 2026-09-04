"""
Tests for the education API endpoints
"""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient


class TestEducationAPI:
    @pytest.mark.api
    def test_get_education_public(self, client: TestClient, test_education):
        response = client.get("/api/v1/education/")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["degree"] == "Test Degree"

    @pytest.mark.api
    def test_get_single_education(self, client: TestClient, test_education):
        response = client.get(f"/api/v1/education/{test_education["id"]}")
        assert response.status_code == 200
        data = response.json()
        assert data["school"] == test_education["school"]

    @pytest.mark.api
    def test_get_nonexistent_education(self, client: TestClient):
        response = client.get("/api/v1/education/999")
        assert response.status_code == 404

    @pytest.mark.api
    def test_inactive_education_hidden(self, client: TestClient):
        from app.db.entities import education

        inactive = education.create(
            {
                "degree": "Hidden",
                "school": "X",
                "location": "Y",
                "period": "Z",
                "start_date": datetime(2020, 1, 1).date(),
                "order": 10,
                "is_active": False,
            }
        )
        response = client.get(f"/api/v1/education/{inactive['id']}")
        assert response.status_code == 404


class TestEducationAdminAPI:
    @pytest.mark.api
    @pytest.mark.auth
    def test_create_education_admin(
        self, client: TestClient, admin_auth_headers, sample_education_data
    ):
        response = client.post(
            "/api/v1/education/",
            json=sample_education_data,
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["degree"] == sample_education_data["degree"]
        assert data["end_date"] == sample_education_data["end_date"]

    @pytest.mark.api
    @pytest.mark.auth
    def test_create_education_unauthorized(
        self, client: TestClient, auth_headers, sample_education_data
    ):
        response = client.post(
            "/api/v1/education/", json=sample_education_data, headers=auth_headers
        )
        assert response.status_code == 403

    @pytest.mark.api
    @pytest.mark.auth
    def test_create_education_no_auth(self, client: TestClient, sample_education_data):
        response = client.post("/api/v1/education/", json=sample_education_data)
        assert response.status_code == 403

    @pytest.mark.api
    @pytest.mark.auth
    def test_update_education_admin(
        self, client: TestClient, admin_auth_headers, test_education
    ):
        response = client.put(
            f"/api/v1/education/{test_education["id"]}",
            json={"degree": "Updated Degree"},
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["degree"] == "Updated Degree"

    @pytest.mark.api
    @pytest.mark.auth
    def test_delete_education_admin(
        self, client: TestClient, admin_auth_headers, test_education
    ):
        response = client.delete(
            f"/api/v1/education/{test_education["id"]}", headers=admin_auth_headers
        )
        assert response.status_code == 200
        get_response = client.get(f"/api/v1/education/{test_education["id"]}")
        assert get_response.status_code == 404


class TestEducationAPIValidation:
    @pytest.mark.api
    @pytest.mark.auth
    def test_create_education_minimal(self, client: TestClient, admin_auth_headers):
        response = client.post(
            "/api/v1/education/",
            json={
                "degree": "Minimal",
                "school": "U",
                "location": "L",
                "period": "P",
                "start_date": "2020-01-01",
            },
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["end_date"] is None
        assert data["description"] is None
        assert data["order"] == 0
