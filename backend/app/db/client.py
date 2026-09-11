"""Cached boto3 DynamoDB clients, pointed at Local when an endpoint is set."""

from functools import lru_cache

import boto3

from ..config import settings
from .tables import table_name


def _connection_kwargs():
    """Boto3 keyword arguments, carrying an endpoint only when one is set."""
    kwargs = {}
    if settings.DYNAMODB_ENDPOINT_URL:
        kwargs["endpoint_url"] = settings.DYNAMODB_ENDPOINT_URL
    return kwargs


@lru_cache(maxsize=1)
def dynamodb_resource():
    """The shared DynamoDB resource, built once per process."""
    return boto3.resource("dynamodb", **_connection_kwargs())


@lru_cache(maxsize=1)
def dynamodb_client():
    """The shared low level DynamoDB client, built once per process."""
    return boto3.client("dynamodb", **_connection_kwargs())


def table(entity):
    """The boto3 Table for one entity, under the configured prefix."""
    return dynamodb_resource().Table(table_name(settings.DYNAMODB_TABLE_PREFIX, entity))


def reset():
    """Drop both cached clients so the next call rereads the settings."""
    dynamodb_resource.cache_clear()
    dynamodb_client.cache_clear()
