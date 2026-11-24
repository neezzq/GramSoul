"""LLM clients: local Ollama (/api/chat, streaming), cloud OpenRouter (OpenAI-compatible
chat completions + image generation) and a deterministic fake for tests (LLM_BACKEND=fake).
The OpenRouter key is read from the server environment only."""
from __future__ import annotations

import asyncio
import base64
import io
import json
import re
import time
from dataclasses import dataclass
from typing import Awaitable, Callable

import httpx

from .config import settings


class LLMError(Exception):
    pass


@dataclass
class LLMResult:
    text: str
    prompt_tokens: int | None = None
    output_tokens: int | None = None
    prompt_ms: int | None = None
    output_ms: int | None = None
    total_ms: int | None = None


OnDelta = Callable[[str], Awaitable[None]]


def _options(num_predict: int | None = None, stop: list[str] | None = None, temperature: float | None = None,
             extra: dict | None = None) -> dict:
    opts = {
        "num_ctx": settings.llm_num_ctx,
        "num_predict": num_predict or settings.llm_num_predict,
        "temperature": settings.llm_temperature if temperature is None else temperature,
        "top_p": settings.llm_top_p,
        "repeat_penalty": settings.llm_repeat_penalty,
    }
    if settings.llm_num_thread > 0:
        opts["num_thread"] = settings.llm_num_thread
    if stop:
        opts["stop"] = stop
    if extra:
        opts.update(extra)
    return opts


async def chat(messages: list[dict], stop: list[str] | None = None, on_delta: OnDelta | None = None,
               num_predict: int | None = None, temperature: float | None = None,
               extra_options: dict | None = None, provider: str = "local") -> LLMResult:
    if settings.llm_backend == "fake":
        return await _fake_chat(messages, on_delta)
    if provider == "cloud":
        return await _cloud_chat(messages, stop, on_delta, num_predict, temperature)
    body = {
        "model": settings.llm_model,
        "messages": messages,
        "stream": True,
        "keep_alive": _keep_alive(),
        "options": _options(num_predict, stop, temperature, extra_options),
    }
    t0 = time.monotonic()
    text_parts: list[str] = []
    final: dict = {}
    timeout = httpx.Timeout(connect=10.0, read=float(settings.llm_timeout_s), write=30.0, pool=10.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", settings.ollama_url.rstrip("/") + "/api/chat", json=body) as resp:
                if resp.status_code != 200:
                    detail = (await resp.aread()).decode("utf-8", "replace")[:300]
                    raise LLMError(f"Ollama ответила {resp.status_code}: {detail}")
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if chunk.get("error"):
                        raise LLMError(str(chunk["error"])[:300])
                    piece = (chunk.get("message") or {}).get("content") or ""
                    if piece:
                        text_parts.append(piece)
                        if on_delta:
                            await on_delta(piece)
                    if chunk.get("done"):
                        final = chunk
                        break
                    if time.monotonic() - t0 > settings.llm_timeout_s:
                        raise LLMError("Превышено время генерации")
    except httpx.HTTPError as e:
        raise LLMError(f"Нет связи с моделью: {type(e).__name__}") from e
    text = "".join(text_parts)
    return LLMResult(
        text=text,
        prompt_tokens=final.get("prompt_eval_count"),
        output_tokens=final.get("eval_count"),
        prompt_ms=_ns_to_ms(final.get("prompt_eval_duration")),
        output_ms=_ns_to_ms(final.get("eval_duration")),
        total_ms=int((time.monotonic() - t0) * 1000),
    )


def _keep_alive():
    v = settings.llm_keep_alive
    try:
        return int(v)
    except ValueError:
        return v


def _ns_to_ms(v) -> int | None:
    return int(v / 1_000_000) if isinstance(v, (int, float)) else None


async def warmup() -> None:
    """Load the model into memory so the first player does not wait for it."""
    if settings.llm_backend == "fake":
        return
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(600.0)) as client:
            await client.post(settings.ollama_url.rstrip("/") + "/api/generate",
                              json={"model": settings.llm_model, "prompt": "", "keep_alive": _keep_alive()})
    except httpx.HTTPError:
        pass


async def model_available() -> bool:
    if settings.llm_backend == "fake":
        return True
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(settings.ollama_url.rstrip("/") + "/api/tags")
            names = {m.get("name") for m in r.json().get("models", [])}
            want = settings.llm_model
            return want in names or (want + ":latest") in names
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Cloud: OpenRouter
# ---------------------------------------------------------------------------
def _cloud_headers() -> dict:
    if not settings.openrouter_api_key:
        raise LLMError("Облачный ИИ не настроен на сервере (нет ключа OpenRouter)")
    return {"Authorization": f"Bearer {settings.openrouter_api_key}", "X-Title": "GramSoul",
            "Content-Type": "application/json"}


