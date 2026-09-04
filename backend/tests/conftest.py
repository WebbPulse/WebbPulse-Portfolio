import os
from datetime import date, datetime, timezone

os.environ.update(
    {
        "TESTING": "1",
        "AWS_DEFAULT_REGION": "us-west-2",
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_SECURITY_TOKEN": "testing",
        "AWS_SESSION_TOKEN": "testing",
        "SECRET_KEY": "test-secret-key",
        "ADMIN_USERNAME": "test-admin",
        "ADMIN_PASSWORD": "test-admin-password",
        "ADMIN_EMAIL": "test-admin@example.com",
        "DYNAMODB_TABLE_PREFIX": "webbpulse-test",
        "ENVIRONMENT": "test",
        "LOG_LEVEL": "WARNING",
    }
)
os.environ.pop("SSM_PARAMETER_PREFIX", None)
os.environ.pop("DYNAMODB_ENDPOINT_URL", None)

import boto3  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from moto import mock_aws  # noqa: E402

from app.config import settings  # noqa: E402
from app.core import admin, site_content  # noqa: E402
from app.core.security import create_access_token, get_password_hash  # noqa: E402
from app.db import client as db_client  # noqa: E402
from app.db import entities  # noqa: E402
from app.db.tables import ENTITIES, META, TTL_ATTRIBUTE, table_definition  # noqa: E402


def create_all_tables(prefix: str = settings.DYNAMODB_TABLE_PREFIX):
    resource = boto3.resource("dynamodb", region_name="us-west-2")
    for entity in ENTITIES + (META,):
        definition = table_definition(prefix, entity)
        resource.create_table(**definition)
    resource.meta.client.update_time_to_live(
        TableName=f"{prefix}-{META}",
        TimeToLiveSpecification={"Enabled": True, "AttributeName": TTL_ATTRIBUTE},
    )


def reset_seed_state():
    admin.reset_seed_state()
    site_content.reset_seed_state()


@pytest.fixture(autouse=True)
def aws_tables():
    with mock_aws():
        db_client.reset()
        reset_seed_state()
        create_all_tables()
        yield
        db_client.reset()
        reset_seed_state()


@pytest.fixture
def client():
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def test_user():
    return entities.users.create(
        {
            "email": "test@example.com",
            "username": "testuser",
            "hashed_password": get_password_hash("testpassword123"),
            "is_admin": False,
            "is_active": True,
        }
    )


@pytest.fixture
def test_admin_user():
    return entities.users.create(
        {
            "email": "admin@example.com",
            "username": "adminuser",
            "hashed_password": get_password_hash("adminpassword123"),
            "is_admin": True,
            "is_active": True,
        }
    )


@pytest.fixture
def test_category():
    return entities.categories.create(
        {
            "name": "Test Category",
            "slug": "test-category",
            "description": "A test category",
        }
    )


@pytest.fixture
def test_post(test_user, test_category):
    return entities.posts.create(
        {
            "title": "Test Post",
            "slug": "test-post",
            "content": "# Test Post\n\nThis is test content.",
            "excerpt": "A test post excerpt",
            "read_time": "5 min read",
            "published_at": datetime.now(timezone.utc),
            "author_id": test_user["id"],
            "category_id": test_category["id"],
        }
    )


@pytest.fixture
def test_draft_post(test_user, test_category):
    return entities.posts.create(
        {
            "title": "Test Draft Post",
            "slug": "test-draft-post",
            "content": "# Draft\n\nThis is a draft.",
            "excerpt": "A draft post excerpt",
            "read_time": "3 min read",
            "published_at": None,
            "author_id": test_user["id"],
            "category_id": test_category["id"],
        }
    )


@pytest.fixture
def test_project():
    return entities.projects.create(
        {
            "title": "Test Project",
            "description": "A test project description",
            "technologies": ["Python", "FastAPI", "React"],
            "github_url": "https://github.com/test/project",
            "live_url": "https://test-project.com",
            "image": "https://example.com/image.jpg",
            "featured": True,
        }
    )


