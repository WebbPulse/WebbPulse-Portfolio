"""Every DynamoDB table this backend owns, and its CreateTable spec.

One registry, so the test suite, the local table script and Terraform
describe the same shapes.
"""

from webbpulse.identity import (
    CREDENTIALS_TABLE,
    IDENTITY_TOKENS_TABLE,
    LOGIN_ATTEMPTS_TABLE,
    OAUTH_LINK_USER_INDEX,
    OAUTH_LINKS_TABLE,
    OAUTH_STATES_TABLE,
    PASSKEY_CREDENTIAL_INDEX,
    PASSKEYS_TABLE,
    RECOVERY_CODES_TABLE,
    REFRESH_FAMILY_INDEX,
    REFRESH_TOKENS_TABLE,
    TOTP_FACTORS_TABLE,
    WEBAUTHN_CHALLENGES_TABLE,
)

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

#: The rate limiter's own table, keyed and named to match `webbpulse.ratelimit`
#: so the id allocator's table is not shared with a hot, high-churn workload.
RATE_LIMITS = "rate-limits"

#: Identity tables, named by the package's own constants so a rename there is a
#: failing test here. Registered in this module because the suite and
#: `scripts/create_local_tables.py` both build their tables from it.
CREDENTIALS = CREDENTIALS_TABLE
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


def _credentials_table():
    """Hash `user_id`, range `credential_type`, and deliberately no TTL.

    Keeping the password hash in its own table is what stops a route that
    returns a user serialising one.
    """
    return {
        "TableName": CREDENTIALS,
        "BillingMode": "PAY_PER_REQUEST",
        "KeySchema": [
            {"AttributeName": "user_id", "KeyType": "HASH"},
            {"AttributeName": "credential_type", "KeyType": "RANGE"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "user_id", "AttributeType": "S"},
            {"AttributeName": "credential_type", "AttributeType": "S"},
        ],
    }


