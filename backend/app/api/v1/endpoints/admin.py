from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse

from ....core.login_limiter import client_ip, login_limiter
from ....core.security import (
    create_access_token,
    get_password_hash,
    verify_password,
)
from ....db.entities import users
from ....schemas import Token, UserLogin

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
    hashed = user["hashed_password"] if user else _DUMMY_HASH
    if not user or not verify_password(user_credentials.password, hashed):
        failures = login_limiter.record_failure(ip)
        if failures >= login_limiter.max_failures:
            return _too_many_requests(login_limiter.retry_after(ip))
        raise _unauthorized("Incorrect username or password")
    if not user.get("is_active", True):
        raise _unauthorized("User account is inactive")

    login_limiter.clear(ip)
    access_token = create_access_token(data={"sub": user["username"]})
    return {"access_token": access_token, "token_type": "bearer"}
