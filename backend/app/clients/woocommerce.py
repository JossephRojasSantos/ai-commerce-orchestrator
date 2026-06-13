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


def _build_http_client() -> httpx.AsyncClient:
    # Credenciales como query params: LiteSpeed (Hostinger) descarta el
    # header Authorization antes de llegar a PHP, así que Basic Auth da 401
    return httpx.AsyncClient(
        timeout=settings.WC_TIMEOUT,
        params={
            "consumer_key": settings.WC_CONSUMER_KEY,
            "consumer_secret": settings.WC_CONSUMER_SECRET,
        },
        follow_redirects=True,
    )


class WooCommerceClient:
    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "WooCommerceClient":
        self._client = _build_http_client()
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

    async def _get_with_headers(self, path: str, params: dict | None = None) -> tuple[list, dict]:
        """Como _get pero devuelve también headers (X-WP-Total para paginación)."""
        url = f"{settings.WC_BASE_URL}{path}"
        resp = await self._client.get(url, params=params or {})
        if resp.status_code >= 500:
            raise WCServerError(resp.status_code, resp.text)
        if resp.status_code >= 400:
            raise WCClientError(resp.status_code, resp.text)
        return resp.json(), dict(resp.headers)

    async def _put(self, path: str, payload: dict) -> dict:
        url = f"{settings.WC_BASE_URL}{path}"
        start = time.monotonic()
        resp = await self._client.put(url, json=payload)
        latency_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            "wc_request",
            wc_endpoint=path,
            method="PUT",
            status=resp.status_code,
            latency_ms=latency_ms,
        )
        if resp.status_code >= 500:
            raise WCServerError(resp.status_code, resp.text)
        if resp.status_code >= 400:
            raise WCClientError(resp.status_code, resp.text)
        return resp.json()

    async def _post(self, path: str, payload: dict) -> dict:
        url = f"{settings.WC_BASE_URL}{path}"
        start = time.monotonic()
        resp = await self._client.post(url, json=payload)
        latency_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            "wc_request",
            wc_endpoint=path,
            method="POST",
            status=resp.status_code,
            latency_ms=latency_ms,
        )
        if resp.status_code >= 500:
            raise WCServerError(resp.status_code, resp.text)
        if resp.status_code >= 400:
            raise WCClientError(resp.status_code, resp.text)
        return resp.json()

    async def create_product(self, payload: dict) -> dict:
        return await self._post("/products", payload)

    async def find_product_by_sku(self, sku: str) -> dict | None:
        if not sku:
            return None
        data = await self._get("/products", {"sku": sku})
        return data[0] if isinstance(data, list) and data else None

    # ── Métodos admin (feature 012) ──────────────────────────

    async def list_orders(
        self,
        status: str | None = None,
        after: str | None = None,
        before: str | None = None,
        search: str | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list, int]:
        params: dict = {"page": page, "per_page": per_page, "orderby": "date", "order": "desc"}
        if status:
            params["status"] = status
        if after:
            params["after"] = after
        if before:
            params["before"] = before
        if search:
            params["search"] = search
        data, headers = await self._get_with_headers("/orders", params)
        total = int(headers.get("x-wp-total", len(data)))
        return data, total

    async def get_order_raw(self, order_id: int) -> dict:
        return await self._get(f"/orders/{order_id}")

    async def get_order_notes(self, order_id: int) -> list:
        return await self._get(f"/orders/{order_id}/notes")

    async def update_order(self, order_id: int, payload: dict) -> dict:
        return await self._put(f"/orders/{order_id}", payload)

    async def list_products_raw(self, per_page: int = 100) -> list:
        return await self._get("/products", {"per_page": per_page, "status": "any"})

    async def update_product(self, product_id: int, payload: dict) -> dict:
        return await self._put(f"/products/{product_id}", payload)

    async def get_product_raw(self, product_id: int) -> dict:
        return await self._get(f"/products/{product_id}")


_wc_client: WooCommerceClient | None = None


async def get_wc_client() -> WooCommerceClient:
    global _wc_client
    if _wc_client is None or _wc_client._client is None:
        _wc_client = WooCommerceClient()
        _wc_client._client = _build_http_client()
    return _wc_client
