"""Voice-over of the characters' lines (text-to-speech through OpenRouter, OpenAI Audio Speech format).

Every character can have a voice (one of VOICES), a manner of speaking and a timbre; the last two go to the
model as plain-language instructions. Audio is cached on disk by (model, voice, instructions, text), so a
line that was played once costs nothing the next time."""
from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from dataclasses import dataclass

import httpx

from .common import ApiError
from .config import settings

log = logging.getLogger("fonar.voice")

# (id, label) — voices of gpt-4o-mini-tts; all of them speak Russian
VOICES: list[tuple[str, str]] = [
    ("alloy", "Alloy — нейтральный, ровный"),
    ("ash", "Ash — мужской, мягкий"),
    ("ballad", "Ballad — мужской, напевный"),
    ("cedar", "Cedar — мужской, глубокий"),
    ("coral", "Coral — женский, тёплый"),
    ("echo", "Echo — мужской, спокойный"),
    ("fable", "Fable — рассказчик, выразительный"),
    ("marin", "Marin — женский, естественный"),
    ("nova", "Nova — женский, живой"),
    ("onyx", "Onyx — мужской, низкий"),
    ("sage", "Sage — женский, спокойный"),
    ("shimmer", "Shimmer — женский, светлый"),
    ("verse", "Verse — мужской, эмоциональный"),
]
VOICE_IDS = {v for v, _ in VOICES}

MANNERS = ["спокойно и мягко", "тепло и нежно", "игриво, с улыбкой", "дерзко и насмешливо", "холодно и сдержанно",
           "взволнованно", "шёпотом, интимно", "устало и тихо", "уверенно и властно", "торжественно"]
TIMBRES = ["низкий, бархатный", "глубокий, с хрипотцой", "средний, чистый", "высокий, звонкий", "мягкий, тёплый",
           "грубоватый", "молодой, лёгкий", "зрелый, спокойный"]

MAX_CHARS = 1200


@dataclass
class VoiceSpec:
    voice: str
    manner: str = ""
    timbre: str = ""


def normalize(voice: str | None, manner: str | None, timbre: str | None) -> tuple[str, str, str]:
    v = (voice or "").strip()
    if v and v not in VOICE_IDS:
        raise ApiError(400, "bad_voice", "Неизвестный голос.")
    m = " ".join((manner or "").split())[:200]
    t = " ".join((timbre or "").split())[:200]
    return v, m, t


def instructions(spec: VoiceSpec, narrator: bool = False) -> str:
    parts = ["Говори по-русски естественно, как живой человек в ролевой истории, с паузами и интонацией по смыслу."]
    if narrator:
        parts.append("Ты — голос рассказчика: спокойно и образно описываешь происходящее.")
    if spec.manner:
        parts.append(f"Манера речи: {spec.manner}.")
    if spec.timbre:
        parts.append(f"Тембр и подача голоса: {spec.timbre}.")
    return " ".join(parts)


_STAR = re.compile(r"\*([^*]+)\*")


def spoken_parts(text: str) -> tuple[str, str]:
    """(what the character says, the narration in *stars*)."""
    speech = _STAR.sub(" ", text or "")
    speech = re.sub(r"^\s*[—–-]\s*", "", speech, flags=re.M)
    speech = " ".join(speech.split())
    acts = " ".join(" ".join(m.group(1).split()) for m in _STAR.finditer(text or ""))
    return speech, acts


def _cache_dir() -> str:
    return os.path.join(settings.data_dir, "voice")


def cache_path(model: str, spec: VoiceSpec, instr: str, text: str) -> str:
    h = hashlib.sha256("\x1f".join([model, spec.voice, instr, text]).encode()).hexdigest()
    return os.path.join(_cache_dir(), h + ".mp3")


def _silent_mp3(seconds: float = 0.5) -> bytes:
    # MPEG-1 Layer III, 128 kbit/s, 44.1 kHz frames of silence (for the fake backend in tests)
    frame = bytes([0xFF, 0xFB, 0x90, 0x64]) + bytes(413)
    return frame * max(1, int(seconds * 38))


