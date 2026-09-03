"""
Tests for the posts API endpoints
"""

import pytest
from fastapi.testclient import TestClient


class TestPostsAPI:
    """Test class for posts API endpoints"""

    @pytest.mark.api
    def test_get_posts_public(self, client: TestClient, test_post):
        """Test getting published posts (public endpoint)"""
        response = client.get("/api/v1/posts/")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["title"] == "Test Post"
        assert data[0]["slug"] == "test-post"

    @pytest.mark.api
    def test_get_posts_with_pagination(self, client: TestClient, test_post):
        """Test getting posts with pagination"""
        response = client.get("/api/v1/posts/?skip=0&limit=5")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) <= 5

    @pytest.mark.api
    def test_get_posts_with_category_filter(
        self, client: TestClient, test_post, test_category
    ):
        """Test getting posts filtered by category"""
        response = client.get(f"/api/v1/posts/?category_slug={test_category["slug"]}")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        if data:
            assert data[0]["category"]["slug"] == test_category["slug"]

    @pytest.mark.api
    def test_get_posts_by_category_endpoint(
        self, client: TestClient, test_post, test_category
    ):
        """Test getting posts by category using dedicated endpoint"""
        response = client.get(f"/api/v1/posts/category/{test_category["slug"]}")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        if data:
            assert data[0]["category"]["slug"] == test_category["slug"]

    @pytest.mark.api
    def test_get_single_post(self, client: TestClient, test_post):
        """Test getting a single post by slug"""
        response = client.get(f"/api/v1/posts/{test_post["slug"]}")
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == test_post["title"]
        assert data["slug"] == test_post["slug"]
        assert data["content"] == test_post["content"]

    @pytest.mark.api
    def test_get_nonexistent_post(self, client: TestClient):
        """Test getting a post that doesn't exist"""
        response = client.get("/api/v1/posts/nonexistent-post")
        assert response.status_code == 404
        assert "Post not found" in response.json()["detail"]

    @pytest.mark.api
    def test_get_draft_post_public_fails(self, client: TestClient, test_draft_post):
        """Test that draft posts are not accessible via public endpoint"""
        response = client.get(f"/api/v1/posts/{test_draft_post["slug"]}")
        assert response.status_code == 404
        assert "Post not found" in response.json()["detail"]

    @pytest.mark.api
    def test_get_categories(self, client: TestClient, test_category):
        """Test getting all categories"""
        response = client.get("/api/v1/posts/categories")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["name"] == test_category["name"]
        assert data[0]["slug"] == test_category["slug"]


