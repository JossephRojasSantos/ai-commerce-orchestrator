import asyncio
from unittest.mock import MagicMock, patch

import httpx
import pytest
from app.clients.woocommerce import WooCommerceClient


@pytest.fixture
def client():
    c = WooCommerceClient()
    c._client = httpx.AsyncClient()
    return c


def test_client_uses_query_param_credentials():
    """Credenciales como query params — LiteSpeed descarta el header Authorization."""

    mock_cfg = MagicMock()
    mock_cfg.WC_CONSUMER_KEY = "ck_test"
    mock_cfg.WC_CONSUMER_SECRET = "cs_test"
    mock_cfg.WC_TIMEOUT = 10.0

    with patch("app.clients.woocommerce.settings", mock_cfg):

        async def run():
            async with WooCommerceClient() as c:
                return dict(c._client.params)

        params = asyncio.get_event_loop().run_until_complete(run())

    assert params["consumer_key"] == "ck_test"
    assert params["consumer_secret"] == "cs_test"


def test_client_has_no_oauth_sign():
    """OAuth signing removed — Basic Auth used instead."""
    assert not hasattr(WooCommerceClient(), "_sign")


@pytest.mark.asyncio
async def test_context_manager_closes_client():
    async with WooCommerceClient() as c:
        assert c._client is not None
    assert c._client.is_closed
