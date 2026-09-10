"""`PortfolioIdentityHooks`: who may sign in here, and what a user record is.

Section 6.3 of `docs/identity-standard.md` draws the line this file sits on. The
package owns how signing in works, and the product owns who may sign in and what
they may do. Everything below is the second half, and it is deliberately short:
Portfolio has one administrator and no roles beyond that, so its policy is two
boolean columns and one claim.

## Why this lives in `app/composition/` and not in `app/domains/identity/`

The same two rules that put `composition/identity.py` here, checked by
`tests/test_domain_boundaries.py`: a module under `app/domains/` may not import
the composition root, and only a module that declares routes may import FastAPI.
This module declares no route, and it is wired into `build_identity_router` by
`composition/identity.py`, which is the composition root. The domain package
keeps its own `router.py` and its `POST /login`, untouched.

## The mapping, field by field

`may_authenticate` refuses unless the user is both `is_admin` and `is_active`.
That is section 8.2's prescription for this product, and it is the same pair
`app/core/security.py`'s `get_current_user` already enforces on every
authenticated request. Writing it twice is not duplication: the legacy resolver
guards the legacy token, this guards the M2 login, and the two flows are
independent until M9 retires the first.

`claims_for` returns `{"roles": ["admin"]}` and nothing else. Every user who
reaches `claims_for` has passed `may_authenticate`, so every one of them is an
administrator, and the claim exists so a consumer can branch on a role rather
than on the absence of one. It deliberately does not carry `username` or
`email`: section 3.3 fixes `sub` as the immutable id, and a mutable identifier
in a token is a value that goes stale in every copy of it.

`load_user_by_id` takes the `sub` claim, which is a string, and Portfolio's ids
are integers from the `meta` counter. It converts, and answers `None` rather
than raising on anything that is not an integer, because a `sub` that is not one
of this product's ids is a token for somebody else's user and "no such user" is
the honest answer. `include_inactive` is not passed: `Repository.get` defaults to
hiding soft deleted rows for repositories that soft delete, and `users` does not
soft delete, so every row it has is visible either way.

`load_user_by_email` is where this product's schema and the package's contract
actually disagree, and the disagreement is worth stating plainly.

The package guarantees the email arrives lowercased and stripped, and documents
that both products key an `email_lower-index` GSI on it. Portfolio has no such
index and no such column. Its uniqueness comes from `UNIQUE#users#email#<value>`
pointer items in `meta`, written verbatim from whatever case the row carried, so
`find_by_unique("email", value)` is an exact, case sensitive lookup.

The smallest faithful mapping is therefore a single `find_by_unique` on the
lowercased address the package already handed over, and no second lookup on any
other casing. Two reasons, in order of weight.

First, the package's contract is explicit that a hook must not lowercase again
against a case sensitive store, and the mirror of that warning is that it must
not go looking for other casings either: a fallback that tried the original case
would make "does this address have an account" answerable by trying two spellings
and timing the difference, which is exactly the enumeration oracle section 5.4
closes.

Second, the exposure is bounded and known. The only row in this table is the
seeded administrator, and it carries `ADMIN_EMAIL` from the `webbpulse-<env>/app`
secret. A mixed case value there is a row this hook will not find, so M2 login
will refuse an address the legacy `POST /api/v1/admin/login` still accepts, which
is a visible, harmless failure while both flows run side by side rather than a
silent one. The legacy flow looks up by username and is untouched by any of this.

Making that gap disappear properly is a migration, not a hook: an `email_lower`
attribute on the row, its own pointer item or GSI, and a backfill. That is M9's
work, when the cutover makes this the only login. `create_user` below writes the
lowercased address, so every row this milestone creates is already findable.

`create_user` fills in the columns Portfolio requires that the package does not
know about. `username` is required and unique here and the package has no concept
of one, so it derives from the email's local part with a numeric suffix on
collision. `is_admin` is `False`: a self registered account is not an
administrator, which means it registers successfully and then cannot sign in,
because `may_authenticate` refuses it. That is the correct behaviour for a single
administrator product and is why `IDENTITY_REGISTRATION_ENABLED` should stay off
in both environments; the hook is implemented anyway so the route is not a 500
if it is ever switched on.

`on_user_created` does nothing. There are no default rows to write and no email
to send until M3.

`user_repository` hands back `app.db.entities.users`. The package types the
return as `object` and no M2 flow calls it, so nothing here depends on it being
a `webbpulse.dynamodb.Repository`; Portfolio's `Repository` is its own class with
its own id allocator and its own pointer based uniqueness. If a later milestone
starts calling this expecting the package's interface, that is the milestone that
either adapts it or moves this table onto the package's repository, and either
is a change with a test rather than a silent shape mismatch.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from webbpulse.identity import AuthenticationRefused

from ..db.entities import users

#: What `may_authenticate` says when it refuses. One message for both failing
#: columns on purpose: section 5.4 requires login to answer identically whether
#: the account is missing, not an administrator, or deactivated, and a message
#: that distinguished them would put that distinction in front of an attacker.
REFUSAL_MESSAGE = "This account may not sign in."
REFUSAL_CODE = "NOT_AN_ADMINISTRATOR"

#: The claim every authenticated user of this product carries. A list rather
#: than a string so a consumer's check is the same shape it would be in a
#: product that has more than one role.
ADMIN_ROLE = "admin"

#: How many suffixed usernames `create_user` will try before giving up. A
#: collision needs a different username, not a retry loop: past this the address
#: is pathological and failing the registration is better than spinning.
USERNAME_ATTEMPTS = 100


class PortfolioIdentityHooks:
    """Portfolio's `IdentityHooks`, satisfying the protocol structurally.

    Not a `BaseIdentityHooks` subclass. The protocol is `runtime_checkable` and
    every hook on it is implemented here, so inheriting would buy only the
    `HookNotImplemented` fallbacks for methods that do not need them, at the cost
    of an import time coupling to the package's class. `tests/test_identity_m2.py`
    asserts `isinstance(hooks, IdentityHooks)` so the structural claim is checked
    rather than assumed.

    Stateless, so one instance is built per process and shared. Every method goes
    through `app.db.entities.users`, whose table resource is resolved per call by
    `app.db.client`, so nothing here caches a boto3 object across a Lambda freeze.
    """

    def load_user_by_id(self, user_id: str) -> Mapping[str, Any] | None:
        """The user whose id is this `sub`, or `None`.

        A `sub` that is not an integer is not one of this product's ids, so it
        gets the same `None` a missing row does rather than a `ValueError` that
        would surface as a 500 on a token this service simply did not mint.
        """
        try:
            numeric_id = int(user_id)
        except (TypeError, ValueError):
            return None
        return users.get(numeric_id)

    def load_user_by_email(self, email: str) -> Mapping[str, Any] | None:
        """The user with this address, or `None`.

        `email` is already lowercased and stripped by the package, and this does
        not lowercase it again or try any other casing. See the module docstring
        for why the exact match is the whole implementation and what it costs.

        One `meta` GetItem followed by one `users` GetItem when the pointer
        exists, which is the same shape the found and not found paths would have
        under any index: the package equalises the password verification, and a
        lookup that is one round trip shorter when it finds nothing is not a
        timing signal a bcrypt round leaves visible.
        """
        return users.find_by_unique("email", email)

    def may_authenticate(self, user: Mapping[str, Any]) -> None:
        """Permit only an active administrator. Section 8.2.

        Returns `None` to permit and raises to refuse, which is the protocol's
        shape and the one where forgetting to return lands on the refusing side.
        """
        if not user.get("is_admin") or not user.get("is_active", True):
            raise AuthenticationRefused(REFUSAL_MESSAGE, error_code=REFUSAL_CODE)

    def claims_for(self, user: Mapping[str, Any]) -> Mapping[str, Any]:
        """The product's claims: the admin role and nothing else."""
        del user  # Everybody who reaches here passed `may_authenticate`.
        return {"roles": [ADMIN_ROLE]}

    def on_user_created(self, user: Mapping[str, Any], via: str) -> None:
        """No side effects to run. M3's verification email is the first one."""
        del user, via

    def create_user(
        self, *, email: str, attributes: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        """Create a Portfolio user row for a registration and return it.

        `is_admin` is `False`, so the account exists and cannot sign in. See the
        module docstring: that is the correct answer for a product with one
        administrator, and it is why registration stays disabled.

        The returned mapping carries `id` as the integer the counter allocated.
        The package stringifies it for the `sub` claim and for the credential's
        partition key, and `load_user_by_id` converts back, so the two ends agree
        without this row growing a second id in a second type.
        """
        record = dict(attributes)
        record.pop("id", None)
        record["email"] = email
        record["username"] = self._available_username(email)
        record["is_admin"] = False
        record["is_active"] = True
        # The password lives in the `credentials` table, which the package writes
        # immediately after this returns. `hashed_password` is the legacy flow's
        # column and is deliberately not set: a row with neither an M2 credential
        # nor a legacy hash cannot be signed in by either flow, and a row with a
        # placeholder in that column could be.
        record.pop("hashed_password", None)
        return users.create(record)

    def user_repository(self) -> object:
        """Portfolio's users repository. Typed `object`, as the protocol has it."""
        return users

    def _available_username(self, email: str) -> str:
        """A unique username derived from the address's local part.

        Portfolio requires a username and enforces its uniqueness with a pointer
        item, so a colliding one fails the whole `TransactWriteItems` rather than
        one attribute. Checking first turns that into a suffix instead of an
        error the registrant cannot act on.

        There is still a race between the check and the create, and it is not
        worth closing: two registrations for the same local part in the same
        instant fail the second one with a `UniqueViolation`, which the flow
        surfaces as a failed registration the caller can retry.
        """
        base = email.partition("@")[0].strip() or "user"
        if users.find_by_unique("username", base) is None:
            return base
        for suffix in range(2, USERNAME_ATTEMPTS + 2):
            candidate = f"{base}{suffix}"
            if users.find_by_unique("username", candidate) is None:
                return candidate
        raise ValueError(f"No username available for the local part {base!r}.")
