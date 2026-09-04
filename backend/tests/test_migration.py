import importlib.util
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db import entities


def load_script():
    path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "migrate_postgres_to_dynamo.py"
    )
    spec = importlib.util.spec_from_file_location("migrate_postgres_to_dynamo", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script():
    return load_script()


def ts(year, month=1, day=1):
    return datetime(year, month, day, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def postgres_rows():
    return {
        "users": [
            {
                "id": 1,
                "username": "legacy-admin",
                "email": "legacy@example.com",
                "hashed_password": "$2b$12$" + "legacyhash" * 5 + "lega",
                "is_admin": True,
                "is_active": None,
                "created_at": ts(2023),
                "updated_at": None,
            }
        ],
        "categories": [
            {
                "id": 3,
                "name": "Cloud",
                "slug": "cloud",
                "description": None,
                "created_at": ts(2023),
                "updated_at": None,
            },
            {
                "id": 7,
                "name": "Code",
                "slug": "code",
                "description": "Programming",
                "created_at": ts(2023),
                "updated_at": ts(2024),
            },
        ],
        "posts": [
            {
                "id": 10,
                "title": "Published",
                "slug": "published",
                "content": "body",
                "excerpt": "e",
                "read_time": "5 min read",
                "published_at": ts(2024, 2, 1),
                "created_at": ts(2024, 1, 1),
                "updated_at": None,
                "category_id": 3,
                "author_id": 1,
            },
            {
                "id": 11,
                "title": "Draft",
                "slug": "draft",
                "content": "body",
                "excerpt": None,
                "read_time": None,
                "published_at": None,
                "created_at": ts(2024, 3, 1),
                "updated_at": None,
                "category_id": None,
                "author_id": 1,
            },
        ],
        "projects": [
            {
                "id": 5,
                "title": "P",
                "description": "D",
                "image": None,
                "technologies": ["Python"],
                "github_url": None,
                "live_url": None,
                "featured": None,
                "display_order": 2,
                "is_active": True,
                "created_at": ts(2023),
                "updated_at": None,
            }
        ],
        "experience": [
            {
                "id": 2,
                "title": "T",
                "company": "C",
                "location": "L",
                "period": "P",
                "start_date": date(2020, 1, 1),
                "end_date": None,
                "description": "D",
                "technologies": None,
                "achievements": ["a"],
                "is_active": False,
                "created_at": ts(2023),
                "updated_at": None,
            }
        ],
        "skills": [
            {
                "id": 9,
                "name": "S",
                "category": "backend",
                "tier": "core",
                "icon": None,
                "order": 1,
                "is_active": True,
                "created_at": ts(2023),
                "updated_at": None,
            }
        ],
        "education": [
            {
                "id": 1,
                "degree": "D",
                "school": "S",
                "location": "L",
                "period": "P",
                "start_date": date(2015, 8, 1),
                "end_date": date(2019, 5, 1),
                "description": None,
                "order": 0,
                "is_active": True,
                "created_at": ts(2023),
                "updated_at": None,
            }
        ],
        "certifications": [
            {
                "id": 4,
                "name": "N",
                "issuer": "I",
                "issued_date": date(2022, 6, 1),
                "credential_url": None,
                "order": 0,
                "is_active": True,
                "created_at": ts(2023),
                "updated_at": None,
            }
        ],
        "site_content": [
            {
                "id": 1,
                "hero_title": "Hi",
                "hero_subtitle": "Sub",
                "hero_description": "Desc",
                "about_paragraphs": ["one"],
                "about_values": [{"title": "v", "description": "d", "icon": "i"}],
                "profile_image_url": None,
                "resume_url": None,
                "email": "me@example.com",
                "github_url": None,
                "linkedin_url": None,
                "footer_tagline": None,
                "project_sort_mode": "newest",
                "created_at": ts(2023),
                "updated_at": None,
            }
        ],
    }


@pytest.mark.unit
def test_transform_row(script, postgres_rows):
    row = script.transform_row("users", postgres_rows["users"][0])
    assert row["is_active"] is True
    assert "updated_at" not in row
    experience = script.transform_row("experience", postgres_rows["experience"][0])
    assert experience["technologies"] == []
    assert experience["is_active"] is False


@pytest.mark.integration
def test_migrate_then_verify(script, postgres_rows):
    summary = script.migrate(postgres_rows)
    assert summary["posts"] == {"rows": 2, "max_id": 11, "existing": 0}
    assert script.verify(postgres_rows) == []

    assert entities.users.find_by_unique("username", "legacy-admin")[
        "hashed_password"
    ] == (postgres_rows["users"][0]["hashed_password"])
    assert entities.posts.current_counter() == 11
    assert entities.categories.create({"name": "Next", "slug": "next"})["id"] == 8
    assert [p["slug"] for p in entities.posts.list_published()] == ["published"]
    assert entities.posts.has_posts_in_category(3) is True
    assert entities.experience.get(2) is None
    assert entities.experience.get(2, include_inactive=True)["technologies"] == []


@pytest.mark.integration
def test_refuses_non_empty_target(script, postgres_rows):
    seeded = entities.users.create(
        {
            "username": "seeded-admin",
            "email": "seeded@example.com",
            "hashed_password": "x",
            "is_admin": True,
        }
    )
    with pytest.raises(script.TargetNotEmpty) as excinfo:
        script.migrate(postgres_rows)
    assert excinfo.value.existing == {"users": 1}
    assert "--replace" in str(excinfo.value)
    assert entities.users.get(seeded["id"])["username"] == "seeded-admin"
    assert entities.projects.count() == 0


@pytest.mark.integration
def test_replace_purges_stale_pointers(script, postgres_rows):
    entities.users.create(
        {
            "username": "seeded-admin",
            "email": "seeded@example.com",
            "hashed_password": "x",
            "is_admin": True,
        }
    )
    entities.categories.create({"name": "Old", "slug": "old"})
    entities.categories.create({"name": "Older", "slug": "older"})
    summary = script.migrate(postgres_rows, replace=True)
    assert summary["users"]["existing"] == 1
    assert summary["categories"]["existing"] == 2
    assert script.verify(postgres_rows) == []
    assert entities.users.find_by_unique("username", "seeded-admin") is None
    assert entities.users.find_by_unique("email", "seeded@example.com") is None
    assert entities.categories.find_by_unique("slug", "old") is None
    assert entities.categories.count() == 2
    assert entities.categories.current_counter() == 7
    assert entities.users.current_counter() == 1
    assert entities.posts.current_counter() == 11


@pytest.mark.integration
def test_replace_twice_is_idempotent(script, postgres_rows):
    script.migrate(postgres_rows)
    script.migrate(postgres_rows, replace=True)
    assert script.verify(postgres_rows) == []
    assert entities.categories.count() == 2


@pytest.mark.integration
def test_dry_run_writes_nothing(script, postgres_rows):
    entities.skills.create({"name": "Existing", "category": "c", "tier": "t"})
    summary = script.migrate(postgres_rows, dry_run=True)
    assert summary["categories"]["rows"] == 2
    assert summary["categories"]["existing"] == 0
    assert summary["skills"]["existing"] == 1
    assert entities.categories.count() == 0
    assert entities.categories.current_counter() == 0
    assert entities.skills.count() == 1


@pytest.mark.integration
def test_verify_reports_drift(script, postgres_rows):
    script.migrate(postgres_rows)
    entities.categories.update(3, {"name": "Changed"})
    entities.skills.hard_delete(9)
    problems = script.verify(postgres_rows)
    assert any(p.startswith("categories#3.name") for p in problems)
    assert "skills#9: missing" in problems


@pytest.mark.integration
def test_api_serves_migrated_data(script, postgres_rows, client: TestClient):
    script.migrate(postgres_rows)
    posts = client.get("/api/v1/posts/").json()
    assert [p["slug"] for p in posts] == ["published"]
    assert posts[0]["category"]["slug"] == "cloud"
    assert client.get("/api/v1/posts/draft").status_code == 404
    content = client.get("/api/v1/site-content/").json()
    assert content["project_sort_mode"] == "newest"
    assert content["about_values"][0]["title"] == "v"
    project = client.get("/api/v1/projects/5").json()
    assert project["featured"] is False and project["created_at"].startswith(
        "2023-01-01T12:00:00"
    )
    login = client.post(
        "/api/v1/admin/login", json={"username": "legacy-admin", "password": "nope"}
    )
    assert login.status_code == 401
