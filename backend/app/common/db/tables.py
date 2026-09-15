"""Every DynamoDB table this backend owns, and its CreateTable spec.

One registry, so the test suite, the local table script and Terraform
describe the same shapes.

The ten identity tables are not described here. `webbpulse.identity.storage.TABLES`
carries the specs `platform-modules/aws//modules/identity` provisions, so they are
read from there and the copy that used to live in this module is gone. A drift
between a local table and the deployed one is then not expressible.
"""

from webbpulse.identity import (
    CREDENTIALS_TABLE,
    IDENTITY_TOKENS_TABLE,
    LOGIN_ATTEMPTS_TABLE,
    OAUTH_LINKS_TABLE,
    OAUTH_STATES_TABLE,
    PASSKEYS_TABLE,
    RECOVERY_CODES_TABLE,
    REFRESH_TOKENS_TABLE,
    TOTP_FACTORS_TABLE,
    WEBAUTHN_CHALLENGES_TABLE,
)
from webbpulse.identity.storage import TABLES as IDENTITY_TABLE_SPECS

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

RATE_LIMITS = "rate-limits"
"""The rate limiter's own table, keyed and named to match `webbpulse.ratelimit` so
the id allocator's table is not shared with a hot, high-churn workload."""

CREDENTIALS = CREDENTIALS_TABLE
"""The identity credential table, named by the package's own constant so a rename
there is a failing test here. Registered in this module because the suite and
`scripts/create_local_tables.py` both build their tables from it."""
REFRESH_TOKENS = REFRESH_TOKENS_TABLE
LOGIN_ATTEMPTS = LOGIN_ATTEMPTS_TABLE

IDENTITY_TOKENS = IDENTITY_TOKENS_TABLE

TOTP_FACTORS = TOTP_FACTORS_TABLE
RECOVERY_CODES = RECOVERY_CODES_TABLE

OAUTH_STATES = OAUTH_STATES_TABLE
OAUTH_LINKS = OAUTH_LINKS_TABLE

PASSKEYS = PASSKEYS_TABLE
WEBAUTHN_CHALLENGES = WEBAUTHN_CHALLENGES_TABLE

COUNTER_PREFIX = "COUNTER#"
UNIQUE_PREFIX = "UNIQUE#"

POSTS_PUBLISHED_INDEX = "published-index"
POSTS_CATEGORY_INDEX = "category-index"


def _entity_table(entity):
    """The base spec for a plain entity table: one numeric `id` hash key."""
    return {
        "TableName": entity,
        "BillingMode": "PAY_PER_REQUEST",
        "KeySchema": [{"AttributeName": "id", "KeyType": "HASH"}],
        "AttributeDefinitions": [{"AttributeName": "id", "AttributeType": "N"}],
    }


def _posts_table():
    """The posts table, with the published and category listing indexes."""
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


IDENTITY_SPECS = {spec.logical_name: spec for spec in IDENTITY_TABLE_SPECS}
"""The package's identity table specs by logical name, so a lookup here fails loudly
rather than silently registering a table this backend does not own."""


def _identity_table(logical_name):
    """The CreateTable spec the identity module provisions for one identity table.

    Read from the package rather than restated, so the local table and the deployed
    one cannot diverge in a key, an index name or a projection.
    """
    return IDENTITY_SPECS[logical_name].create_table_request()


def _pk_table(name):
    """The base spec for a table keyed by a single string `pk`."""
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
    CREDENTIALS: _identity_table(CREDENTIALS),
    REFRESH_TOKENS: _identity_table(REFRESH_TOKENS),
    LOGIN_ATTEMPTS: _identity_table(LOGIN_ATTEMPTS),
    IDENTITY_TOKENS: _identity_table(IDENTITY_TOKENS),
    TOTP_FACTORS: _identity_table(TOTP_FACTORS),
    RECOVERY_CODES: _identity_table(RECOVERY_CODES),
    OAUTH_STATES: _identity_table(OAUTH_STATES),
    OAUTH_LINKS: _identity_table(OAUTH_LINKS),
    PASSKEYS: _identity_table(PASSKEYS),
    WEBAUTHN_CHALLENGES: _identity_table(WEBAUTHN_CHALLENGES),
}

TTL_ATTRIBUTE = "ttl"

RATE_LIMIT_TTL_ATTRIBUTE = "expires_at"
"""The rate limiter's TTL attribute, distinct from the meta table's `ttl`."""

IDENTITY_TTL_ATTRIBUTE = "expires_at"
"""The identity tables' TTL attribute. Only tables holding expiring session state
enable it; a credential or factor must never expire on a reclaim."""

IDENTITY_ORDER = (
    CREDENTIALS,
    REFRESH_TOKENS,
    LOGIN_ATTEMPTS,
    IDENTITY_TOKENS,
    TOTP_FACTORS,
    RECOVERY_CODES,
    OAUTH_STATES,
    OAUTH_LINKS,
    PASSKEYS,
    WEBAUTHN_CHALLENGES,
)
"""The identity tables in the creation order this backend has always used, which is
not the package's own tuple order. Only the order is stated here; which of them
expires, and on which attribute, is read from the spec."""

ALL_TABLES = (
    *((entity, None) for entity in ENTITIES),
    (META, TTL_ATTRIBUTE),
    (RATE_LIMITS, RATE_LIMIT_TTL_ATTRIBUTE),
    *((name, IDENTITY_SPECS[name].ttl_attribute) for name in IDENTITY_ORDER),
)
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
