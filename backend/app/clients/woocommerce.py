import time

import httpx
import structlog

from app.config import settings

logger = structlog.get_logger()


class WCServerError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(message)


class WCClientError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(message)


class WooCommerceClient:
    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "WooCommerceClient":
        # Basic Auth over HTTPS — simpler and correct for SSL endpoints
        self._client = httpx.AsyncClient(
            timeout=settings.WC_TIMEOUT,
            auth=(settings.WC_CONSUMER_KEY, settings.WC_CONSUMER_SECRET),
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, *args) -> None:
        if self._client:
            await self._client.aclose()

    async def _get(self, path: str, params: dict | None = None) -> dict | list:
        params = params or {}
        url = f"{settings.WC_BASE_URL}{path}"
        all_params = {**params}
        start = time.monotonic()
        try:
            resp = await self._client.get(url, params=all_params)
        except httpx.TimeoutException as exc:
            raise exc
        latency_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            "wc_request",
            wc_endpoint=path,
            status=resp.status_code,
            latency_ms=latency_ms,
        )
        if resp.status_code >= 500:
            raise WCServerError(resp.status_code, resp.text)
        if resp.status_code >= 400:
            raise WCClientError(resp.status_code, resp.text)
        return resp.json()


_wc_client: WooCommerceClient | None = None


async def get_wc_client() -> WooCommerceClient:
    global _wc_client
    if _wc_client is None or _wc_client._client is None:
        _wc_client = WooCommerceClient()
        _wc_client._client = httpx.AsyncClient(timeout=settings.WC_TIMEOUT)
    return _wc_client
