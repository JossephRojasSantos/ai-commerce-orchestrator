"""Autenticación del panel de administración (feature 012).

Un solo administrador: hash pbkdf2 en settings, sesiones opacas en Redis con TTL
deslizante, y rate limit de login por IP (research R1).
"""

import hashlib
import hmac
import secrets

import redis.asyncio as aioredis
import structlog
from fastapi import Header, HTTPException, Request

from app.config import settings

logger = structlog.get_logger()

_PBKDF2_ITERATIONS = 600_000
_SESSION_PREFIX = "admin_session:"
_FAIL_PREFIX = "admin_login_fail:"
_BLOCK_PREFIX = "admin_login_block:"
_MAX_FAILS = 5
_FAIL_WINDOW = 600  # 10 min
_BLOCK_SECONDS = 900  # 15 min


def _redis():
    return aioredis.from_url(settings.REDIS_URL, decode_responses=True)


def hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _PBKDF2_ITERATIONS).hex()


def verify_password(password: str) -> bool:
    if not settings.ADMIN_PASSWORD_HASH or not settings.ADMIN_PASSWORD_SALT:
        return False
    candidate = hash_password(password, settings.ADMIN_PASSWORD_SALT)
    return hmac.compare_digest(candidate, settings.ADMIN_PASSWORD_HASH)


async def check_login_blocked(ip: str) -> bool:
    r = _redis()
    try:
        return bool(await r.get(_BLOCK_PREFIX + ip))
    finally:
        await r.aclose()


async def register_login_failure(ip: str) -> None:
    r = _redis()
    try:
        key = _FAIL_PREFIX + ip
        count = await r.incr(key)
        if count == 1:
            await r.expire(key, _FAIL_WINDOW)
        if count >= _MAX_FAILS:
            await r.set(_BLOCK_PREFIX + ip, "1", ex=_BLOCK_SECONDS)
            logger.warning("admin.login_blocked", ip=ip)
    finally:
        await r.aclose()


async def create_session(ip: str) -> str:
    token = secrets.token_urlsafe(32)
    r = _redis()
    try:
        await r.set(_SESSION_PREFIX + token, ip, ex=settings.ADMIN_SESSION_TTL)
        await r.delete(_FAIL_PREFIX + ip)
    finally:
        await r.aclose()
    logger.info("admin.session_created")
    return token


async def destroy_session(token: str) -> None:
    r = _redis()
    try:
        await r.delete(_SESSION_PREFIX + token)
    finally:
        await r.aclose()


async def require_admin_session(
    request: Request,
    authorization: str = Header(..., alias="Authorization"),
) -> str:
    """Dependency: valida el token de sesión y renueva su TTL (sliding)."""
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="unauthorized")

    r = _redis()
    try:
        key = _SESSION_PREFIX + token
        exists = await r.get(key)
        if not exists:
            raise HTTPException(status_code=401, detail="unauthorized")
        await r.expire(key, settings.ADMIN_SESSION_TTL)
    finally:
        await r.aclose()
    return token