def _cloud_error(status: int, body: str) -> LLMError:
    try:
        msg = (json.loads(body).get("error") or {}).get("message") or body
    except Exception:
        msg = body
    msg = str(msg)[:200]
    if status == 401:
        return LLMError("OpenRouter не принял ключ — проверь OPENROUTER_API_KEY на сервере")
    if status == 402:
        return LLMError("На балансе OpenRouter закончились деньги")
    if status == 429:
        return LLMError("OpenRouter: слишком много запросов, попробуй через минуту")
    return LLMError(f"OpenRouter {status}: {msg}")


def _reasoning_param() -> dict | None:
    r = (settings.cloud_reasoning or "off").lower()
    if r in ("", "default"):
        return None
    if r == "off":
        return {"enabled": False}
    return {"effort": r, "exclude": True}


async def _cloud_chat(messages: list[dict], stop: list[str] | None, on_delta: OnDelta | None,
                      max_tokens: int | None, temperature: float | None) -> LLMResult:
    headers = _cloud_headers()
    body: dict = {
        "model": settings.cloud_text_model,
        "messages": messages,
        "stream": True,
        "max_tokens": max_tokens or settings.cloud_max_tokens,
        "temperature": settings.cloud_temperature if temperature is None else temperature,
        "usage": {"include": True},
    }
    if stop:
        body["stop"] = stop[:4]
    reasoning = _reasoning_param()
    if reasoning is not None:
        body["reasoning"] = reasoning
    url = settings.openrouter_base_url.rstrip("/") + "/chat/completions"
    t0 = time.monotonic()
    timeout = httpx.Timeout(connect=10.0, read=float(settings.cloud_timeout_s), write=30.0, pool=10.0)
    for attempt in range(2):
        parts: list[str] = []
        usage: dict = {}
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("POST", url, json=body, headers=headers) as resp:
                    if resp.status_code != 200:
                        raw = (await resp.aread()).decode("utf-8", "replace")
                        # some models refuse the reasoning switch — retry once without it
                        if attempt == 0 and resp.status_code == 400 and "reasoning" in raw.lower() and "reasoning" in body:
                            body.pop("reasoning", None)
                            continue
                        raise _cloud_error(resp.status_code, raw)
                    async for line in resp.aiter_lines():
                        if not line.startswith("data:"):
                            continue  # SSE comments such as ": OPENROUTER PROCESSING"
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        if chunk.get("error"):
                            raise LLMError("OpenRouter: " + str((chunk["error"] or {}).get("message", chunk["error"]))[:200])
                        if chunk.get("usage"):
                            usage = chunk["usage"]
                        for ch in chunk.get("choices") or []:
                            piece = (ch.get("delta") or {}).get("content") or ""
                            if piece:
                                parts.append(piece)
                                if on_delta:
                                    await on_delta(piece)
                        if time.monotonic() - t0 > settings.cloud_timeout_s:
                            raise LLMError("Превышено время генерации")
            break
        except httpx.HTTPError as e:
            raise LLMError(f"Нет связи с OpenRouter: {type(e).__name__}") from e
    return LLMResult(text="".join(parts), prompt_tokens=usage.get("prompt_tokens"),
                     output_tokens=usage.get("completion_tokens"), total_ms=int((time.monotonic() - t0) * 1000))


async def generate_image(prompt: str, aspect_ratio: str = "3:4") -> bytes:
    """Returns encoded image bytes (PNG/JPEG/WebP) from the cloud image model."""
    if settings.llm_backend == "fake":
        return _fake_image(prompt)
    headers = _cloud_headers()
    body = {
        "model": settings.cloud_image_model,
        "messages": [{"role": "user", "content": prompt}],
        "modalities": ["image", "text"],
        "image_config": {"aspect_ratio": aspect_ratio},
    }
    url = settings.openrouter_base_url.rstrip("/") + "/chat/completions"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10.0, read=180.0, write=30.0, pool=10.0)) as client:
            resp = await client.post(url, json=body, headers=headers)
    except httpx.HTTPError as e:
        raise LLMError(f"Нет связи с OpenRouter: {type(e).__name__}") from e
    if resp.status_code != 200:
        raise _cloud_error(resp.status_code, resp.text)
    data = resp.json()
    if data.get("error"):
        raise LLMError("OpenRouter: " + str((data["error"] or {}).get("message", data["error"]))[:200])
    for ch in data.get("choices") or []:
        msg = ch.get("message") or {}
        for img in msg.get("images") or []:
            url_ = ((img.get("image_url") or {}).get("url")) or ""
            if url_.startswith("data:") and "," in url_:
                return base64.b64decode(url_.split(",", 1)[1])
        # some providers put the data URL into content parts
        content = msg.get("content")
        if isinstance(content, list):
            for part in content:
                u = ((part or {}).get("image_url") or {}).get("url", "")
                if u.startswith("data:") and "," in u:
                    return base64.b64decode(u.split(",", 1)[1])
    raise LLMError("Модель не вернула картинку (возможно, запрос отклонён фильтром). Попробуй описать иначе.")


