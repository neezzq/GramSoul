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
    """level 3 = rich, 2 = medium, 1 = short, 0 = name + personality only."""
    lim = {3: 150, 2: 100, 1: 70, 0: 60}[level]
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
                rel.append(f"{nm} — {_clip(attitude, 70 if level >= 2 else 45)}")
        if rel:
            parts.append("Отношение: " + "; ".join(rel))
    if level >= 2 and c.example_lines.strip():
        ex = [l.strip() for l in c.example_lines.splitlines() if l.strip()][:1 if level == 2 else 2]
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
    lines.append(
        f"Отвечай по-русски, 1–4 строки. Каждая строка начинается с имени и двоеточия. "
        f"Действия — в *звёздочках*, речь — без них. Пример:\n"
        f"{NARRATOR}: Ветер стучит ставнями, пламя свечи дрожит.\n"
        f"{ex}: *оглядывается и понижает голос* Слышишь? Кажется, кто-то идёт."
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
            bits = [b for b in (_clip(s.hero.personality, 60), _clip(s.hero.appearance, 60) if level >= 3 else "") if b]
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
    for level, rules_lim, summary_lim in ((3, 300, 600), (2, 220, 500), (2, 160, 400), (1, 140, 350), (0, 100, 300), (0, 0, 250)):
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
        if n == hn or (len(n) > 25 and (n in hn or hn in n)):
            return True
        if len(n) > 25 and difflib.SequenceMatcher(None, n, hn).ratio() > 0.85:
            return True
    return False


def parse_output(raw: str, npcs: list[str], heroes: list[str], max_messages: int = 6,
                 history: list[str] | None = None) -> list[ParsedLine]:
    """Split model output into narrator / character messages.

    Lines attributed to the players' heroes are dropped (the AI must not speak
    for them); unattributed text continues the previous speaker or becomes
    narration."""
    out: list[ParsedLine] = []
    skipping_hero = False
    for raw_line in (raw or "").splitlines():
        line = raw_line.strip()
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