@dataclass
class SpeechResult:
    data: bytes
    prompt_tokens: int  # characters (the admin page shows them as voice-over volume)
    output_tokens: int = 0
    cost: float = 0.0
    cached: bool = False


async def synthesize(text: str, spec: VoiceSpec, narrator: bool = False) -> SpeechResult:
    text = " ".join((text or "").split())[:MAX_CHARS]
    if not text:
        raise ApiError(400, "nothing_to_say", "Здесь нечего озвучивать.")
    if not settings.tts_available:
        raise ApiError(503, "voice_off", "Озвучка не настроена на сервере.")
    voice = spec.voice if spec.voice in VOICE_IDS else (settings.tts_narrator_voice if narrator else settings.tts_default_voice)
    spec = VoiceSpec(voice, spec.manner, spec.timbre)
    instr = instructions(spec, narrator)
    path = cache_path(settings.tts_model, spec, instr, text)
    try:
        with open(path, "rb") as f:
            return SpeechResult(f.read(), 0, cached=True)
    except OSError:
        pass
    if settings.llm_backend == "fake":
        data = _silent_mp3()
    else:
        data = await _openrouter_speech(text, spec.voice, instr)
    os.makedirs(_cache_dir(), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)
    return SpeechResult(data, len(text), cost=len(text) / 1_000_000 * settings.tts_usd_per_mchar)


async def _openrouter_speech(text: str, voice: str, instr: str) -> bytes:
    base = (settings.tts_base_url or settings.openrouter_base_url).rstrip("/")
    headers = {"Authorization": f"Bearer {settings.tts_key}", "X-Title": "GramSoul", "Content-Type": "application/json"}
    body = {"model": settings.tts_model, "input": text, "voice": voice, "response_format": "mp3", "instructions": instr}
    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10.0, read=90.0, write=30.0, pool=10.0)) as client:
        try:
            r = await client.post(base + "/audio/speech", json=body, headers=headers)
            if r.status_code in (400, 422) and "instruction" in r.text.lower():
                body.pop("instructions")  # a model without style instructions: plain voice
                r = await client.post(base + "/audio/speech", json=body, headers=headers)
        except httpx.HTTPError as e:
            raise ApiError(502, "voice_failed", f"Сервис озвучки не ответил ({type(e).__name__}). Попробуй ещё раз.")
    if r.status_code == 401:
        raise ApiError(502, "voice_key", "Сервис озвучки не принял ключ (TTS_API_KEY / OPENROUTER_API_KEY).")
    if r.status_code == 402:
        raise ApiError(502, "voice_balance", "На балансе OpenRouter не хватает денег на озвучку.")
    if r.status_code == 429:
        raise ApiError(429, "voice_busy", "Сервис озвучки занят. Попробуй через минуту.")
    if r.status_code >= 400:
        log.warning("tts %s: %s", r.status_code, r.text[:300])
        raise ApiError(502, "voice_failed", f"Озвучка не получилась (ошибка {r.status_code}).")
    ctype = r.headers.get("content-type", "")
    if "json" in ctype or len(r.content) < 200:
        log.warning("tts unexpected answer %s: %s", ctype, r.text[:200])
        raise ApiError(502, "voice_failed", "Сервис озвучки вернул не аудио.")
    return r.content


def clean_cache(max_age_days: int = 30) -> int:
    """Old cached audio is removed (lines are rarely replayed after a month)."""
    n = 0
    cutoff = time.time() - max_age_days * 86400
    try:
        names = os.listdir(_cache_dir())
    except OSError:
        return 0
    for name in names:
        p = os.path.join(_cache_dir(), name)
        try:
            if os.path.getmtime(p) < cutoff:
                os.remove(p)
                n += 1
        except OSError:
            pass
    return n