@pytest.fixture
def test_experience():
    return entities.experience.create(
        {
            "title": "Test Position",
            "company": "Test Company",
            "location": "Test City, Test State",
            "period": "Jan 2022 - Dec 2023",
            "start_date": date(2022, 1, 1),
            "end_date": date(2023, 12, 31),
            "description": "A test job description",
            "technologies": ["Python", "SQL", "AWS"],
            "achievements": ["Achievement 1", "Achievement 2"],
        }
    )


@pytest.fixture
def test_education():
    return entities.education.create(
        {
            "degree": "Test Degree",
            "school": "Test University",
            "location": "Test City, ST",
            "period": "Aug 2018 - May 2022",
            "start_date": date(2018, 8, 1),
            "end_date": date(2022, 5, 31),
            "description": "Test description",
            "order": 10,
        }
    )


@pytest.fixture
def test_certification():
    return entities.certifications.create(
        {
            "name": "Test Cert",
            "issuer": "Test Issuer",
            "issued_date": date(2023, 1, 1),
            "credential_url": "https://example.com/cred/test",
            "order": 10,
        }
    )


@pytest.fixture
def test_site_content():
    return entities.site_content.create(
        {
            "hero_title": "Hi, I'm Test",
            "hero_subtitle": "Test Subtitle",
            "hero_description": "Test description",
            "about_paragraphs": ["Paragraph one", "Paragraph two"],
            "about_values": [
                {
                    "title": "Test Value",
                    "description": "Test value description",
                    "icon": "star",
                }
            ],
        },
        item_id=entities.SITE_CONTENT_ID,
    )


@pytest.fixture
def test_skill():
    return entities.skills.create(
        {
            "name": "Test Skill",
            "category": "frontend",
            "tier": "working",
            "icon": "🧪",
            "order": 10,
        }
    )


@pytest.fixture
def auth_headers(test_user):
    return {
        "Authorization": f"Bearer {create_access_token({'sub': test_user['username']})}"
    }


@pytest.fixture
def admin_auth_headers(test_admin_user):
    token = create_access_token({"sub": test_admin_user["username"]})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def invalid_auth_headers():
    return {"Authorization": "Bearer invalid_token"}


@pytest.fixture
def sample_post_data():
    return {
        "title": "Sample Post",
        "slug": "sample-post",
        "content": "# Sample Post\n\nThis is sample content.",
        "excerpt": "A sample post excerpt",
        "read_time": "8 min read",
        "category_id": 1,
    }


@pytest.fixture
def sample_category_data():
    return {
        "name": "Sample Category",
        "slug": "sample-category",
        "description": "A sample category description",
    }


@pytest.fixture
def sample_project_data():
    return {
        "title": "Sample Project",
        "description": "A sample project description",
        "technologies": ["React", "TypeScript", "Node.js"],
        "github_url": "https://github.com/sample/project",
        "live_url": "https://sample-project.com",
        "image": "https://example.com/sample.jpg",
        "featured": True,
    }


@pytest.fixture
def sample_experience_data():
    return {
        "title": "Sample Position",
        "company": "Sample Company",
        "location": "Sample City, Sample State",
        "period": "Jan 2022 - Dec 2023",
        "start_date": "2022-01-01",
        "end_date": "2023-12-31",
        "description": "A sample job description",
        "technologies": ["Python", "JavaScript", "Docker"],
        "achievements": ["Achievement 1", "Achievement 2"],
    }


@pytest.fixture
def sample_skill_data():
    return {
        "name": "Sample Skill",
        "category": "backend",
        "tier": "working",
        "icon": "🔧",
        "order": 20,
    }


@pytest.fixture
def sample_education_data():
    return {
        "degree": "Sample Degree",
        "school": "Sample University",
        "location": "Sample City, ST",
        "period": "Aug 2018 - May 2022",
        "start_date": "2018-08-01",
        "end_date": "2022-05-31",
        "description": "Sample description",
        "order": 20,
    }


@pytest.fixture
def sample_certification_data():
    return {
        "name": "Sample Certification",
        "issuer": "Sample Issuer",
        "issued_date": "2023-06-01",
        "credential_url": "https://example.com/cred/123",
        "order": 20,
    }
