"""The admin seeder in identity mode, against the real store on moto."""

import pytest
from webbpulse.identity import PASSWORD_CREDENTIAL_TYPE, CredentialRecord
from webbpulse.security import hash_password, verify_password

from app.config import settings
from app.core import middleware
from app.db import entities
from app.db.tables import CREDENTIALS
from app.domains.identity.service import (
    LEGACY_HASH_FIELD,
    reset_seed_state,
    seed_admin_user,
)


@pytest.fixture
def store():
    """The real `DynamoCredentialStore` over the moto table `conftest` created."""
    from webbpulse.dynamodb import Repository
    from webbpulse.identity import DynamoCredentialStore

    return DynamoCredentialStore(
        Repository(CREDENTIALS, prefix=settings.DYNAMODB_TABLE_PREFIX)
    )


def make_admin(**overrides):
    """The administrator's row, as the legacy seeder used to write it."""
    record = {
        "username": settings.ADMIN_USERNAME,
        "email": settings.ADMIN_EMAIL,
        "hashed_password": hash_password(settings.ADMIN_PASSWORD),
        "is_admin": True,
        "is_active": True,
    }
    record.update(overrides)
    return entities.users.create(record)


def reload(user):
    """Re-read a user row, inactive ones included."""
    return entities.users.get(user["id"], include_inactive=True)


class TestClearedColumnStaysCleared:
    """Seeding never repopulates the cleared legacy password column."""

    def test_a_row_with_no_legacy_column_is_not_repopulated(self, store):
        """The whole reason this change exists."""
        user = make_admin()
        entities.users.update(user["id"], {LEGACY_HASH_FIELD: None})
        assert LEGACY_HASH_FIELD not in reload(user)
        store.put(
            CredentialRecord(
                user_id=str(user["id"]),
                credential_type=PASSWORD_CREDENTIAL_TYPE,
                secret=hash_password(settings.ADMIN_PASSWORD),
            )
        )

        seed_admin_user(store)

        assert LEGACY_HASH_FIELD not in reload(user)

    def test_a_populated_column_is_left_alone_rather_than_rewritten(self, store):
        """Identity mode neither reads nor writes the column, in either direction."""
        original = hash_password("something-that-is-not-the-admin-password")
        user = make_admin(hashed_password=original)
        store.put(
            CredentialRecord(
                user_id=str(user["id"]),
                credential_type=PASSWORD_CREDENTIAL_TYPE,
                secret=hash_password(settings.ADMIN_PASSWORD),
            )
        )

        seed_admin_user(store)

        assert reload(user)[LEGACY_HASH_FIELD] == original

    def test_the_legacy_path_still_reconciles_the_column(self):
        """No store supplied means the old behaviour, unchanged."""
        user = make_admin(hashed_password=hash_password("stale"))

        seed_admin_user()

        assert verify_password(settings.ADMIN_PASSWORD, reload(user)[LEGACY_HASH_FIELD])


class TestExistingCredentialIsNotOverwritten:
    """Seeding leaves an existing identity credential alone."""

    def test_a_password_changed_through_the_identity_flow_survives_a_seed(self, store):
        """The case that makes this a create and not a reconcile."""
        user = make_admin()
        chosen = hash_password("the-password-the-admin-actually-chose")
        store.put(
            CredentialRecord(
                user_id=str(user["id"]),
                credential_type=PASSWORD_CREDENTIAL_TYPE,
                secret=chosen,
            )
        )

        seed_admin_user(store)

        credential = store.get(str(user["id"]), PASSWORD_CREDENTIAL_TYPE)
        assert credential.secret == chosen
        assert verify_password(
            "the-password-the-admin-actually-chose", credential.secret
        )
        assert not verify_password(settings.ADMIN_PASSWORD, credential.secret)

    def test_created_at_is_not_refreshed_by_a_seed(self, store):
        """Repeated seeds leave both credential timestamps untouched."""
        user = make_admin()
        store.put(
            CredentialRecord(
                user_id=str(user["id"]),
                credential_type=PASSWORD_CREDENTIAL_TYPE,
                secret=hash_password("chosen"),
            )
        )
        before = store.get(str(user["id"]), PASSWORD_CREDENTIAL_TYPE)

        seed_admin_user(store)
        seed_admin_user(store)

        after = store.get(str(user["id"]), PASSWORD_CREDENTIAL_TYPE)
        assert after.created_at == before.created_at
        assert after.updated_at == before.updated_at