def _fake_image(prompt: str) -> bytes:
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (300, 400), (40, 10, 30))
    ImageDraw.Draw(img).text((10, 10), "fake", fill=(255, 80, 160))
    out = io.BytesIO()
    img.save(out, "PNG")
    return out.getvalue()


# ---------------------------------------------------------------------------
# Fake backend for tests. Behaviour can be steered from the player's text:
#   "#fail"  -> raises an error,  "#slow" -> takes ~2 s.
# ---------------------------------------------------------------------------
FAKE_COUNTER = {"n": 0}


async def _fake_chat(messages: list[dict], on_delta: OnDelta | None) -> LLMResult:
    FAKE_COUNTER["n"] += 1
    n = FAKE_COUNTER["n"]
    prefilled = messages[-1]["role"] == "assistant"
    if prefilled:
        messages = messages[:-1]
    last = messages[-1]["content"]
    system = messages[0]["content"]
    if "#onlyhero" in last and not prefilled:
        await asyncio.sleep(0.02)
        return LLMResult(text="Ян: *встаёт* Я пойду.", total_ms=5)
    if "#fail" in last:
        await asyncio.sleep(0.05)
        raise LLMError("Тестовая ошибка модели")
    if "#echo_system" in last:  # tests can inspect which prompt variant was used
        return LLMResult(text="Рассказчик: " + ("ОБЛАКО" if "подробно" in system else "ЛОКАЛЬНО") + f" №{n}")
    if system.startswith("Convert the character description"):
        return LLMResult(text="REFUSE" if "#refuse" in last else "An adult woman with silver hair and a green coat, calm smile.")
    if system.startswith("PERSONA_JSON"):
        if "#badjson" in last:
            return LLMResult(text="Не могу.")
        return LLMResult(text='Вот персонаж:\n```json\n' + json.dumps({
            "name": "Ветта", "description": "Хозяйка ночного маяка. " + last[:40],
            "personality": "Говорит тихо, с иронией.", "backstory": "Выросла на острове.",
            "first_message": "*Ты поднимаешься по лестнице маяка.* — Опоздал, — улыбается Ветта.",
            "tags": ["Маяк", "#мистика", "море"]}, ensure_ascii=False) + "\n```")
    if system.startswith("Ты помогаешь игроку в ролевом чате"):
        return LLMResult(text='["*улыбается* Привет!", "Кто ты такой?", "*молча кивает и садится рядом*"]')
    if system.startswith("Ты — ") and "Это ролевой чат" in system:  # personal chat with a persona
        if "#fail" in last:
            raise LLMError("Тестовая ошибка модели")
        name = system[5:].split(".")[0]
        import random as _r
        words = ["дождь", "чайник", "дверь", "свет", "ветер", "листья", "корица", "хлеб", "часы", "полночь", "море",
                 "фонарь", "книга", "кошка", "мост", "звезда", "песок", "ключ", "письмо", "шарф", "трамвай", "снег"]
        pick = _r.Random(n).sample(words, 7)
        text = f"*{name} улыбается: {', '.join(pick[:4])}.* — Ответ №{n}: {' и '.join(pick[4:])}."
        for piece in text.split(" "):
            await asyncio.sleep(0.002)
            if on_delta:
                await on_delta(piece + " ")
        return LLMResult(text=text, prompt_tokens=50, output_tokens=12, total_ms=5)
    if system.startswith("Ты кратко пересказываешь"):
        return LLMResult(text=f"Краткое содержание №{n}: герои беседовали.")
    m = re.search(r"Пиши за: Рассказчик(?:, ([^.]+))?\.", last)
    npc = (m.group(1).split(",")[0].strip() if m and m.group(1) else "Персонаж")
    text = f"Рассказчик: Ответ №{n}. Ветер стих.\n{npc}: *кивает* Слышу тебя. (№{n})"
    delay = 2.0 if "#slow" in last else 0.02
    for piece in text.split(" "):
        await asyncio.sleep(delay / 10)
        if on_delta:
            await on_delta(piece + " ")
    return LLMResult(text=text, prompt_tokens=100, output_tokens=20, prompt_ms=10, output_ms=10, total_ms=20)
