from functools import lru_cache

import boto3

from ..config import settings
from .tables import table_name


def _connection_kwargs():
    kwargs = {}
    if settings.DYNAMODB_ENDPOINT_URL:
        kwargs["endpoint_url"] = settings.DYNAMODB_ENDPOINT_URL
    return kwargs


@lru_cache(maxsize=1)
def dynamodb_resource():
    return boto3.resource("dynamodb", **_connection_kwargs())


@lru_cache(maxsize=1)
def dynamodb_client():
    return boto3.client("dynamodb", **_connection_kwargs())


def table(entity):
    return dynamodb_resource().Table(table_name(settings.DYNAMODB_TABLE_PREFIX, entity))


def reset():
    dynamodb_resource.cache_clear()
    dynamodb_client.cache_clear()
