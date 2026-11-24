"""OpenRouter client against a mocked API (format of streaming chat + image responses)."""
import base64
import io
import json

import httpx
import pytest

from app import llm


pytestmark = pytest.mark.asyncio


def _png() -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (255, 0, 128)).save(buf, "PNG")
    return buf.getvalue()


def make_transport(seen: list, status: int = 200, reasoning_400: bool = False):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append({"auth": request.headers.get("authorization"), "body": body})
        if reasoning_400 and "reasoning" in body:
            return httpx.Response(400, json={"error": {"message": "reasoning is not supported"}})
        if status != 200:
            return httpx.Response(status, json={"error": {"message": "nope"}})
        if body.get("modalities"):
            url = "data:image/png;base64," + base64.b64encode(_png()).decode()
            return httpx.Response(200, json={"choices": [{"message": {"content": "", "images": [
                {"type": "image_url", "image_url": {"url": url}}]}}]})
        sse = (": OPENROUTER PROCESSING\n\n"
               'data: {"choices":[{"delta":{"content":"Рассказчик: Ветер"}}]}\n\n'
               'data: {"choices":[{"delta":{"content":" стих."}}]}\n\n'
               'data: {"choices":[{"delta":{}}],"usage":{"prompt_tokens":120,"completion_tokens":7}}\n\n'
               "data: [DONE]\n\n")
        return httpx.Response(200, content=sse.encode(), headers={"content-type": "text/event-stream"})
    return httpx.MockTransport(handler)


@pytest.fixture
def cloud(monkeypatch):
    monkeypatch.setattr(llm.settings, "llm_backend", "ollama")
    monkeypatch.setattr(llm.settings, "openrouter_api_key", "sk-or-test")
    real = httpx.AsyncClient
    state = {"transport": None}

    def factory(*a, **kw):
        kw["transport"] = state["transport"]
        return real(*a, **kw)
    monkeypatch.setattr(llm.httpx, "AsyncClient", factory)
    return state


async def test_streaming_text(cloud):
    seen = []
    cloud["transport"] = make_transport(seen)
    pieces = []

    async def on_delta(p):
        pieces.append(p)
    r = await llm.chat([{"role": "user", "content": "hi"}], stop=["\nЯн:", "\nЛада:", "a", "b", "c"],
                       on_delta=on_delta, provider="cloud")
    assert r.text == "Рассказчик: Ветер стих." and pieces == ["Рассказчик: Ветер", " стих."]
    assert r.prompt_tokens == 120 and r.output_tokens == 7
    body = seen[0]["body"]
    assert seen[0]["auth"] == "Bearer sk-or-test"
    assert body["model"] == llm.settings.cloud_text_model and body["stream"] is True and len(body["stop"]) == 4
    assert body["reasoning"] == {"enabled": False}


async def test_reasoning_param_fallback(cloud):
    seen = []
    cloud["transport"] = make_transport(seen, reasoning_400=True)
    r = await llm.chat([{"role": "user", "content": "hi"}], provider="cloud")
    assert r.text.startswith("Рассказчик") and len(seen) == 2 and "reasoning" not in seen[1]["body"]


@pytest.mark.parametrize("status,needle", [(401, "ключ"), (402, "баланс"), (429, "много запросов")])
async def test_errors_are_readable(cloud, status, needle):
    cloud["transport"] = make_transport([], status=status)
    with pytest.raises(llm.LLMError) as e:
        await llm.chat([{"role": "user", "content": "hi"}], provider="cloud")
    assert needle in str(e.value)


async def test_image(cloud):
    seen = []
    cloud["transport"] = make_transport(seen)
    data = await llm.generate_image("маяк")
    assert data.startswith(b"\x89PNG")
    assert seen[0]["body"]["modalities"] == ["image", "text"]
    assert seen[0]["body"]["model"] == llm.settings.cloud_image_model


async def test_no_key(monkeypatch):
    monkeypatch.setattr(llm.settings, "llm_backend", "ollama")
    monkeypatch.setattr(llm.settings, "openrouter_api_key", "")
    with pytest.raises(llm.LLMError) as e:
        await llm.chat([{"role": "user", "content": "hi"}], provider="cloud")
    assert "нет ключа" in str(e.value)
