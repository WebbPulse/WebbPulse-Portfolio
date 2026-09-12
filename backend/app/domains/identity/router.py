"""The legacy login route: username and password for an access token."""

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse

from ...core.login_limiter import client_ip, login_limiter
from ...core.security import (
    create_access_token,
    get_password_hash,
    verify_password,
)
from .repository import users
from .schemas import Token, UserLogin

router = APIRouter()

_DUMMY_HASH = get_password_hash("timing-equalizer")


def _too_many_requests(retry_after: int) -> JSONResponse:
    """The 429 body and `Retry-After` header for a locked out caller."""
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "detail": "Too many failed login attempts. Please try again later.",
            "error": "Too Many Requests",
            "retry_after": retry_after,
        },
        headers={"Retry-After": str(retry_after)},
    )


def _unauthorized(detail: str) -> HTTPException:
    """A 401 that challenges for a bearer token."""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


@router.post("/login", response_model=Token)
async def login(user_credentials: UserLogin, request: Request):
    """Exchange a username and password for an access token.

    Every rejection costs one password verification against `_DUMMY_HASH`, so an
    unknown user and a wrong password are indistinguishable in response and timing.
    """
    ip = client_ip(request)
    retry_after = login_limiter.retry_after(ip)
    if retry_after:
        return _too_many_requests(retry_after)

    user = users.find_by_unique("username", user_credentials.username)
    hashed = (user.get("hashed_password") if user else None) or _DUMMY_HASH
    if not user or not verify_password(user_credentials.password, hashed):
        failures = login_limiter.record_failure(ip)
        if failures >= login_limiter.max_failures:
            retry_after = login_limiter.retry_after(ip)
            return _too_many_requests(retry_after if retry_after else login_limiter.window_seconds)
        raise _unauthorized("Incorrect username or password")
    if not user.get("is_active", True):
        raise _unauthorized("User account is inactive")

    login_limiter.clear(ip)
    access_token = create_access_token(data={"sub": user["username"]})
    return {"access_token": access_token, "token_type": "bearer"}