def _refresh_tokens_table():
    """Hash `token_hash`, plus the family index reuse detection revokes on.

    Verification is a point read; the index exists only to revoke a whole
    family once a replayed token is seen.
    """
    return {
        "TableName": REFRESH_TOKENS,
        "BillingMode": "PAY_PER_REQUEST",
        "KeySchema": [{"AttributeName": "token_hash", "KeyType": "HASH"}],
        "AttributeDefinitions": [
            {"AttributeName": "token_hash", "AttributeType": "S"},
            {"AttributeName": "family_id", "AttributeType": "S"},
            {"AttributeName": "generation", "AttributeType": "N"},
        ],
        "GlobalSecondaryIndexes": [
            {
                "IndexName": REFRESH_FAMILY_INDEX,
                "KeySchema": [
                    {"AttributeName": "family_id", "KeyType": "HASH"},
                    {"AttributeName": "generation", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
        ],
    }


def _identity_tokens_table():
    """Hash `token_hash`, no range, no index, and a TTL that reclaims only.

    One item is one single-use link, its `purpose` an attribute rather than a
    second table. Expiry is re-checked on read, so the TTL is never the check.
    """
    return {
        "TableName": IDENTITY_TOKENS,
        "BillingMode": "PAY_PER_REQUEST",
        "KeySchema": [{"AttributeName": "token_hash", "KeyType": "HASH"}],
        "AttributeDefinitions": [
            {"AttributeName": "token_hash", "AttributeType": "S"},
        ],
    }


def _login_attempts_table():
    """Hash `identity_key`, range `attempted_at`, so an attempt is an append.

    Ranging on the timestamp lets the progressive lockout read recent history
    newest first rather than every attempt ever recorded.
    """
    return {
        "TableName": LOGIN_ATTEMPTS,
        "BillingMode": "PAY_PER_REQUEST",
        "KeySchema": [
            {"AttributeName": "identity_key", "KeyType": "HASH"},
            {"AttributeName": "attempted_at", "KeyType": "RANGE"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "identity_key", "AttributeType": "S"},
            {"AttributeName": "attempted_at", "AttributeType": "S"},
        ],
    }


def _totp_factors_table():
    """Hash `user_id`, no range key, no index, and deliberately no TTL.

    One factor per user: re-enrolling replaces the seed rather than adding a
    row. The seed itself is sealed under a KMS data key by the package.
    """
    return {
        "TableName": TOTP_FACTORS,
        "BillingMode": "PAY_PER_REQUEST",
        "KeySchema": [{"AttributeName": "user_id", "KeyType": "HASH"}],
        "AttributeDefinitions": [{"AttributeName": "user_id", "AttributeType": "S"}],
    }


def _recovery_codes_table():
    """Hash `user_id`, range `code_hash`, no index, and no TTL either.

    A code is only ever compared, so only its hash is stored. Spending one is
    a point write and reading a set is one Query on the partition.
    """
    return {
        "TableName": RECOVERY_CODES,
        "BillingMode": "PAY_PER_REQUEST",
        "KeySchema": [
            {"AttributeName": "user_id", "KeyType": "HASH"},
            {"AttributeName": "code_hash", "KeyType": "RANGE"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "user_id", "AttributeType": "S"},
            {"AttributeName": "code_hash", "AttributeType": "S"},
        ],
    }


def _oauth_states_table():
    """Hash `state`, no range key, no index, and a TTL that reclaims only.

    One row is one in-flight authorization request, spent by a conditional delete
    so racing callbacks resolve to one winner. Expiry is re-checked on read.
    """
    return {
        "TableName": OAUTH_STATES,
        "BillingMode": "PAY_PER_REQUEST",
        "KeySchema": [{"AttributeName": "state", "KeyType": "HASH"}],
        "AttributeDefinitions": [{"AttributeName": "state", "AttributeType": "S"}],
    }


def _oauth_links_table():
    """Hash `provider_subject`, plus the user index, and deliberately no TTL.

    The provider identity as primary key makes uniqueness a conditional put. A
    link may be a user's only sign-in method, so it must never expire.
    """
    return {
        "TableName": OAUTH_LINKS,
        "BillingMode": "PAY_PER_REQUEST",
        "KeySchema": [{"AttributeName": "provider_subject", "KeyType": "HASH"}],
        "AttributeDefinitions": [
            {"AttributeName": "provider_subject", "AttributeType": "S"},
            {"AttributeName": "user_id", "AttributeType": "S"},
        ],
        "GlobalSecondaryIndexes": [
            {
                "IndexName": OAUTH_LINK_USER_INDEX,
                "KeySchema": [{"AttributeName": "user_id", "KeyType": "HASH"}],
                "Projection": {"ProjectionType": "ALL"},
            },
        ],
    }


def _passkeys_table():
    """Hash `user_id`, range `credential_id`, one index the other way, no TTL.

    The index serves the login lookup from credential id to owner. A passkey may
    be a user's only factor, so it must never expire.
    """
    return {
        "TableName": PASSKEYS,
        "BillingMode": "PAY_PER_REQUEST",
        "KeySchema": [
            {"AttributeName": "user_id", "KeyType": "HASH"},
            {"AttributeName": "credential_id", "KeyType": "RANGE"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "user_id", "AttributeType": "S"},
            {"AttributeName": "credential_id", "AttributeType": "S"},
        ],
        "GlobalSecondaryIndexes": [
            {
                "IndexName": PASSKEY_CREDENTIAL_INDEX,
                "KeySchema": [{"AttributeName": "credential_id", "KeyType": "HASH"}],
                "Projection": {"ProjectionType": "ALL"},
            },
        ],
    }


def _webauthn_challenges_table():
    """Hash `challenge_id`, no range, no index, and a TTL that reclaims only.

    A challenge is a row because unreplayability is a claim about state. It is
    deleted on consumption and refused once its deadline passes.
    """
    return {
        "TableName": WEBAUTHN_CHALLENGES,
        "BillingMode": "PAY_PER_REQUEST",
        "KeySchema": [{"AttributeName": "challenge_id", "KeyType": "HASH"}],
        "AttributeDefinitions": [
            {"AttributeName": "challenge_id", "AttributeType": "S"}
        ],
    }


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
    CREDENTIALS: _credentials_table(),
    REFRESH_TOKENS: _refresh_tokens_table(),
    LOGIN_ATTEMPTS: _login_attempts_table(),
    IDENTITY_TOKENS: _identity_tokens_table(),
    TOTP_FACTORS: _totp_factors_table(),
    RECOVERY_CODES: _recovery_codes_table(),
    OAUTH_STATES: _oauth_states_table(),
    OAUTH_LINKS: _oauth_links_table(),
    PASSKEYS: _passkeys_table(),
    WEBAUTHN_CHALLENGES: _webauthn_challenges_table(),
}

TTL_ATTRIBUTE = "ttl"

#: The rate limiter's TTL attribute, distinct from the meta table's `ttl`.
RATE_LIMIT_TTL_ATTRIBUTE = "expires_at"

#: The identity tables' TTL attribute. Only tables holding expiring session
#: state enable it; a credential or factor must never expire on a reclaim.
IDENTITY_TTL_ATTRIBUTE = "expires_at"

#: Every table this backend owns, in creation order, paired with the TTL
#: attribute it enables or `None`. The suite and the local table script walk it.
ALL_TABLES = (
    *((entity, None) for entity in ENTITIES),
    (META, TTL_ATTRIBUTE),
    (RATE_LIMITS, RATE_LIMIT_TTL_ATTRIBUTE),
    (CREDENTIALS, None),
    (REFRESH_TOKENS, IDENTITY_TTL_ATTRIBUTE),
    (LOGIN_ATTEMPTS, IDENTITY_TTL_ATTRIBUTE),
    (IDENTITY_TOKENS, IDENTITY_TTL_ATTRIBUTE),
    (TOTP_FACTORS, None),
    (RECOVERY_CODES, None),
    (OAUTH_STATES, IDENTITY_TTL_ATTRIBUTE),
    (OAUTH_LINKS, None),
    (PASSKEYS, None),
    (WEBAUTHN_CHALLENGES, IDENTITY_TTL_ATTRIBUTE),
)


def table_name(prefix, entity):
    """The deployed table name for an entity under this environment's prefix."""
    return f"{prefix}-{entity}"


def table_definition(prefix, entity):
    """A CreateTable spec for an entity, named for this environment's prefix."""
    spec = dict(TABLES[entity])
    spec["TableName"] = table_name(prefix, entity)
    return spec
