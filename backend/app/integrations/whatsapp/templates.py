"""
WhatsApp Message Template registry — AI-118.

Templates must be approved in Meta Business Manager before use in production.
While the app is in test mode, only test numbers can receive template messages.

Registered templates:
  - tm_bienvenida      : welcome message (category: MARKETING)
  - tm_estado_pedido   : order status update (category: UTILITY)
  - tm_confirmacion    : order confirmation (category: UTILITY)

To send a template:
    from app.integrations.whatsapp.client import send_template_message
    await send_template_message(phone, "tm_estado_pedido", {"order_id": "1234", "status": "en proceso"})
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class WATemplate:
    name: str
    language: str
    category: str
    variables: tuple[str, ...]


TEMPLATES: dict[str, WATemplate] = {
    "tm_bienvenida": WATemplate(
        name="tm_bienvenida",
        language="es",
        category="MARKETING",
        variables=(),
    ),
    "tm_estado_pedido": WATemplate(
        name="tm_estado_pedido",
        language="es",
        category="UTILITY",
        variables=("order_id", "status"),
    ),
    "tm_confirmacion": WATemplate(
        name="tm_confirmacion",
        language="es",
        category="UTILITY",
        variables=("order_id", "total"),
    ),
}


def get_template(name: str) -> WATemplate:
    if name not in TEMPLATES:
        raise KeyError(f"Template '{name}' not registered. Available: {list(TEMPLATES)}")
    return TEMPLATES[name]