class TestMissingCredentialIsCreatedOnce:
    """Seeding creates the admin row and credential exactly once."""

    def test_a_brand_new_environment_gets_a_row_and_a_credential(self, store):
        """An empty environment gets an admin row and credential, no legacy column."""
        assert entities.users.count() == 0

        seed_admin_user(store)

        user = entities.users.find_by_unique("username", settings.ADMIN_USERNAME)
        assert user["is_admin"] is True and user["is_active"] is True
        assert user["email"] == settings.ADMIN_EMAIL
        assert LEGACY_HASH_FIELD not in user
        credential = store.get(str(user["id"]), PASSWORD_CREDENTIAL_TYPE)
        assert verify_password(settings.ADMIN_PASSWORD, credential.secret)

    def test_an_existing_row_with_no_credential_gets_one(self, store):
        """An existing admin row without a credential gets one."""
        user = make_admin()
        assert store.get(str(user["id"]), PASSWORD_CREDENTIAL_TYPE) is None

        seed_admin_user(store)

        credential = store.get(str(user["id"]), PASSWORD_CREDENTIAL_TYPE)
        assert verify_password(settings.ADMIN_PASSWORD, credential.secret)

    def test_repeated_seeds_write_the_credential_exactly_once(self, store):
        """Repeated seeds keep one user and one unchanged credential."""
        seed_admin_user(store)
        user = entities.users.find_by_unique("username", settings.ADMIN_USERNAME)
        first = store.get(str(user["id"]), PASSWORD_CREDENTIAL_TYPE)

        seed_admin_user(store)
        seed_admin_user(store)

        after = store.get(str(user["id"]), PASSWORD_CREDENTIAL_TYPE)
        assert after.secret == first.secret
        assert entities.users.count() == 1

    def test_the_row_is_still_reconciled_in_identity_mode(self, store):
        """Everything except the password is the seeder's job in both modes."""
        user = make_admin(email="stale@example.com", is_admin=False, is_active=False)

        seed_admin_user(store)

        refreshed = reload(user)
        assert refreshed["email"] == settings.ADMIN_EMAIL
        assert refreshed["is_admin"] is True
        assert refreshed["is_active"] is True


class TestTheStoreResolution:
    """`app/core/middleware.py` is what decides which mode the seeder runs in."""

    def test_no_identity_issuer_means_no_store(self, monkeypatch):
        """With no identity issuer configured there is no credential store."""
        middleware.reset_admin_credential_store()
        monkeypatch.setattr(settings, "IDENTITY_ISSUER", None)
        try:
            assert middleware._admin_credential_store() is None
        finally:
            middleware.reset_admin_credential_store()

    def test_an_identity_issuer_builds_the_credential_store(self, monkeypatch):
        """An identity issuer builds a DynamoDB credential store."""
        middleware.reset_admin_credential_store()
        monkeypatch.setattr(
            settings, "IDENTITY_ISSUER", "https://api.example.test/api/auth"
        )
        try:
            resolved = middleware._admin_credential_store()
            assert resolved is not None
            from webbpulse.identity import DynamoCredentialStore

            assert isinstance(resolved, DynamoCredentialStore)
        finally:
            middleware.reset_admin_credential_store()

    def test_the_seed_middleware_hook_runs_in_the_resolved_mode(self, monkeypatch):
        """`_seed_admin` is the zero-argument callable `SEEDERS` holds."""
        middleware.reset_admin_credential_store()
        monkeypatch.setattr(
            settings, "IDENTITY_ISSUER", "https://api.example.test/api/auth"
        )
        reset_seed_state()
        try:
            middleware.SEEDERS["admin"]()
            user = entities.users.find_by_unique("username", settings.ADMIN_USERNAME)
            assert LEGACY_HASH_FIELD not in user
            store_ = middleware._admin_credential_store()
            assert store_.get(str(user["id"]), PASSWORD_CREDENTIAL_TYPE) is not None
        finally:
            middleware.reset_admin_credential_store()
            reset_seed_state()
