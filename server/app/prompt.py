"""Prompt building for the role-play model and parsing of its output.

The model gets: the current character cards, world rules, the scene state
(location, who is present, recent actions), a short summary of old messages and
the last messages verbatim. Everything is trimmed to the configured context."""
from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass, field

NARRATOR = "Рассказчик"
NARRATOR_ALIASES = {"рассказчик", "narrator", "ведущий", "автор", "повествователь", "описание", "сцена"}

CHARS_PER_TOKEN = 2.0  # conservative: measured ~2.4 chars/token for Russian prompts with the Qwen tokenizer


@dataclass
class Card:
    id: int
    public_id: str
    role: str  # npc | hero
    name: str
    age: str = ""
    appearance: str = ""
    habits: str = ""
    personality: str = ""
    motivation: str = ""
    backstory: str = ""
    speech_style: str = ""
    relationships: dict[str, str] = field(default_factory=dict)  # target public_id -> text
    example_lines: str = ""
    version: int = 1


@dataclass
class Seat:
    nick: str
    hero_name: str
    hero: Card | None  # None when the story has no hero card for this seat


@dataclass
class HistoryItem:
    seq: int
    kind: str  # player | character | narrator | system
    speaker: str
    text: str


@dataclass
class PromptInput:
    title: str
    description: str
    world_rules: str
    location: str
    npcs: list[Card]
    seats: list[Seat]
    summary: str
    history: list[HistoryItem]  # visible messages, oldest first, already limited to the recent window
    facts: list[str]
    mode: str  # reply | continue | regenerate
    num_ctx: int
    num_predict: int
    rich: bool = False  # cloud model: longer, more detailed reactions and full character cards


@dataclass
class BuiltPrompt:
    messages: list[dict]
    stop: list[str]
    text: str  # flattened, stored for debugging / verification


def _cut(text: str, limit: int) -> str:
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut + "…"


def _name_of(public_id: str, cards: dict[str, Card], seats: list[Seat]) -> str | None:
    if public_id.startswith("seat:"):
        try:
            return seats[int(public_id[5:])].hero_name
        except (ValueError, IndexError):
            return None
    c = cards.get(public_id)
    return c.name if c else None


def _clip(text: str, limit: int) -> str:
    return _cut(text, limit).rstrip(" .;,")


FULL_FIELDS = [("Характер", "personality"), ("Речь", "speech_style"), ("Привычки", "habits"),
               ("Внешность", "appearance"), ("Мотивация", "motivation"), ("Прошлое", "backstory")]


def card_text(c: Card, all_cards: dict[str, Card], seats: list[Seat], level: int) -> str:
    """level 4 = full (cloud), 3 = rich, 2 = medium, 1 = short, 0 = name + personality only."""
    lim = {4: 700, 3: 150, 2: 100, 1: 70, 0: 60}[level]
    fields = FULL_FIELDS if level >= 2 else FULL_FIELDS[:3] if level == 1 else FULL_FIELDS[:1]
    parts = [c.name + (f" ({_clip(c.age, 20)})" if c.age.strip() else "")]
    for label, attr in fields:
        val = getattr(c, attr)
        if val and val.strip():
            parts.append(f"{label}: {_clip(val, lim)}")
    if level >= 1:
        rel = []
        for target, attitude in (c.relationships or {}).items():
            nm = _name_of(target, all_cards, seats)
            if nm and attitude and attitude.strip() and nm != c.name:
                rel.append(f"{nm} — {_clip(attitude, 250 if level >= 4 else 70 if level >= 2 else 45)}")
        if rel:
            parts.append("Отношение: " + "; ".join(rel))
    if level >= 2 and c.example_lines.strip():
        ex = [l.strip() for l in c.example_lines.splitlines() if l.strip()][:1 if level == 2 else 4 if level >= 4 else 2]
        if ex:
            parts.append("Пример: " + " / ".join(_clip(e, 90) for e in ex))
    return ". ".join(parts) + "."


