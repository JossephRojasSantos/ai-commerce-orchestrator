"""Autenticación del panel de administración (feature 012).

Un solo administrador: hash pbkdf2 en settings, sesiones opacas en Redis con TTL
deslizante, y rate limit de login por IP (research R1).
"""

import base64
import hashlib
import hmac
import secrets
import struct
import time

import redis.asyncio as aioredis
import structlog
from fastapi import Header, HTTPException, Request

from app.config import settings

logger = structlog.get_logger()

_PBKDF2_ITERATIONS = 600_000
_SESSION_PREFIX = "admin_session:"
_FAIL_PREFIX = "admin_login_fail:"
_BLOCK_PREFIX = "admin_login_block:"
_MFA_PREFIX = "admin_mfa:"  # challenge: password verificado, falta 2º factor
_MFA_WACODE_PREFIX = "admin_mfa_wa:"  # código enviado por WhatsApp
_MFA_FAIL_PREFIX = "admin_mfa_fail:"  # intentos del 2º factor por challenge
_MAX_FAILS = 5
_FAIL_WINDOW = 600  # 10 min
_BLOCK_SECONDS = 900  # 15 min
_MFA_TTL = 300  # 5 min para completar el 2º factor
_MFA_MAX_FAILS = 5


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


# ── MFA: TOTP (RFC 6238) + respaldo por WhatsApp ─────────────


def mfa_enabled() -> bool:
    return bool(settings.ADMIN_TOTP_SECRET)


def _totp_at(secret_b32: str, moment: float, step: int = 30, digits: int = 6) -> str:
    counter = int(moment // step)
    pad = "=" * ((8 - len(secret_b32) % 8) % 8)
    key = base64.b32decode(secret_b32.upper() + pad)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % (10**digits)
    return str(code).zfill(digits)


def verify_totp(code: str, window: int = 1) -> bool:
    """Valida un código TOTP con tolerancia de ±window ventanas (deriva de reloj)."""
    if not settings.ADMIN_TOTP_SECRET or not code.isdigit():
        return False
    now = time.time()
    for drift in range(-window, window + 1):
        if hmac.compare_digest(_totp_at(settings.ADMIN_TOTP_SECRET, now + drift * 30), code):
            return True
    return False


async def create_mfa_challenge(ip: str) -> str:
    """Password verificado → emite challenge corto; el token de sesión NO se entrega aún."""
    token = secrets.token_urlsafe(24)
    r = _redis()
    try:
        await r.set(_MFA_PREFIX + token, ip, ex=_MFA_TTL)
    finally:
        await r.aclose()
    return token


async def _mfa_challenge_valid(token: str) -> bool:
    r = _redis()
    try:
        return bool(await r.get(_MFA_PREFIX + token))
    finally:
        await r.aclose()


async def send_whatsapp_code(token: str) -> bool:
    """Respaldo: envía un código de 6 dígitos al celular del admin por WhatsApp."""
    if not await _mfa_challenge_valid(token) or not settings.ADMIN_PHONE:
        return False
    code = f"{secrets.randbelow(1_000_000):06d}"
    r = _redis()
    try:
        await r.set(_MFA_WACODE_PREFIX + token, code, ex=_MFA_TTL)
    finally:
        await r.aclose()

    from app.integrations.whatsapp.client import send_text_message

    text = (
        f"🔐 Tu código de acceso al panel de Tienda Mágica es *{code}*. "
        "Vence en 5 minutos. Si no fuiste tú, ignora este mensaje."
    )
    result = await send_text_message(settings.ADMIN_PHONE, text)
    return result.status == "sent"


async def verify_second_factor(token: str, code: str) -> str | None:
    """Valida TOTP o código WhatsApp. Devuelve token de sesión si OK, o None.

    Bloquea el challenge tras _MFA_MAX_FAILS intentos para frenar fuerza bruta.
    """
    r = _redis()
    try:
        ip = await r.get(_MFA_PREFIX + token)
        if not ip:
            return None

        fail_key = _MFA_FAIL_PREFIX + token
        fails = int(await r.get(fail_key) or 0)
        if fails >= _MFA_MAX_FAILS:
            await r.delete(_MFA_PREFIX + token)
            return None

        wa_code = await r.get(_MFA_WACODE_PREFIX + token)
        ok = verify_totp(code) or (wa_code is not None and hmac.compare_digest(wa_code, code))
        if not ok:
            n = await r.incr(fail_key)
            if n == 1:
                await r.expire(fail_key, _MFA_TTL)
            return None

        # Éxito: limpiar challenge y emitir sesión
        await r.delete(_MFA_PREFIX + token, _MFA_WACODE_PREFIX + token, fail_key)
    finally:
        await r.aclose()
    return await create_session(ip)


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
