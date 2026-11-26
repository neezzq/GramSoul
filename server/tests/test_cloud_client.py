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


def make_transport(seen: list, status: int = 200, reasoning_400: bool = False, no_image_input: bool = False):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append({"auth": request.headers.get("authorization"), "body": body})
        if no_image_input and isinstance(body["messages"][0]["content"], list):
            return httpx.Response(400, json={"error": {"message": "image input is not supported"}})
        if reasoning_400 and "reasoning" in body:
            return httpx.Response(400, json={"error": {"message": "reasoning is not supported"}})
        if status != 200:
            return httpx.Response(status, json={"error": {"message": "nope"}})
        if body.get("modalities"):
            url = "data:image/png;base64," + base64.b64encode(_png()).decode()
            return httpx.Response(200, json={"choices": [{"message": {"content": "", "images": [
                {"type": "image_url", "image_url": {"url": url}}]}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 1290, "cost": 0.039}})
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
    img = await llm.generate_image("маяк")
    assert img.data.startswith(b"\x89PNG") and img.output_tokens == 1290 and img.cost == 0.039
    assert seen[0]["body"]["modalities"] == ["image", "text"]
    assert seen[0]["body"]["model"] == llm.settings.cloud_image_model


async def test_image_with_reference_portraits_and_fallback(cloud):
    seen = []
    cloud["transport"] = make_transport(seen)
    img = await llm.generate_image("сцена", references=[b"\xff\xd8jpeg-1", b"\xff\xd8jpeg-2"])
    parts = seen[0]["body"]["messages"][0]["content"]
    assert parts[0] == {"type": "text", "text": "сцена"}
    assert [p["type"] for p in parts[1:]] == ["image_url", "image_url"]
    assert parts[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert img.data.startswith(b"\x89PNG")
    # a model without image input: drawn from the text alone
    seen.clear()
    cloud["transport"] = make_transport(seen, no_image_input=True)
    img = await llm.generate_image("сцена", references=[b"x"])
    assert img.data.startswith(b"\x89PNG") and isinstance(seen[-1]["body"]["messages"][0]["content"], str)


async def test_no_key(monkeypatch):
    monkeypatch.setattr(llm.settings, "llm_backend", "ollama")
    monkeypatch.setattr(llm.settings, "openrouter_api_key", "")
    with pytest.raises(llm.LLMError) as e:
        await llm.chat([{"role": "user", "content": "hi"}], provider="cloud")
    assert "нет ключа" in str(e.value)
