"""
Tests for the certifications API endpoints
"""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient


class TestCertificationsAPI:
    @pytest.mark.api
    def test_get_certifications_public(self, client: TestClient, test_certification):
        response = client.get("/api/v1/certifications/")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["name"] == "Test Cert"

    @pytest.mark.api
    def test_certifications_ordering(self, client: TestClient):
        from app.db.entities import certifications

        for name, year, order in (("A", 2020, 20), ("B", 2023, 10), ("C", 2022, 10)):
            certifications.create(
                {
                    "name": name,
                    "issuer": "X",
                    "issued_date": datetime(year, 1, 1).date(),
                    "order": order,
                }
            )
        response = client.get("/api/v1/certifications/")
        assert response.status_code == 200
        data = response.json()
        # order asc, then issued_date desc
        assert [c["name"] for c in data] == ["B", "C", "A"]

    @pytest.mark.api
    def test_get_single_certification(self, client: TestClient, test_certification):
        response = client.get(f"/api/v1/certifications/{test_certification["id"]}")
        assert response.status_code == 200
        assert response.json()["name"] == test_certification["name"]

    @pytest.mark.api
    def test_get_nonexistent_certification(self, client: TestClient):
        response = client.get("/api/v1/certifications/999")
        assert response.status_code == 404


class TestCertificationsAdminAPI:
    @pytest.mark.api
    @pytest.mark.auth
    def test_create_certification_admin(
        self, client: TestClient, admin_auth_headers, sample_certification_data
    ):
        response = client.post(
            "/api/v1/certifications/",
            json=sample_certification_data,
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == sample_certification_data["name"]
        assert data["credential_url"] == sample_certification_data["credential_url"]

    @pytest.mark.api
    @pytest.mark.auth
    def test_create_certification_unauthorized(
        self, client: TestClient, auth_headers, sample_certification_data
    ):
        response = client.post(
            "/api/v1/certifications/",
            json=sample_certification_data,
            headers=auth_headers,
        )
        assert response.status_code == 403

    @pytest.mark.api
    @pytest.mark.auth
    def test_update_certification_admin(
        self, client: TestClient, admin_auth_headers, test_certification
    ):
        response = client.put(
            f"/api/v1/certifications/{test_certification["id"]}",
            json={"name": "Renamed Cert"},
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Renamed Cert"

    @pytest.mark.api
    @pytest.mark.auth
    def test_delete_certification_admin(
        self, client: TestClient, admin_auth_headers, test_certification
    ):
        response = client.delete(
            f"/api/v1/certifications/{test_certification["id"]}",
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        get_response = client.get(f"/api/v1/certifications/{test_certification["id"]}")
        assert get_response.status_code == 404


class TestCertificationsAPIValidation:
    @pytest.mark.api
    @pytest.mark.auth
    def test_create_certification_minimal(self, client: TestClient, admin_auth_headers):
        response = client.post(
            "/api/v1/certifications/",
            json={
                "name": "Minimal",
                "issuer": "X",
                "issued_date": "2024-01-01",
            },
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["credential_url"] is None
        assert data["order"] == 0
