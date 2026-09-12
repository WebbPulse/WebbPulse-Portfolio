"""Password hashing and token verification, on top of `webbpulse.security`.

The adapter layer: the names the rest of the backend imports, plus the two
product decisions the package leaves open, folding every token failure to 401.
"""

from datetime import timedelta
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from webbpulse.http import user_id_dependency
from webbpulse.log_context import set_span_context_attributes
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
from .identity_claims import identity_subject
from .logging import logger


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Check a password against a stored bcrypt hash.

    Raises on a non-string rather than answering `False`: every caller passes a
    validated `str`, so anything else is a programming error worth surfacing.
    """
    if not isinstance(plain_password, str):
        raise TypeError("password must be a string")
    return _verify_password(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password with bcrypt at the package's default cost."""
    return hash_password(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Sign `data` into an HS256 access token, expiring at the configured default."""
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

    Every failure answers `None`; the reason reaches the log line only.
    """
    try:
        payload = decode_token(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
    except TokenError as exc:
        logger.debug("Rejected bearer token", extra={"reason": type(exc).__name__})
        return None
    subject = payload.get("sub")
    return subject if isinstance(subject, str) else None


class IdentityAwareHTTPBearer(HTTPBearer):
    """`HTTPBearer` that does not refuse a request an authorizer already vouched for.

    When the gateway verified the token the credential is in the request context,
    so returning `None` lets the resolver that reads those claims run.
    """

    async def __call__(
        self, request: Request
    ) -> Optional[HTTPAuthorizationCredentials]:
        """The bearer credential, or `None` when verified claims are present."""
        if request.headers.get("authorization"):
            return await super().__call__(request)
        if identity_subject(request):
            return None
        return await super().__call__(request)


security = IdentityAwareHTTPBearer(scheme_name="HTTPBearer")
"""`scheme_name` pins the OpenAPI security scheme name, which FastAPI would otherwise
take from the class, so the published contract does not move."""


def _identity_user(request: Request) -> Optional[dict]:
    """The Portfolio admin an identity access token names, or `None`.

    The `sub` is the same integer id the legacy row has. The account checks are
    re-applied so a token minted before an account was disabled stops working.
    """
    subject = identity_subject(request)
    if not subject:
        return None
    try:
        user_id = int(subject)
    except (TypeError, ValueError):
        return None
    user = users.get(user_id)
    if not user or not user.get("is_admin"):
        return None
    if not user.get("is_active", True):
        return None
    return user


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """Resolve the caller to the admin user it names.

    Dual mode: the legacy HS256 bearer resolves first, and an identity token the
    gateway verified resolves to the same row when it does not.
    """
    username = verify_token(credentials.credentials) if credentials else None
    if not username:
        identity_user = _identity_user(request)
        if identity_user is not None:
            return identity_user
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


def _user_id(user: dict) -> object:
    """The id to bind, pulled out of the user mapping.

    `.get` rather than `[]`, so a row missing the key binds nothing and the
    request still succeeds.
    """
    return user.get("id")


_bind_user_id = user_id_dependency(get_current_user, extract=_user_id)
"""`get_current_user`, wrapped so the resolved id reaches the log context. Not in the
middleware, which runs before there is any token to resolve."""


async def CurrentUser(user: dict = Depends(_bind_user_id)) -> dict:
    """The dependency every authenticated route takes.

    Wraps the id binding and copies the bound values onto the active span, so a
    log line and a trace join on one string. A no-op when nothing is recording.
    """
    set_span_context_attributes()
    return user


def require_admin(user: dict, message: str) -> None:
    """Raise 403 with `message` unless the user is an administrator."""
    if not user.get("is_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=message)
