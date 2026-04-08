import httpx
import pytest
from app.clients.woocommerce import WooCommerceClient


@pytest.fixture
def client():
    c = WooCommerceClient()
    c._client = httpx.AsyncClient()
    return c


def test_oauth1_signature_format(client):
    params = {}
    url = "https://tiendamagica.shop/wp-json/wc/v3/products"
    oauth = client._sign("GET", url, params)
    assert "oauth_signature" in oauth
    assert oauth["oauth_signature_method"] == "HMAC-SHA256"
    assert "oauth_nonce" in oauth
    assert "oauth_timestamp" in oauth


def test_get_serializes_params(client):
    params = {"page": 1, "per_page": 10}
    oauth = client._sign("GET", "https://example.com/test", params)
    assert "oauth_consumer_key" in oauth


@pytest.mark.asyncio
async def test_context_manager_closes_client():
    async with WooCommerceClient() as c:
        assert c._client is not None
    assert c._client.is_closed
