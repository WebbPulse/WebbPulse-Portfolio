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
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


@router.post("/login", response_model=Token)
async def login(user_credentials: UserLogin, request: Request):
    ip = client_ip(request)
    retry_after = login_limiter.retry_after(ip)
    if retry_after:
        return _too_many_requests(retry_after)

    user = users.find_by_unique("username", user_credentials.username)
    # `.get(...) or _DUMMY_HASH` rather than a subscript. Once
    # `scripts/clear_legacy_credentials.py` has run for an environment the
    # column is removed from the row outright, and a subscript would turn this
    # route from "refuses every password" into "500s on every attempt". The
    # dummy hash keeps the timing the same as a wrong password, which is the
    # reason it exists at all, so a cleared user and an unknown user are
    # indistinguishable from the outside.
    hashed = (user.get("hashed_password") if user else None) or _DUMMY_HASH
    if not user or not verify_password(user_credentials.password, hashed):
        failures = login_limiter.record_failure(ip)
        if failures >= login_limiter.max_failures:
            # The limiter fails open, so the second lookup can come back None
            # even though the first call reached the threshold. Fall back to the
            # configured window rather than emitting a null Retry-After.
            retry_after = login_limiter.retry_after(ip)
            return _too_many_requests(
                retry_after if retry_after else login_limiter.window_seconds
            )
        raise _unauthorized("Incorrect username or password")
    if not user.get("is_active", True):
        raise _unauthorized("User account is inactive")

    login_limiter.clear(ip)
    access_token = create_access_token(data={"sub": user["username"]})
    return {"access_token": access_token, "token_type": "bearer"}
