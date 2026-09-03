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

COUNTER_PREFIX = "COUNTER#"
UNIQUE_PREFIX = "UNIQUE#"
LOGIN_FAIL_PREFIX = "LOGIN_FAIL#"

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


def _meta_table():
    return {
        "TableName": META,
        "BillingMode": "PAY_PER_REQUEST",
        "KeySchema": [{"AttributeName": "pk", "KeyType": "HASH"}],
        "AttributeDefinitions": [{"AttributeName": "pk", "AttributeType": "S"}],
    }


TABLES = {
    **{entity: _entity_table(entity) for entity in ENTITIES if entity != "posts"},
    "posts": _posts_table(),
    META: _meta_table(),
}

TTL_ATTRIBUTE = "ttl"


def table_name(prefix, entity):
    return f"{prefix}-{entity}"


def table_definition(prefix, entity):
    spec = dict(TABLES[entity])
    spec["TableName"] = table_name(prefix, entity)
    return spec
