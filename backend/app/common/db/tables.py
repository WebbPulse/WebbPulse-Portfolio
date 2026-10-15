"""Every DynamoDB table this backend owns, and its CreateTable spec.

One registry, so the test suite, the local table script and Terraform describe
the same shapes.
"""

PUBLIC_CACHE = "public-cache"
"""The public domain's cache table, keyed by a string `pk` with a `ttl`. It holds
computed public data such as the live system figures."""

TTL_ATTRIBUTE = "ttl"


def _pk_table(name):
    """The base spec for a table keyed by a single string `pk`."""
    return {
        "TableName": name,
        "BillingMode": "PAY_PER_REQUEST",
        "KeySchema": [{"AttributeName": "pk", "KeyType": "HASH"}],
        "AttributeDefinitions": [{"AttributeName": "pk", "AttributeType": "S"}],
    }


TABLES = {
    PUBLIC_CACHE: _pk_table(PUBLIC_CACHE),
}

ALL_TABLES = ((PUBLIC_CACHE, TTL_ATTRIBUTE),)
"""Every table this backend owns, in creation order, paired with the TTL attribute it
enables or `None`. The suite and the local table script walk it."""


def table_name(prefix, entity):
    """The deployed table name for an entity under this environment's prefix."""
    return f"{prefix}-{entity}"


def table_definition(prefix, entity):
    """A CreateTable spec for an entity, named for this environment's prefix."""
    spec = dict(TABLES[entity])
    spec["TableName"] = table_name(prefix, entity)
    return spec
