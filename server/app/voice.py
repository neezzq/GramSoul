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
    if settings.llm_backend != "fake":
        await prepare_model()  # the cache key names the model that will actually speak
    path = cache_path(current_model(), spec, instr, text)
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


# The speech model actually used: TTS_MODEL when OpenRouter has it, otherwise the best match from OpenRouter's
# own list of speech models (model ids there change: dated variants appear and disappear).
_resolved: dict = {"model": None, "voices": None, "at": 0.0, "tried": 0.0}
_PREFER = ("gpt-4o-mini-tts", "openai/", "tts")


def current_model() -> str:
    return _resolved["model"] or settings.tts_model


def _error_text(r: httpx.Response) -> str:
    try:
        msg = (r.json().get("error") or {}).get("message") or r.text
    except Exception:
        msg = r.text
    msg = " ".join(str(msg).split())
    low = msg.lower()
    # «0 endpoints … guardrail restrictions and data policy. We removed them for the following reasons: …»
    if "zdr" in low:
        return ("OpenRouter не пускает к модели озвучки: в настройках аккаунта включён режим Zero Data Retention "
                "(openrouter.ai/settings/privacy) — у этой модели нет провайдера без хранения данных")
    if "guardrail" in low or "data policy" in low:
        reasons = re.sub(r"^\s*\(an endpoint may have matched multiple reasons\)\s*:?\s*", "", msg.split("reasons", 1)[-1])
        return "OpenRouter не пускает к модели озвучки из-за настроек приватности или ограничений ключа: " + reasons[:220]
    return msg[:220]


async def _speech_models(client: httpx.AsyncClient, base: str, headers: dict) -> list[dict]:
    """[{id, voices}] of the speech models OpenRouter offers."""
    for path in ("/audio/speech/models", "/models?output_modalities=speech"):
        try:
            r = await client.get(base + path, headers=headers)
            if r.status_code != 200:
                continue
            data = r.json().get("data") or []
            out = []
            for m in data:
                mid = m.get("id") or m.get("slug")
                if not mid:
                    continue
                kinds = (m.get("architecture") or {}).get("output_modalities")
                if kinds is not None and not {"speech", "audio"} & set(kinds):
                    continue  # a text or image model (the filter of the general list was not applied)
                voices = m.get("supported_voices")
                if voices is None:
                    for ep in m.get("endpoints") or []:
                        voices = voices or ep.get("supported_voices")
                out.append({"id": mid, "voices": [str(v) for v in voices] if voices else None})
            if out:
                return out
        except (httpx.HTTPError, ValueError):
            continue
    return []


async def _resolve_model(client: httpx.AsyncClient, base: str, headers: dict, force: bool = False) -> None:
    now = time.time()
    if not force and ((_resolved["model"] and now - _resolved["at"] < 6 * 3600) or now - _resolved.get("tried", 0.0) < 600):
        return  # fresh, or the list could not be read a moment ago (do not ask again on every line)
    _resolved["tried"] = now
    models = await _speech_models(client, base, headers)
    if not models:
        return
    ids = [m["id"] for m in models]
    pick = None
    if settings.tts_model in ids:
        pick = settings.tts_model
    else:
        for key in _PREFER:
            pick = next((i for i in ids if key in i), None)
            if pick:
                break
        pick = pick or ids[0]
    _resolved.update(model=pick, voices=next(m["voices"] for m in models if m["id"] == pick), at=time.time())
    if pick != settings.tts_model:
        log.warning("TTS_MODEL %s is not offered; using %s", settings.tts_model, pick)


def _endpoint() -> tuple[str, dict]:
    base = (settings.tts_base_url or settings.openrouter_base_url).rstrip("/")
    headers = {"Authorization": f"Bearer {settings.tts_key}", "X-Title": "GramSoul", "Content-Type": "application/json"}
    return base, headers


async def prepare_model() -> None:
    """Finds out which speech model will be used (at most once in 6 hours; quietly keeps the old choice on errors)."""
    base, headers = _endpoint()
    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
        await _resolve_model(client, base, headers)


async def _openrouter_speech(text: str, voice: str, instr: str) -> bytes:
    base, headers = _endpoint()

    def body_for() -> dict:
        v = voice
        known = _resolved["voices"]
        if known and v not in known:  # this model has other voices: take the closest neutral one
            v = next((x for x in (settings.tts_default_voice, "alloy") if x in known), known[0])
        return {"model": current_model(), "input": text, "voice": v, "response_format": "mp3", "instructions": instr}

    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10.0, read=90.0, write=30.0, pool=10.0)) as client:
        try:
            await _resolve_model(client, base, headers)
            body = body_for()
            r = await client.post(base + "/audio/speech", json=body, headers=headers)
            if r.status_code in (400, 404) and "exist" in r.text.lower():
                # the model name went out of date: read OpenRouter's list again and retry once
                await _resolve_model(client, base, headers, force=True)
                body = body_for()
                r = await client.post(base + "/audio/speech", json=body, headers=headers)
            if r.status_code in (400, 422) and "instruction" in r.text.lower():
                body.pop("instructions")  # a model without style instructions: plain voice
                r = await client.post(base + "/audio/speech", json=body, headers=headers)
        except httpx.HTTPError as e:
            _problem(f"сервис озвучки не ответил ({type(e).__name__})")
            raise ApiError(502, "voice_failed", "Сервис озвучки не ответил. Попробуй ещё раз.")
    if r.status_code == 429:
        log.warning("tts 429: %s", r.text[:300])
        _problem("OpenRouter отклоняет запросы озвучки: слишком часто (лимит ключа или провайдера, ошибка 429)")
        raise ApiError(429, "voice_busy", "Сервис озвучки занят. Попробуй через минуту.")
    if r.status_code >= 400:
        # what exactly went wrong (key, balance, account privacy settings) is for the owner: the log and the
        # admin page; the player only learns that the voice-over is unavailable
        log.warning("tts %s: %s", r.status_code, r.text[:1200])
        if r.status_code == 401:
            _problem("OpenRouter не принял ключ (TTS_API_KEY / OPENROUTER_API_KEY)")
        elif r.status_code == 402:
            _problem("на балансе OpenRouter не хватает денег на озвучку")
        else:
            _problem(f"{_error_text(r)} (ошибка {r.status_code})")
        raise ApiError(502, "voice_failed", UNAVAILABLE)
    ctype = r.headers.get("content-type", "")
    if "json" in ctype or len(r.content) < 200:
        log.warning("tts unexpected answer %s: %s", ctype, r.text[:200])
        _problem(f"сервис озвучки вернул не аудио ({ctype or 'без типа'})")
        raise ApiError(502, "voice_failed", UNAVAILABLE)
    _last_problem.clear()
    _last_ok["at"] = int(time.time() * 1000)
    return r.content


UNAVAILABLE = "Озвучка сейчас недоступна. Попробуй позже."
_last_problem: dict = {}
_last_ok: dict = {"at": None}  # the last voice-over actually made by the service (lines from the cache do not count)


def _problem(text: str) -> None:
    _last_problem.update(at=int(time.time() * 1000), text=text)


def last_problem() -> dict | None:
    """The latest unresolved voice-over failure with its reason (for the admin page), or None. `ok_at` — when the
    service last made a voice-over: lines replayed from the cache do not clear the problem, so the admin sees
    whether anything worked after it."""
    return {**_last_problem, "ok_at": _last_ok["at"]} if _last_problem else None


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
