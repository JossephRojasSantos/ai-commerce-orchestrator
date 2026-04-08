import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.clients.woocommerce import WCServerError
from app.config import settings


def wc_retry(func):
    return retry(
        retry=retry_if_exception_type((httpx.TransportError, WCServerError)),
        wait=wait_exponential(multiplier=0.5, max=4),
        stop=stop_after_attempt(settings.WC_MAX_RETRIES),
        reraise=True,
    )(func)