class TestPostsAdminAPI:
    """Test class for admin-only posts API endpoints"""

    @pytest.mark.api
    @pytest.mark.auth
    def test_get_all_posts_admin(
        self, client: TestClient, admin_auth_headers, test_post, test_draft_post
    ):
        """Test getting all posts (including drafts) as admin"""
        response = client.get("/api/v1/posts/admin", headers=admin_auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 2  # Both published and draft posts
        post_slugs = [post["slug"] for post in data]
        assert test_post["slug"] in post_slugs
        assert test_draft_post["slug"] in post_slugs

    @pytest.mark.api
    @pytest.mark.auth
    def test_get_all_posts_unauthorized(self, client: TestClient, auth_headers):
        """Test getting all posts without admin privileges"""
        response = client.get("/api/v1/posts/admin", headers=auth_headers)
        assert response.status_code == 403
        assert "Not enough permissions" in response.json()["detail"]

    @pytest.mark.api
    @pytest.mark.auth
    def test_get_all_posts_no_auth(self, client: TestClient):
        """Test getting all posts without authentication"""
        response = client.get("/api/v1/posts/admin")
        assert response.status_code == 403

    @pytest.mark.api
    @pytest.mark.auth
    def test_create_post_admin(
        self, client: TestClient, admin_auth_headers, test_category, sample_post_data
    ):
        """Test creating a new post as admin"""
        sample_post_data["category_id"] = test_category["id"]
        response = client.post(
            "/api/v1/posts/admin", json=sample_post_data, headers=admin_auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == sample_post_data["title"]
        assert data["slug"] == sample_post_data["slug"]
        assert data["content"] == sample_post_data["content"]
        assert data["category_id"] == test_category["id"]

    @pytest.mark.api
    @pytest.mark.auth
    def test_create_post_with_auto_slug(
        self, client: TestClient, admin_auth_headers, test_category
    ):
        """Test creating a post without providing a slug (should auto-generate)"""
        post_data = {
            "title": "Auto Slug Test Post",
            "content": "# Auto Slug Test\n\nThis post gets an auto-generated slug.",
            "excerpt": "Auto slug test excerpt",
            "read_time": "5 min read",
            "category_id": test_category["id"],
        }
        response = client.post(
            "/api/v1/posts/admin", json=post_data, headers=admin_auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["slug"] == "auto-slug-test-post"

    @pytest.mark.api
    @pytest.mark.auth
    def test_create_post_duplicate_slug(
        self, client: TestClient, admin_auth_headers, test_post, test_category
    ):
        """Test creating a post with a duplicate slug"""
        post_data = {
            "title": "Different Title",
            "slug": test_post["slug"],  # Use existing slug
            "content": "# Different Content",
            "excerpt": "Different excerpt",
            "read_time": "3 min read",
            "category_id": test_category["id"],
        }
        response = client.post(
            "/api/v1/posts/admin", json=post_data, headers=admin_auth_headers
        )
        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]

    @pytest.mark.api
    @pytest.mark.auth
    def test_create_post_unauthorized(
        self, client: TestClient, auth_headers, test_category, sample_post_data
    ):
        """Test creating a post without admin privileges"""
        sample_post_data["category_id"] = test_category["id"]
        response = client.post(
            "/api/v1/posts/admin", json=sample_post_data, headers=auth_headers
        )
        assert response.status_code == 403
        assert "Not enough permissions" in response.json()["detail"]

    @pytest.mark.api
    @pytest.mark.auth
    def test_update_post_admin(self, client: TestClient, admin_auth_headers, test_post):
        """Test updating a post as admin"""
        update_data = {
            "title": "Updated Test Post",
            "content": "# Updated Content\n\nThis is updated content.",
            "excerpt": "Updated excerpt",
        }
        response = client.put(
            f"/api/v1/posts/admin/{test_post["id"]}",
            json=update_data,
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == update_data["title"]
        assert data["content"] == update_data["content"]
        assert data["excerpt"] == update_data["excerpt"]

    @pytest.mark.api
    @pytest.mark.auth
    def test_update_nonexistent_post(self, client: TestClient, admin_auth_headers):
        """Test updating a post that doesn't exist"""
        update_data = {"title": "Updated Title"}
        response = client.put(
            "/api/v1/posts/admin/999", json=update_data, headers=admin_auth_headers
        )
        assert response.status_code == 404
        assert "Post not found" in response.json()["detail"]

    @pytest.mark.api
    @pytest.mark.auth
    def test_delete_post_admin(self, client: TestClient, admin_auth_headers, test_post):
        """Test deleting a post as admin"""
        response = client.delete(
            f"/api/v1/posts/admin/{test_post["id"]}", headers=admin_auth_headers
        )
        assert response.status_code == 200
        assert "deleted successfully" in response.json()["message"]

        # Verify post is deleted
        get_response = client.get(f"/api/v1/posts/{test_post["slug"]}")
        assert get_response.status_code == 404

    @pytest.mark.api
    @pytest.mark.auth
    def test_delete_nonexistent_post(self, client: TestClient, admin_auth_headers):
        """Test deleting a post that doesn't exist"""
        response = client.delete("/api/v1/posts/admin/999", headers=admin_auth_headers)
        assert response.status_code == 404
        assert "Post not found" in response.json()["detail"]

    @pytest.mark.api
    @pytest.mark.auth
    def test_publish_post_admin(
        self, client: TestClient, admin_auth_headers, test_draft_post
    ):
        """Test publishing a draft post as admin"""
        response = client.post(
            f"/api/v1/posts/admin/{test_draft_post["id"]}/publish",
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        assert "published successfully" in response.json()["message"]

        # Verify post is now published
        get_response = client.get(f"/api/v1/posts/{test_draft_post["slug"]}")
        assert get_response.status_code == 200

    @pytest.mark.api
    @pytest.mark.auth
    def test_publish_already_published_post(
        self, client: TestClient, admin_auth_headers, test_post
    ):
        """Test publishing a post that's already published"""
        response = client.post(
            f"/api/v1/posts/admin/{test_post["id"]}/publish", headers=admin_auth_headers
        )
        assert response.status_code == 400
        assert "already published" in response.json()["detail"]


class TestCategoriesAdminAPI:
    """Test class for admin-only categories API endpoints"""

    @pytest.mark.api
    @pytest.mark.auth
    def test_create_category_admin(
        self, client: TestClient, admin_auth_headers, sample_category_data
    ):
        """Test creating a new category as admin"""
        response = client.post(
            "/api/v1/posts/categories",
            json=sample_category_data,
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == sample_category_data["name"]
        assert data["slug"] == sample_category_data["slug"]

    @pytest.mark.api
    @pytest.mark.auth
    def test_create_category_with_auto_slug(
        self, client: TestClient, admin_auth_headers
    ):
        """Test creating a category without providing a slug (should auto-generate)"""
        category_data = {
            "name": "Auto Slug Category",
            "description": "A category with auto-generated slug",
        }
        response = client.post(
            "/api/v1/posts/categories", json=category_data, headers=admin_auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["slug"] == "auto-slug-category"

    @pytest.mark.api
    @pytest.mark.auth
    def test_create_category_duplicate_slug(
        self, client: TestClient, admin_auth_headers, test_category
    ):
        """Test creating a category with a duplicate slug"""
        category_data = {
            "name": "Different Name",
            "slug": test_category["slug"],  # Use existing slug
            "description": "Different description",
        }
        response = client.post(
            "/api/v1/posts/categories", json=category_data, headers=admin_auth_headers
        )
        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]

    @pytest.mark.api
    @pytest.mark.auth
    def test_update_category_admin(
        self, client: TestClient, admin_auth_headers, test_category
    ):
        """Test updating a category as admin"""
        update_data = {
            "name": "Updated Test Category",
            "description": "Updated category description",
        }
        response = client.put(
            f"/api/v1/posts/categories/{test_category["id"]}",
            json=update_data,
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == update_data["name"]
        assert data["description"] == update_data["description"]

    @pytest.mark.api
    @pytest.mark.auth
    def test_delete_category_admin(
        self, client: TestClient, admin_auth_headers, test_category
    ):
        """Test deleting a category as admin"""
        response = client.delete(
            f"/api/v1/posts/categories/{test_category["id"]}",
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        assert "deleted successfully" in response.json()["message"]

    @pytest.mark.api
    @pytest.mark.auth
    def test_delete_category_with_posts(
        self, client: TestClient, admin_auth_headers, test_category, test_post
    ):
        """Test deleting a category that has posts (should fail)"""
        response = client.delete(
            f"/api/v1/posts/categories/{test_category["id"]}",
            headers=admin_auth_headers,
        )
        assert response.status_code == 400
        assert "has posts" in response.json()["detail"]


class TestPostsAPIValidation:
    """Test class for API validation and edge cases"""

    @pytest.mark.api
    def test_get_posts_invalid_pagination(self, client: TestClient):
        """Test getting posts with invalid pagination parameters"""
        response = client.get("/api/v1/posts/?skip=-1")
        assert response.status_code == 422

        response = client.get("/api/v1/posts/?limit=0")
        assert response.status_code == 422

        response = client.get("/api/v1/posts/?limit=101")
        assert response.status_code == 422

    @pytest.mark.api
    @pytest.mark.auth
    def test_create_post_invalid_data(self, client: TestClient, admin_auth_headers):
        """Test creating a post with invalid data"""
        # Missing required fields
        response = client.post(
            "/api/v1/posts/admin", json={}, headers=admin_auth_headers
        )
        assert response.status_code == 422

        # Invalid read_time
        post_data = {"title": "Test Post", "content": "Test content", "read_time": -1}
        response = client.post(
            "/api/v1/posts/admin", json=post_data, headers=admin_auth_headers
        )
        assert response.status_code == 422

    @pytest.mark.api
    @pytest.mark.auth
    def test_create_post_invalid_category(self, client: TestClient, admin_auth_headers):
        """Test creating a post with non-existent category"""
        post_data = {
            "title": "Test Post",
            "content": "Test content",
            "category_id": 999,  # Non-existent category
        }
        response = client.post(
            "/api/v1/posts/admin", json=post_data, headers=admin_auth_headers
        )
        assert response.status_code == 422  # Should fail validation
