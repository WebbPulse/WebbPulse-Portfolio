"""Shared fixtures: a mocked AWS environment with the tables this backend owns."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

pytest_plugins = ["webbpulse.testing"]
"""The package's own fixtures, which is where `primary_keys_only` comes from."""

os.environ.update(
    {
        "TESTING": "1",
        "AWS_DEFAULT_REGION": "us-west-2",
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_SECURITY_TOKEN": "testing",
        "AWS_SESSION_TOKEN": "testing",
        "DYNAMODB_TABLE_PREFIX": "webbpulse-test",
        "ENVIRONMENT": "test",
        "LOG_LEVEL": "WARNING",
    }
)
os.environ.pop("APP_SECRETS_ARN", None)
os.environ.pop("DYNAMODB_ENDPOINT_URL", None)

import boto3  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from moto import mock_aws  # noqa: E402

from app.common.config import settings  # noqa: E402
from app.common.db import client as db_client  # noqa: E402
from app.common.db.tables import ALL_TABLES, table_definition  # noqa: E402

if TYPE_CHECKING:
    from webbpulse.testing import CheckedKey


def create_all_tables(prefix: str = settings.DYNAMODB_TABLE_PREFIX):
    """Create every table this backend owns, TTL included where there is one."""
    resource = boto3.resource("dynamodb", region_name="us-west-2")
    for entity, ttl_attribute in ALL_TABLES:
        definition = table_definition(prefix, entity)
        resource.create_table(**definition)
        if ttl_attribute is None:
            continue
        resource.meta.client.update_time_to_live(
            TableName=definition["TableName"],
            TimeToLiveSpecification={
                "Enabled": True,
                "AttributeName": ttl_attribute,
            },
        )


@pytest.fixture(autouse=True)
def _primary_keys_only(primary_keys_only: list[CheckedKey]) -> list[CheckedKey]:
    """Hold every moto test to DynamoDB's exact primary key rule."""
    return primary_keys_only


@pytest.fixture(autouse=True)
def aws_tables():
    """Run each test against freshly created tables in a mocked AWS."""
    with mock_aws():
        db_client.reset()
        create_all_tables()
        yield
        db_client.reset()


@pytest.fixture
def client():
    """The whole surface in one process, built from the domain routers."""
    from app.common.composition.app import build_app

    with TestClient(build_app()) as test_client:
        yield test_client
