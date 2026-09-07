ENTITIES = (
    "users",
    "categories",
    "posts",
    "projects",
    "experience",
    "skills",
    "education",
    "certifications",
    "site-content",
)

META = "meta"

# The rate limiter's own table. Login throttling used to write LOGIN_FAIL#
# items into `meta`, which made the id allocator's table shared with a hot,
# high-churn workload and gave every writing domain a reason to hold write
# access to it. The limiter items live here instead, keyed and named to match
# `webbpulse.ratelimit` so PR 4 can swap the package implementation in.
RATE_LIMITS = "rate-limits"

COUNTER_PREFIX = "COUNTER#"
UNIQUE_PREFIX = "UNIQUE#"

POSTS_PUBLISHED_INDEX = "published-index"
POSTS_CATEGORY_INDEX = "category-index"


def _entity_table(entity):
    return {
        "TableName": entity,
        "BillingMode": "PAY_PER_REQUEST",
        "KeySchema": [{"AttributeName": "id", "KeyType": "HASH"}],
        "AttributeDefinitions": [{"AttributeName": "id", "AttributeType": "N"}],
    }


def _posts_table():
    spec = _entity_table("posts")
    spec["AttributeDefinitions"] = [
        {"AttributeName": "id", "AttributeType": "N"},
        {"AttributeName": "published_flag", "AttributeType": "S"},
        {"AttributeName": "published_at", "AttributeType": "S"},
        {"AttributeName": "category_id", "AttributeType": "N"},
    ]
    spec["GlobalSecondaryIndexes"] = [
        {
            "IndexName": POSTS_PUBLISHED_INDEX,
            "KeySchema": [
                {"AttributeName": "published_flag", "KeyType": "HASH"},
                {"AttributeName": "published_at", "KeyType": "RANGE"},
            ],
            "Projection": {"ProjectionType": "ALL"},
        },
        {
            "IndexName": POSTS_CATEGORY_INDEX,
            "KeySchema": [
                {"AttributeName": "category_id", "KeyType": "HASH"},
                {"AttributeName": "id", "KeyType": "RANGE"},
            ],
            "Projection": {"ProjectionType": "KEYS_ONLY"},
        },
    ]
    return spec


def _pk_table(name):
    return {
        "TableName": name,
        "BillingMode": "PAY_PER_REQUEST",
        "KeySchema": [{"AttributeName": "pk", "KeyType": "HASH"}],
        "AttributeDefinitions": [{"AttributeName": "pk", "AttributeType": "S"}],
    }


TABLES = {
    **{entity: _entity_table(entity) for entity in ENTITIES if entity != "posts"},
    "posts": _posts_table(),
    META: _pk_table(META),
    RATE_LIMITS: _pk_table(RATE_LIMITS),
}

TTL_ATTRIBUTE = "ttl"

# `webbpulse.ratelimit` names its TTL attribute `expires_at`, not the `ttl` the
# meta table uses, and the Terraform table declaration follows the package. The
# two names have to stay distinct while both tables exist.
RATE_LIMIT_TTL_ATTRIBUTE = "expires_at"


def table_name(prefix, entity):
    return f"{prefix}-{entity}"


def table_definition(prefix, entity):
    spec = dict(TABLES[entity])
    spec["TableName"] = table_name(prefix, entity)
    return spec