def _format_history_line(h: HistoryItem) -> str:
    return f"{h.speaker}: {h.text.strip()}"


def present_names(inp: PromptInput) -> list[str]:
    heroes = [s.hero_name for s in inp.seats]
    recent_text = " ".join(h.text for h in inp.history[-8:])
    recent_speakers = {h.speaker for h in inp.history[-8:]}
    npcs = [c.name for c in inp.npcs
            if c.name in recent_speakers or (c.name[:-1] if len(c.name) >= 4 else c.name) in recent_text]
    if not npcs and inp.npcs:
        npcs = [inp.npcs[0].name]
    return heroes + npcs


def _system_prompt(inp: PromptInput, present: list[str], level: int, rules_lim: int, summary_lim: int) -> str:
    hero_names = [s.hero_name for s in inp.seats]
    npc_names = [c.name for c in inp.npcs]
    cards_by_pid = {c.public_id: c for c in inp.npcs}
    for s in inp.seats:
        if s.hero:
            cards_by_pid[s.hero.public_id] = s.hero
    lines = [
        f"Ты — рассказчик ролевой истории «{_clip(inp.title, 60)}» и говоришь за персонажей: "
        f"{', '.join(npc_names) or 'жители мира'}.",
    ]
    if hero_names:
        lines.append(
            f"Герои игроков: {', '.join(hero_names)}. За них пишут только сами игроки. Ты не пишешь их слова, "
            f"мысли, чувства и решения — только реакцию мира и своих персонажей на их поступки."
        )
    ex = npc_names[0] if npc_names else "Персонаж"
    if inp.rich:
        lines.append(
            "Отвечай по-русски, живо и подробно: 2–6 строк. Каждая строка начинается с имени и двоеточия. "
            f"«{NARRATOR}: …» — атмосферное описание событий, обстановки и ощущений (2–4 предложения); "
            "«Имя персонажа: …» — действия в *звёздочках*, реплика — с тире, строго в его манере речи. "
            "Реагируй на поступки героев конкретно, учитывай, где все находятся, кто рядом и что уже произошло. "
            "Двигай сюжет вперёд, не повторяй уже сказанное. Пример:\n"
            f"{NARRATOR}: Ветер стучит ставнями, пламя свечи дрожит.\n"
            f"{ex}: *оглядывается и понижает голос* — Слышишь? Кажется, кто-то идёт."
        )
    else:
        lines.append(
            f"Отвечай по-русски, 1–4 строки. Каждая строка начинается с имени и двоеточия. "
            f"Действия — в *звёздочках*, реплики — с тире. Пример:\n"
            f"{NARRATOR}: Ветер стучит ставнями, пламя свечи дрожит.\n"
            f"{ex}: *оглядывается и понижает голос* — Слышишь? Кажется, кто-то идёт."
        )
    if inp.world_rules.strip() and rules_lim > 0:
        lines.append("Мир: " + _clip(inp.world_rules, rules_lim) + ".")
    npc_block = []
    for c in sorted(inp.npcs, key=lambda c: c.name not in present):
        lvl = level if c.name in present else max(0, level - 2)
        npc_block.append("- " + card_text(c, cards_by_pid, inp.seats, lvl))
    if npc_block:
        lines.append("Твои персонажи:\n" + "\n".join(npc_block))
    hb = []
    for s in inp.seats:
        desc = ""
        if s.hero and level >= 1:
            lim_h = 300 if level >= 4 else 60
            bits = [b for b in (_clip(s.hero.personality, lim_h), _clip(s.hero.appearance, lim_h) if level >= 3 else "") if b]
            desc = (" — " + "; ".join(bits)) if bits else ""
        hb.append(f"- {s.hero_name}{desc} (игрок {s.nick})")
    if hb:
        lines.append("Герои игроков:\n" + "\n".join(hb))
    if inp.summary.strip() and summary_lim > 0:
        lines.append("Что было раньше: " + _clip(inp.summary, summary_lim) + ".")
    return "\n\n".join(lines)


