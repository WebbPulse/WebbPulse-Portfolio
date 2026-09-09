"""Password hashing and token verification, on top of `webbpulse.security`.

The hashing and signing halves of this module used to be written out here, on
`python-jose` and a hand rolled `[:72]` truncation. Both are now
`webbpulse.security`, and what is left is the adapter: the names the rest of
the backend already imports, and the two product decisions the package
deliberately does not make.

**What moved into the package.** `bcrypt.hashpw`, `bcrypt.checkpw`, the 72 byte
truncation and the JWT encode and decode. The truncation is gone from this file
rather than kept alongside the package's: `hash_password` and `verify_password`
truncate to 72 bytes themselves, on a byte boundary, so doing it twice would be
the same cut applied twice and doing it differently would be a bug.

**What stayed here, and why.** The package's `decode_token` returns the claims
mapping and raises `ExpiredToken` or `InvalidToken`. This backend's callers want
neither: `verify_token` has always returned the `sub` claim or `None`, folding
"expired", "forged", "malformed" and "no subject" into one answer, and
`get_current_user` turns that `None` into a 401. That collapse is kept exactly
as it was, because it is what the frontend's 401 handling in
`frontend/src/services/api.ts` is written against. The two exceptions are used
internally, where they are strictly better than `python-jose`'s single
`JWTError`: an expired token is now distinguishable from a forged one in the
log line, even though both still answer 401.

**`bearer_claims` is deliberately not adopted.** The package's FastAPI
dependency builds its own `HTTPBearer(auto_error=False)` and answers 401 when
the `Authorization` header is missing or is not a bearer scheme. This module's
`security` is `HTTPBearer()` with `auto_error` left on, which answers **403** to
those same two cases, and `tests/test_auth_hardening.py` pins that 403. Swapping
in the dependency would change the status code a `Basic` header gets, and the
detail shape with it, for no gain: the token verification underneath is already
the package's. Adopting it is a behaviour change to argue on its own, not a
side effect of moving hashing and signing into the package.
"""

from datetime import timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from webbpulse.security import (
    TokenError,
    create_token,
    decode_token,
    hash_password,
)
from webbpulse.security import (
    verify_password as _verify_password,
)

from ..config import settings
from ..db.entities import users
from .logging import logger


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Check a password against a stored bcrypt hash.

    `plain_password` is required to be a string here rather than in the package.
    `webbpulse.security.verify_password` answers `False` for a non-string, which
    is the right default for a library: a service that reaches it with `None`
    from a JSON body wants a failed login, not a 500. This backend never does.
    Every caller passes a Pydantic validated `str`, so a `None` arriving here is
    a programming error rather than a bad request, and the `TypeError` the old
    implementation raised is what says so at the call site instead of one frame
    deeper as a mysteriously failing login.
    """
    if not isinstance(plain_password, str):
        raise TypeError("password must be a string")
    return _verify_password(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password with bcrypt at the package's default cost.

    The cost is unchanged. `bcrypt.gensalt()`, which this used to call with no
    argument, defaults to 12, and `webbpulse.security.DEFAULT_ROUNDS` is also
    12, so every hash already stored verifies and every new hash matches the old
    ones in cost. `tests/test_security_compat.py` pins that against a hash
    written by the previous implementation.
    """
    return hash_password(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Sign `data` into an HS256 access token.

    The signature and the claims are byte for byte what `python-jose` produced:
    the same secret, the same algorithm, `exp` set from the same default when no
    `expires_delta` is given. The one addition is `iat`, which `create_token`
    always sets and nothing reads; it does not affect verification here or in
    any already-deployed function.
    """
    return create_token(
        data,
        settings.SECRET_KEY,
        expires_in=(
            expires_delta
            if expires_delta is not None
            else timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        ),
        algorithm=settings.ALGORITHM,
    )


def verify_token(token: str) -> Optional[str]:
    """The token's `sub` claim, or `None` if it cannot be trusted.

    Every failure is `None`, which is the contract `get_current_user` and the
    tests are written against. Expiry is separated from the rest only for the
    log line: it is the ordinary end of a session rather than something worth
    investigating, and folding the two together is what made the previous
    implementation's logs useless for telling a stale tab from a forged token.
    """
    try:
        payload = decode_token(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
    except TokenError as exc:
        logger.debug("Rejected bearer token", reason=type(exc).__name__)
        return None
    subject = payload.get("sub")
    return subject if isinstance(subject, str) else None


security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    username = verify_token(credentials.credentials)
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = users.find_by_unique("username", username)
    if not user or not user.get("is_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions"
        )
    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="User account is inactive"
        )
    return user


def require_admin(user: dict, message: str) -> None:
    if not user.get("is_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=message)
