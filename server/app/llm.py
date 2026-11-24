"""LLM client: Ollama /api/chat with streaming, plus a deterministic fake used by
automated tests (LLM_BACKEND=fake)."""
from __future__ import annotations

import asyncio
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
               extra_options: dict | None = None) -> LLMResult:
    if settings.llm_backend == "fake":
        return await _fake_chat(messages, on_delta)
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