def build(inp: PromptInput) -> BuiltPrompt:
    budget = int(max(800, (inp.num_ctx - inp.num_predict - 120) * CHARS_PER_TOKEN))
    hero_names = [s.hero_name for s in inp.seats]
    npc_names = [c.name for c in inp.npcs]
    present = present_names(inp)

    # scene state + instruction go last (keeps the system prefix cacheable)
    state = []
    if inp.location.strip():
        state.append("Место: " + _clip(inp.location, 150))
    if present:
        state.append("Рядом: " + ", ".join(present))
    if inp.facts:
        state.append("Уже произошло: " + "; ".join(_clip(f, 80) for f in inp.facts[-5:]))
    who = ", ".join([NARRATOR] + [n for n in npc_names if n in present][:3])
    if inp.mode == "continue":
        instr = f"Продолжи сцену — что происходит дальше? Пиши за: {who}."
    else:
        instr = f"Ответь на последний ход игроков. Пиши за: {who}."
    if hero_names:
        instr += f" Не пиши за героев игроков ({', '.join(hero_names)})."
    tail = ("[" + ". ".join(state) + "]\n" if state else "") + instr

    # the system prompt may use at most ~55% of the budget; shrink cards until it fits
    sys_budget = int(budget * 0.55)
    system = ""
    levels = ((3, 300, 600), (2, 220, 500), (2, 160, 400), (1, 140, 350), (0, 100, 300), (0, 0, 250))
    if inp.rich:
        levels = ((4, 2500, 3000),) + levels
    for level, rules_lim, summary_lim in levels:
        system = _system_prompt(inp, present, level, rules_lim, summary_lim)
        if len(system) <= sys_budget:
            break

    used = len(system) + len(tail) + 40
    kept: list[HistoryItem] = []
    for h in reversed(list(inp.history)):
        line = _format_history_line(h)
        if used + len(line) + 1 > budget:
            room = budget - used - len(h.speaker) - 4
            if room > 120 and not kept:
                kept.append(HistoryItem(h.seq, h.kind, h.speaker, _cut(h.text, room)))
            elif room > 200:
                kept.append(HistoryItem(h.seq, h.kind, h.speaker, "…" + h.text.strip()[-(room - 2):]))
            break
        kept.append(h)
        used += len(line) + 1
    kept.reverse()

    messages: list[dict] = [{"role": "system", "content": system}]
    for h in kept:
        role = "user" if h.kind == "player" else "assistant"
        line = _format_history_line(h)
        if messages[-1]["role"] == role:
            messages[-1]["content"] += "\n" + line
        else:
            messages.append({"role": role, "content": line})
    if messages[-1]["role"] == "user":
        messages[-1]["content"] += "\n\n" + tail
    else:
        messages.append({"role": "user", "content": tail})

    stop = ["<|im_end|>", "<|endoftext|>"]
    for hn in hero_names:
        stop += [f"\n{hn}:", f"\n{hn} :", f"\n**{hn}", f"\n[{hn}]"]
    flat = "\n\n".join(f"<{m['role']}>\n{m['content']}" for m in messages)
    return BuiltPrompt(messages=messages, stop=stop[:16], text=flat)


# ---------------------------------------------------------------------------
# Output parsing
# ---------------------------------------------------------------------------

_LINE_RE = re.compile(r"^\s*[-–—•]?\s*(?:\*\*|\[|«|\")?\s*([^:\]\*\n«»\"]{1,40}?)\s*(?:\*\*|\]|»|\")?\s*[:：]\s*(.*)$")


@dataclass
class ParsedLine:
    kind: str  # narrator | character
    name: str
    text: str


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().strip("*_[]()«»\"").casefold())


