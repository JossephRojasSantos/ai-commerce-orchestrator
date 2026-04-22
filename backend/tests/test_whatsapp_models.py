"""Coverage for app/integrations/whatsapp/models.py"""
from app.integrations.whatsapp.models import (
    WAIncomingMessage,
    WASendResult,
    WATextMessage,
    WAWebhookChange,
    WAWebhookEntry,
    WAWebhookPayload,
    WAWebhookValue,
)


def test_wa_text_message():
    m = WATextMessage(body="hola")
    assert m.body == "hola"


def test_wa_incoming_message_text():
    msg = WAIncomingMessage(id="id1", from_="521234567890", type="text", text=WATextMessage(body="test"))
    assert msg.from_ == "521234567890"
    assert msg.type == "text"
    assert msg.text.body == "test"


def test_wa_incoming_message_no_text():
    msg = WAIncomingMessage(id="id2", from_="521234567890", type="image")
    assert msg.text is None


def test_wa_webhook_value_no_messages():
    v = WAWebhookValue()
    assert v.messages is None


def test_wa_webhook_value_with_messages():
    msg = WAIncomingMessage(id="id3", from_="5200", type="text", text=WATextMessage(body="x"))
    v = WAWebhookValue(messages=[msg])
    assert len(v.messages) == 1


def test_wa_webhook_change():
    c = WAWebhookChange(field="messages", value=WAWebhookValue())
    assert c.field == "messages"


def test_wa_webhook_entry():
    change = WAWebhookChange(field="messages", value=WAWebhookValue())
    entry = WAWebhookEntry(id="eid", changes=[change])
    assert entry.id == "eid"
    assert len(entry.changes) == 1


def test_wa_webhook_payload():
    change = WAWebhookChange(field="messages", value=WAWebhookValue())
    entry = WAWebhookEntry(id="eid", changes=[change])
    payload = WAWebhookPayload(object="whatsapp_business_account", entry=[entry])
    assert payload.object == "whatsapp_business_account"


def test_wa_send_result_sent():
    r = WASendResult(message_id="msg123", status="sent")
    assert r.status == "sent"
    assert r.error is None


def test_wa_send_result_failed():
    r = WASendResult(message_id="", status="failed", error="timeout")
    assert r.status == "failed"
    assert r.error == "timeout"
