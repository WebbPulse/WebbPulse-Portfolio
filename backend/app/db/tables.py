from webbpulse.identity import (
    CREDENTIALS_TABLE,
    IDENTITY_TOKENS_TABLE,
    LOGIN_ATTEMPTS_TABLE,
    RECOVERY_CODES_TABLE,
    REFRESH_FAMILY_INDEX,
    REFRESH_TOKENS_TABLE,
    TOTP_FACTORS_TABLE,
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

# The rate limiter's own table. Login throttling used to write LOGIN_FAIL#
# items into `meta`, which made the id allocator's table shared with a hot,
# high-churn workload and gave every writing domain a reason to hold write
# access to it. The limiter items live here instead, keyed and named to match
# `webbpulse.ratelimit` so PR 4 can swap the package implementation in.
RATE_LIMITS = "rate-limits"

# The identity standard's M2 tables. Every name below is copied from
# `webbpulse.identity.storage` and `webbpulse.identity.lockout`, which is the
# code that reads and writes them, and `terraform/dynamodb.tf` declares the same
# shapes for the deployed tables. `tests/test_identity_m2.py` asserts the two
# sides agree against the constants the package exports, so a rename in the
# package is a failing test here rather than a ValidationException in staging.
#
# These are registered here, and not only in Terraform, because the test suite
# and `scripts/create_local_tables.py` both build their tables from this module.
# A table the package writes to that is missing from `TABLES` is a suite that
# cannot exercise a single M2 flow.
CREDENTIALS = CREDENTIALS_TABLE
REFRESH_TOKENS = REFRESH_TOKENS_TABLE
LOGIN_ATTEMPTS = LOGIN_ATTEMPTS_TABLE

# The identity standard's M3 table, on the same rule as the three above: the
# name is the package's own constant, and `webbpulse.identity.verification` is
# the only code that reads or writes it.
IDENTITY_TOKENS = IDENTITY_TOKENS_TABLE

# The identity standard's M4 tables, on the same rule as the four above: each
# name is the package's own constant, and `webbpulse.identity.mfa` is the only
# code that reads or writes either one.
#
# Neither has a TTL and neither ever will. Section 4.1's rule applies here with
# more force than anywhere else in this module: an expiring refresh token costs
# a user one extra sign in, while a TOTP factor or a recovery code that vanishes
# on a storage reclaim schedule costs them the account. The rows are deleted
# explicitly, by a user turning TOTP off or by a regeneration replacing a set,
# and never on a clock.
#
# The MFA ticket that carries a login between its two legs is not a table. It is
# an `identity-tokens` row with `purpose = "mfa_ticket"`, which is the same
# single-use primitive M3's verification and reset links already use, so M4 adds
# no fifth identity table for it.
TOTP_FACTORS = TOTP_FACTORS_TABLE
RECOVERY_CODES = RECOVERY_CODES_TABLE

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


def _credentials_table():
    """Hash `user_id`, range `credential_type`, and deliberately no TTL.

    The range key is what lets a second credential kind exist later without
    another attribute on the user record, and keeping the password hash in its
    own table is what stops a route that returns a user from serialising one.
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

    Verification is a GetItem on the primary key with no index in the way. The
    index is only for revoking a whole family once a replayed token is seen, and
    its name is the package's `REFRESH_FAMILY_INDEX`, which DynamoDB resolves by
    name, so the two cannot differ.
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

    One item is one single-use link, for either purpose: `purpose` is an
    attribute on the record rather than a second table, which is what makes
    verification and reset the same primitive with the same expiry check and
    the same atomic consumption. `LinkService.confirm` asserts the purpose it
    wanted against the stored record, so one table does not make a verification
    link a valid reset link.

    No index. `DynamoIdentityTokenStore.revoke_for_user` raises rather than
    scanning, and the package's M3 decision 6 is explicit that this stays so: a
    user index would cost a write on the click path to serve the issue path, and
    what it would close is a link the user asked for that expires on its own
    inside an hour.

    The TTL is storage reclamation and never the expiry check. DynamoDB deletes
    on its own schedule, typically within a couple of days, so `confirm`
    re-checks `expires_at` against the clock every time.
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

    `identity_key` is `email#<lower>` or `ip#<addr>`. Ranging on the timestamp
    is what makes the progressive lockout read the recent history newest first
    rather than scanning every attempt ever recorded.
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

    One factor per user, so `user_id` alone is the key. A second authenticator
    is not a second row: the user re-enrols and the seed is replaced, which is
    what keeps the login challenge's factor list a derivation from one item
    rather than a query over several.

    The seed is not stored in the clear. `webbpulse.identity.crypto` seals it
    under a data key from the KMS envelope key `module.identity` creates, and
    the three envelope fields are ordinary non-key attributes, so nothing about
    that reaches this key schema.
    """
    return {
        "TableName": TOTP_FACTORS,
        "BillingMode": "PAY_PER_REQUEST",
        "KeySchema": [{"AttributeName": "user_id", "KeyType": "HASH"}],
        "AttributeDefinitions": [{"AttributeName": "user_id", "AttributeType": "S"}],
    }


def _recovery_codes_table():
    """Hash `user_id`, range `code_hash`, no index, and no TTL either.

    The range key is the hash of the code rather than the code, on the same rule
    the credentials table follows: a recovery code is only ever compared, so
    there is no reason to be able to read one back. Spending one is then a point
    write on the primary key with no index in the way, and reading a whole set
    is one Query on the partition.
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
    CREDENTIALS: _credentials_table(),
    REFRESH_TOKENS: _refresh_tokens_table(),
    LOGIN_ATTEMPTS: _login_attempts_table(),
    IDENTITY_TOKENS: _identity_tokens_table(),
    TOTP_FACTORS: _totp_factors_table(),
    RECOVERY_CODES: _recovery_codes_table(),
}

TTL_ATTRIBUTE = "ttl"

# `webbpulse.ratelimit` names its TTL attribute `expires_at`, not the `ttl` the
# meta table uses, and the Terraform table declaration follows the package. The
# two names have to stay distinct while both tables exist.
RATE_LIMIT_TTL_ATTRIBUTE = "expires_at"

# `webbpulse.identity` names its TTL attribute `expires_at` too, on all three
# of its tables that have one. `credentials`, `totp-factors` and
# `recovery-codes` are not in here and must never be: a credential or a second
# factor that expired on a storage reclaim schedule would sign somebody out of
# their own account, on DynamoDB's timetable rather than on a deadline anybody
# chose, and for the two M4 tables it would lock the account rather than merely
# end a session.
IDENTITY_TTL_ATTRIBUTE = "expires_at"

#: Every table this backend owns, in the order they are created, paired with the
#: TTL attribute each one enables or `None`. `tests/conftest.py` and
#: `scripts/create_local_tables.py` both walk this rather than keeping their own
#: lists, so a table added to `TABLES` is a table both of them create.
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
)


def table_name(prefix, entity):
    return f"{prefix}-{entity}"


def table_definition(prefix, entity):
    spec = dict(TABLES[entity])
    spec["TableName"] = table_name(prefix, entity)
    return spec