def _match(name: str, npcs: list[str], heroes: list[str]) -> tuple[str, str] | None:
    n = _norm(name)
    if not n:
        return None
    if n in NARRATOR_ALIASES:
        return ("narrator", NARRATOR)
    for h in heroes:
        if _norm(h) == n or _norm(h).split(" ")[0] == n:
            return ("hero", h)
    for c in npcs:
        cn = _norm(c)
        if cn == n or cn.split(" ")[0] == n or n.split(" ")[0] == cn.split(" ")[0]:
            return ("character", c)
    return None


def _clean_text(t: str) -> str:
    t = t.replace("<|im_end|>", "").replace("<|endoftext|>", "").strip()
    t = re.sub(r"\s+\n", "\n", t)
    # an unpaired * breaks the italic rendering — close it
    if t.count("*") % 2 == 1:
        t = t + "*"
    return t.strip()


def _norm_text(t: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", (t or "").casefold()).split())


def _is_repeat(text: str, history: list[str]) -> bool:
    """True if the model just copied something that is already in the scene."""
    n = _norm_text(text)
    if len(n) < 12:
        return False
    for h in history:
        hn = _norm_text(h)
        if not hn:
            continue
        # containment counts only between substantial texts: a short player line ("А", "да")
        # is a substring of almost any reply and must not make it a "repeat"
        if n == hn or (len(n) > 25 and len(hn) > 25 and (n in hn or hn in n)):
            return True
        if len(n) > 25 and difflib.SequenceMatcher(None, n, hn).ratio() > 0.85:
            return True
    return False


# Fragments of our own instructions / scene-state block that small models sometimes echo back.
_SERVICE_MARKERS = ("Место:", "Рядом:", "Уже произошло:", "Пиши за:", "Не пиши за", "Ответь на последний ход",
                    "Продолжи сцену", "Что было раньше:", "Герои игроков", "Твои персонажи:", "Не повторяй уже сказанное")


def _strip_service(line: str) -> str:
    """Cut an echoed instruction/state fragment out of a line of model output."""
    cut = len(line)
    for m in _SERVICE_MARKERS:
        i = line.find(m)
        if i != -1:
            cut = min(cut, i)
    if cut < len(line):
        line = line[:cut].rstrip(" ;,[")
        if line.startswith("[") and "]" not in line:
            line = line[1:]
    return line.strip()


def _is_fact_echo(text: str, facts: list[str]) -> bool:
    """True if the text only re-lists scene facts from the prompt ("Ива - смотрит в туман; Харитон - ...")."""
    if not facts:
        return False
    nf = [_norm_text(f) for f in facts if _norm_text(f)]
    segs = [_norm_text(x) for x in re.split(r"[;\n]", text.replace("*", "")) if _norm_text(x)]
    if not segs:
        return False
    for seg in segs:
        if not any(seg == f or (len(seg) > 12 and seg in f) or (f in seg and len(seg) <= len(f) * 1.3)
                   or difflib.SequenceMatcher(None, seg, f).ratio() > 0.85 for f in nf):
            return False
    return True


def parse_output(raw: str, npcs: list[str], heroes: list[str], max_messages: int = 6,
                 history: list[str] | None = None, facts: list[str] | None = None) -> list[ParsedLine]:
    """Split model output into narrator / character messages.

    Lines attributed to the players' heroes are dropped (the AI must not speak
    for them); unattributed text continues the previous speaker or becomes
    narration."""
    out: list[ParsedLine] = []
    skipping_hero = False
    for raw_line in (raw or "").splitlines():
        line = _strip_service(raw_line.strip())
        if not line:
            continue
        if line.startswith("<|") or line.lower().startswith(("assistant", "user", "system")):
            continue
        m = _LINE_RE.match(line)
        target = _match(m.group(1), npcs, heroes) if m else None
        if target:
            kind, name = target
            body = m.group(2).strip()
            # "Рассказчик: Лада: ..." — a nested label decides who is really speaking
            inner = _LINE_RE.match(body) if body else None
            inner_target = _match(inner.group(1), npcs, heroes) if inner else None
            if inner_target:
                kind, name = inner_target
                body = inner.group(2).strip()
            if kind == "hero":
                skipping_hero = True
                continue
            skipping_hero = False
            if not body:
                continue
            if out and out[-1].name == name:
                out[-1].text += "\n" + body
            else:
                out.append(ParsedLine(kind, name, body))
            continue
        if skipping_hero:
            continue
        if history and _is_repeat(line, history):
            continue  # an unlabelled line copied from the scene/instructions
        if m and not target and len(m.group(1).split()) <= 3 and m.group(1)[:1].isupper():
            # "Unknown Name: text" — keep the text as narration, drop the unknown label
            body = m.group(2).strip()
            if not body:
                continue
            line = body
        if out:
            out[-1].text += "\n" + line
        else:
            out.append(ParsedLine("narrator", NARRATOR, line))
    result = []
    seen: list[str] = list(history or [])
    for p in out:
        t = _clean_text(p.text)
        letters = sum(ch.isalpha() for ch in t.replace("*", ""))
        if len(t) < 2 or letters < 2:
            continue  # e.g. "Харитон: **"
        if _is_repeat(t, seen):
            continue  # copied an earlier line of the scene
        if _is_fact_echo(t, facts or []):
            continue  # re-listed the "Уже произошло" block instead of reacting
        seen.append(t)
        result.append(ParsedLine(p.kind, p.name, t[:1500]))
    return result[:max_messages]


# ---------------------------------------------------------------------------
# Scene facts and summaries
# ---------------------------------------------------------------------------

_ACTION_RE = re.compile(r"\*([^*]{3,160})\*")


def extract_facts(speaker: str, text: str) -> list[str]:
    if speaker == NARRATOR:
        return []
    facts = []
    for m in _ACTION_RE.finditer(text or ""):
        act = " ".join(m.group(1).split())
        if act:
            facts.append(f"{speaker} — {act}")
    return facts[:3]


def summary_messages(old_summary: str, items: list[HistoryItem], max_chars: int) -> list[dict]:
    lines = "\n".join(_cut(_format_history_line(h), 260) for h in items)
    sys = (
        "Ты кратко пересказываешь события ролевой истории. Пиши по-русски, 3–6 предложений, "
        "в прошедшем времени. Сохрани главное: где находятся герои, кто рядом, что произошло, "
        "кто что пообещал или узнал. Не придумывай нового."
    )
    user = ""
    if old_summary.strip():
        user += "Краткое содержание до этого:\n" + _cut(old_summary, max_chars) + "\n\n"
    user += "Новые события:\n" + lines + "\n\nНапиши обновлённое краткое содержание всей истории."
    return [{"role": "system", "content": sys}, {"role": "user", "content": user}]


def fallback_summary(old_summary: str, items: list[HistoryItem], max_chars: int) -> str:
    """Extractive summary used when the model fails: first sentence of each message."""
    bits = []
    for h in items:
        first = re.split(r"(?<=[.!?…])\s", h.text.strip(), maxsplit=1)[0]
        bits.append(f"{h.speaker}: {_cut(first, 90)}")
    text = (old_summary.strip() + " " + " ".join(bits)).strip()
    if len(text) > max_chars:
        text = "…" + text[-max_chars:]
    return text


def card_versions_json(npcs: list[Card], seats: list[Seat]) -> str:
    d = {c.public_id: c.version for c in npcs}
    for s in seats:
        if s.hero:
            d[s.hero.public_id] = s.hero.version
    return json.dumps(d, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Scene photo prompt (cloud image model)
# ---------------------------------------------------------------------------
def image_prompt(title: str, world_rules: str, location: str, characters: list[Card], recent: list[HistoryItem],
                 user_prompt: str) -> str:
    """What the player asked for comes first and wins; the scene only supplies looks and mood.
    Everyone in the picture is an adult (all characters are 18+)."""
    want = user_prompt.strip()
    if want:
        lines = [f"Нарисуй одну иллюстрацию: {_clip(want, 300)}.",
                 "Это главное: рисуй именно то, что просит игрок, даже если это другое место или момент, "
                 f"чем в текущей сцене ролевой истории «{_clip(title, 80)}». Сцену ниже используй только для "
                 "внешности персонажей, эпохи и настроения."]
    else:
        lines = [f"Нарисуй одну иллюстрацию к текущей сцене ролевой истории «{_clip(title, 80)}»."]
    if world_rules.strip():
        lines.append("Мир и эпоха: " + _clip(world_rules, 350) + ".")
    if location.strip() and not want:
        lines.append("Место: " + _clip(location, 250) + ".")
    looks = [f"{c.name} — {_clip(c.appearance, 220)}" for c in characters if c.appearance.strip()]
    if looks:
        lines.append("Внешность персонажей: " + "; ".join(looks) + ".")
    if recent:
        happening = " ".join(_cut(f"{h.speaker}: {h.text}", 220) for h in recent[-5:])
        lines.append(("Для настроения — что было в сцене: " if want else "Что происходит прямо сейчас: ")
                     + _clip(happening, 500 if want else 900) + ".")
    lines.append("Все люди на изображении — взрослые (18+), даже если в тексте их называют учениками, "
                 "студентами, юношами или девушками.")
    lines.append("Стиль: кинематографичная цифровая живопись, выразительный свет, вертикальный кадр. "
                 "Без текста, надписей, подписей и рамок на изображении.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Personal chat with one character (persona): the model *is* the character
# ---------------------------------------------------------------------------
@dataclass
class ChatPromptInput:
    name: str
    description: str
    personality: str
    backstory: str
    user_name: str
    setting: str
    summary: str
    history: list[HistoryItem]
    mode: str  # reply | continue
    num_ctx: int
    num_predict: int
    rich: bool = False


CHAT_STYLE = (
    "Как отвечать: на языке собеседника; действия и обстановку пиши в *звёздочках* (курсив), реплики — с тире; "
    "3–8 предложений; сохраняй характер и факты диалога; двигай сцену вперёд и не повторяй уже сказанное. "
    "Не подписывай ответ своим именем."
)


def _chat_system(inp: ChatPromptInput, lim: int, summary_lim: int) -> str:
    lines = [
        f"Ты — {inp.name}. Это ролевой чат: ты отвечаешь только за {inp.name} и окружающий мир "
        f"и никогда не пишешь слова, мысли и поступки собеседника ({inp.user_name})."
    ]
    if inp.description.strip():
        lines.append("О персонаже: " + _clip(inp.description, lim))
    if inp.personality.strip():
        lines.append("Характер: " + _clip(inp.personality, lim))
    if inp.backstory.strip():
        lines.append("Предыстория: " + _clip(inp.backstory, lim))
    if inp.setting.strip():
        lines.append("Мир и сцена: " + _clip(inp.setting, lim))
    if inp.summary.strip() and summary_lim > 0:
        lines.append("Что было раньше: " + _clip(inp.summary, summary_lim))
    lines.append(CHAT_STYLE)
    return "\n\n".join(lines)


def build_chat(inp: ChatPromptInput) -> BuiltPrompt:
    budget = int(max(800, (inp.num_ctx - inp.num_predict - 120) * CHARS_PER_TOKEN))
    system = ""
    for lim, summary_lim in (((2000, 3000),) if inp.rich else ()) + ((600, 800), (350, 500), (200, 300), (100, 200)):
        system = _chat_system(inp, lim, summary_lim)
        if len(system) <= int(budget * 0.55):
            break
    tail = (f"(Продолжи сцену от лица {inp.name}: что происходит дальше?)" if inp.mode == "continue" else "")
    used = len(system) + len(tail) + 40
    kept: list[HistoryItem] = []
    for h in reversed(list(inp.history)):
        n = len(h.text) + 8
        if used + n > budget:
            room = budget - used
            if room > 200 and not kept:
                kept.append(HistoryItem(h.seq, h.kind, h.speaker, "…" + h.text.strip()[-(room - 2):]))
            break
        kept.append(h)
        used += n
    kept.reverse()
    messages: list[dict] = [{"role": "system", "content": system}]
    for h in kept:
        role = "user" if h.kind == "player" else "assistant"
        text = h.text.strip()
        if messages[-1]["role"] == role:
            messages[-1]["content"] += "\n\n" + text
        else:
            messages.append({"role": role, "content": text})
    if tail:
        if messages[-1]["role"] == "user":
            messages[-1]["content"] += "\n\n" + tail
        else:
            messages.append({"role": "user", "content": tail})
    elif messages[-1]["role"] != "user":
        messages.append({"role": "user", "content": f"(Продолжи от лица {inp.name}.)"})
    stop = ["<|im_end|>", "<|endoftext|>", f"\n{inp.user_name}:", f"\n**{inp.user_name}"]
    flat = "\n\n".join(f"<{m['role']}>\n{m['content']}" for m in messages)
    return BuiltPrompt(messages=messages, stop=stop, text=flat)


def parse_chat_output(raw: str, name: str, user_names: list[str], history: list[str] | None = None) -> list[ParsedLine]:
    """One message from the character. Drops a leading "Name:" label and anything written for the player."""
    text = (raw or "").replace("<|im_end|>", "").replace("<|endoftext|>", "")
    keep: list[str] = []
    for line in text.splitlines():
        m = _LINE_RE.match(line.strip())
        if m:
            label = _norm(m.group(1))
            if any(label == _norm(u) for u in user_names):
                break  # the model started writing for the player
            if label == _norm(name) or label == _norm(NARRATOR):
                line = m.group(2)
        keep.append(line)
    out = _clean_text("\n".join(keep))
    if sum(ch.isalpha() for ch in out) < 2:
        return []
    if history and _is_repeat(out, history):
        return []
    return [ParsedLine("character", name, out[:4000])]


# ---------------------------------------------------------------------------
# "Подсказать варианты реплики": three short options for the player's next turn
# ---------------------------------------------------------------------------
SUGGEST_SYSTEM = (
    "Ты помогаешь игроку в ролевом чате. Предложи 3 разных коротких варианта его следующего хода — "
    "каждый до 25 слов: действие в *звёздочках* и/или реплика. Варианты разные по настроению "
    "(например: смелый, осторожный, неожиданный). Пиши на языке переписки, от лица игрока. "
    "Ответ — только JSON-массив из трёх строк."
)


def suggest_messages(hero: str, others: list[str], history: list[HistoryItem]) -> list[dict]:
    lines = "\n".join(_cut(_format_history_line(h), 300) for h in history[-12:])
    user = (f"Игрок пишет за: {hero}. Другие персонажи: {', '.join(others) or '—'}.\n\n"
            f"Последние сообщения:\n{lines}\n\nТри варианта следующего хода игрока ({hero}):")
    return [{"role": "system", "content": SUGGEST_SYSTEM}, {"role": "user", "content": user}]


def parse_suggestions(raw: str) -> list[str]:
    raw = (raw or "").strip()
    items: list[str] = []
    m = re.search(r"\[.*\]", raw, re.S)
    if m:
        try:
            data = json.loads(m.group(0))
            items = [str(x) for x in data if isinstance(x, (str, int, float))]
        except ValueError:
            items = []
    if not items:  # numbered / bulleted lines from small models
        for line in raw.splitlines():
            line = re.sub(r"^\s*(?:\d+[.)]|[-•*]\s)\s*", "", line).strip().strip('"«»').strip()
            if len(line) > 2 and not line.startswith(("[", "]", "```")):
                items.append(line)
    out = []
    for it in items:
        it = " ".join(it.split()).strip().strip('"')
        if it and it not in out:
            out.append(it[:220])
    return out[:3]
