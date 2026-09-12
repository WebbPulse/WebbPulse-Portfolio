"""`PortfolioIdentityHooks`: who may sign in here, and what a user record is.

The package owns how signing in works; this owns who may. Portfolio has one
administrator and no other roles, so the whole policy is two columns and a claim.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from webbpulse.identity import AuthenticationRefused

from ..db.entities import users

REFUSAL_MESSAGE = "This account may not sign in."
"""What `may_authenticate` says when it refuses. One message for every failing
column, so login cannot be used to tell missing from refused."""
REFUSAL_CODE = "NOT_AN_ADMINISTRATOR"

ADMIN_ROLE = "admin"
"""The claim every authenticated user of this product carries, as a list so a
consumer's check has the same shape as in a product with several roles."""

USERNAME_ATTEMPTS = 100
"""How many suffixed usernames `create_user` tries before giving up, so a
pathological local part fails the registration rather than spinning."""


class PortfolioIdentityHooks:
    """Portfolio's `IdentityHooks`, satisfying the protocol structurally.

    Stateless, so one instance is shared per process, and every method resolves
    its table per call rather than caching a boto3 object across a freeze.
    """

    def load_user_by_id(self, user_id: str) -> Mapping[str, Any] | None:
        """The user whose id is this `sub`, or `None`.

        A `sub` that is not an integer is not one of this product's ids, so it
        gets the same `None` a missing row does.
        """
        try:
            numeric_id = int(user_id)
        except (TypeError, ValueError):
            return None
        return users.get(numeric_id)

    def load_user_by_email(self, email: str) -> Mapping[str, Any] | None:
        """The user with this address, or `None`.

        The package already lowercased and stripped it. Trying a second casing
        would make an address's existence answerable by timing, so this does not.
        """
        return users.find_by_unique("email", email)

    def may_authenticate(self, user: Mapping[str, Any]) -> None:
        """Permit only an active administrator, raising to refuse."""
        if not user.get("is_admin") or not user.get("is_active", True):
            raise AuthenticationRefused(REFUSAL_MESSAGE, error_code=REFUSAL_CODE)

    def claims_for(self, user: Mapping[str, Any]) -> Mapping[str, Any]:
        """The product's claims: the admin role and nothing else."""
        del user
        return {"roles": [ADMIN_ROLE]}

    def on_user_created(self, user: Mapping[str, Any], via: str) -> None:
        """No side effects to run. The verification email is the flow's job."""
        del user, via

    def create_user(
        self, *, email: str, attributes: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        """Create a Portfolio user row for a registration and return it.

        `is_admin` is `False`, so a self registered account exists and cannot
        sign in, which is why registration stays disabled for this product.
        """
        record = dict(attributes)
        record.pop("id", None)
        record["email"] = email
        record["username"] = self._available_username(email)
        record["is_admin"] = False
        record["is_active"] = True
        record.pop("hashed_password", None)
        return users.create(record)

    def mark_email_verified(self, user_id: str) -> None:
        """Record that this user's address is confirmed, on the `users` row.

        Raises when the id is unusable or the row is gone, since the link is already
        spent and a verification that did not happen must not be reported.
        """
        try:
            numeric_id = int(user_id)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"mark_email_verified was given {user_id!r}, which is not one of "
                "this product's integer user ids."
            ) from exc

        if users.update(numeric_id, {"email_verified": True}) is None:
            raise ValueError(
                f"mark_email_verified found no user with id {numeric_id}. The link "
                "was consumed, so the address is not verified and the user needs a "
                "new one."
            )

    def has_other_sign_in_method(self, user_id: str) -> bool:
        """Whether this user holds a sign-in method the package cannot see.

        `False` for Portfolio: every way into an account is a password
        credential or an OAuth link, and the caller counts both itself.
        """
        del user_id
        return False

    def user_repository(self) -> object:
        """Portfolio's users repository. Typed `object`, as the protocol has it."""
        return users

    def _available_username(self, email: str) -> str:
        """A unique username derived from the address's local part.

        Checking first turns a collision into a suffix rather than a failed
        write; the remaining race surfaces as a retryable `UniqueViolation`.
        """
        base = email.partition("@")[0].strip() or "user"
        if users.find_by_unique("username", base) is None:
            return base
        for suffix in range(2, USERNAME_ATTEMPTS + 2):
            candidate = f"{base}{suffix}"
            if users.find_by_unique("username", candidate) is None:
                return candidate
        raise ValueError(f"No username available for the local part {base!r}.")
