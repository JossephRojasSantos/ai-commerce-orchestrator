"""Tests para descarga/interpretación de adjuntos WhatsApp (Fase 3)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.integrations.whatsapp import media


def _mock_client(get_results):
    client = AsyncMock()
    client.get = AsyncMock(side_effect=get_results)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _resp(json_data=None, content=b""):
    r = MagicMock()
    r.json.return_value = json_data or {}
    r.content = content
    r.raise_for_status = MagicMock()
    return r


@pytest.mark.asyncio
async def test_download_media_success():
    meta = _resp({"url": "https://lookaside/x", "mime_type": "image/jpeg", "file_size": 1000})
    blob = _resp(content=b"IMGBYTES")
    with patch.object(media.httpx, "AsyncClient", return_value=_mock_client([meta, blob])):
        data, mime = await media.download_media("media1")
    assert data == b"IMGBYTES"
    assert mime == "image/jpeg"


@pytest.mark.asyncio
async def test_download_media_empty_id():
    data, mime = await media.download_media("")
    assert data == b"" and mime == ""


@pytest.mark.asyncio
async def test_download_media_too_large():
    meta = _resp({"url": "u", "mime_type": "image/jpeg", "file_size": 99_999_999})
    with patch.object(media.httpx, "AsyncClient", return_value=_mock_client([meta])):
        data, mime = await media.download_media("media1")
    assert data == b"" and mime == ""


@pytest.mark.asyncio
async def test_interpret_media_image_uses_vision():
    with patch(
        "app.integrations.whatsapp.media.multimodal_complete",
        new_callable=AsyncMock,
        return_value="una licuadora roja",
    ) as mc:
        out = await media.interpret_media("image", b"x", "image/jpeg")
    assert out == "una licuadora roja"
    content = mc.call_args.args[0]
    assert any(p["type"] == "image_url" for p in content)


@pytest.mark.asyncio
async def test_interpret_media_audio_uses_audio_model_and_format():
    with patch(
        "app.integrations.whatsapp.media.multimodal_complete",
        new_callable=AsyncMock,
        return_value="hola quiero info",
    ) as mc:
        out = await media.interpret_media("voice", b"x", "audio/ogg; codecs=opus")
    assert out == "hola quiero info"
    content = mc.call_args.args[0]
    assert content[1]["type"] == "input_audio"
    assert content[1]["input_audio"]["format"] == "ogg"


@pytest.mark.asyncio
async def test_interpret_media_empty_returns_empty():
    out = await media.interpret_media("image", b"", "image/jpeg")
    assert out == ""


@pytest.mark.asyncio
async def test_media_to_text_pipeline():
    with (
        patch.object(
            media, "download_media", new_callable=AsyncMock, return_value=(b"x", "image/jpeg")
        ),
        patch.object(media, "interpret_media", new_callable=AsyncMock, return_value="texto"),
    ):
        out = await media.media_to_text({"image": {"id": "m1"}}, "image")
    assert out == "texto"
