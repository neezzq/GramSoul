"""Stories and character cards."""
from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from . import demo
from .common import ApiError, User, hub, new_id, not_found
from .config import settings
from .db import Database, now_ms

CARD_FIELDS = ("age", "appearance", "habits", "personality", "motivation", "backstory", "speech_style", "example_lines")
FIELD_LIMITS = {"age": 40, "appearance": 1500, "habits": 1500, "personality": 1500, "motivation": 1500,
                "backstory": 3000, "speech_style": 1000, "example_lines": 1500}


class CharacterIn(BaseModel):
    id: str | None = None
    key: str | None = None
    role: str = "npc"
    name: str = Field(min_length=1, max_length=40)
    avatar_image_id: str | None = None
    age: str = ""
    appearance: str = ""
    habits: str = ""
    personality: str = ""
    motivation: str = ""
    backstory: str = ""
    speech_style: str = ""
    relationships: dict[str, str] = Field(default_factory=dict)
    example_lines: str = ""


class StartMessageIn(BaseModel):
    speaker: str = "narrator"
    text: str = Field(min_length=1, max_length=1500)


class StoryIn(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=1500)
    intro: str = Field(default="", max_length=2000)
    world_rules: str = Field(default="", max_length=3000)
    start_scene: str = Field(default="", max_length=1000)
    cover_image_id: str | None = None
    characters: list[CharacterIn] = Field(default_factory=list)
    start_messages: list[StartMessageIn] = Field(default_factory=list)


class QuickStoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    avatar_image_id: str | None = None
    personality: str = Field(default="", max_length=1500)
    speech_style: str = Field(default="", max_length=1000)
    start_line: str = Field(default="", max_length=1500)


class CharacterPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=40)
    avatar_image_id: str | None = None
    clear_avatar: bool = False
    age: str | None = None
    appearance: str | None = None
    habits: str | None = None
    personality: str | None = None
    motivation: str | None = None
    backstory: str | None = None
    speech_style: str | None = None
    relationships: dict[str, str] | None = None
    example_lines: str | None = None


# ---------------------------------------------------------------------------
def _check_image(db: Database, user: User, image_id: str | None) -> str | None:
    if not image_id:
        return None
    row = db.one("SELECT owner_id FROM images WHERE id=?", (image_id,))
    if not row or row["owner_id"] != user.id:
        raise ApiError(400, "bad_image", "Изображение не найдено. Загрузи его ещё раз.")
    return image_id


def _check_fields(c: CharacterIn | CharacterPatch) -> None:
    for f, lim in FIELD_LIMITS.items():
        v = getattr(c, f, None)
        if v is not None and len(v) > lim:
            raise ApiError(400, "too_long", f"Поле слишком длинное (максимум {lim} символов).")
    rel = getattr(c, "relationships", None) or {}
    if len(rel) > 12 or any(len(v) > 500 for v in rel.values()):
        raise ApiError(400, "too_long", "Слишком длинное описание отношений.")


def story_row(db: Database, user: User, story_pid: str):
    row = db.one("SELECT * FROM stories WHERE public_id=?", (story_pid,))
    if not row or row["owner_id"] != user.id:
        raise not_found("История не найдена")
    return row


def character_dict(row, pid_by_id: dict[int, str]) -> dict[str, Any]:
    rel_raw = json.loads(row["relationships"] or "{}")
    return {
        "id": row["public_id"],
        "role": row["role"],
        "position": row["position"],
        "name": row["name"],
        "avatar_image_id": row["avatar_image_id"],
        **{f: row[f] for f in CARD_FIELDS},
        "relationships": rel_raw,
        "version": row["version"],
        "updated_at": row["updated_at"],
    }


def story_dict(db: Database, row, full: bool = True) -> dict[str, Any]:
    chars = db.all("SELECT * FROM characters WHERE story_id=? ORDER BY position", (row["id"],))
    pid_by_id = {c["id"]: c["public_id"] for c in chars}
    d = {
        "id": row["public_id"],
        "title": row["title"],
        "description": row["description"],
        "intro": row["intro"],
        "world_rules": row["world_rules"],
        "start_scene": row["start_scene"],
        "cover_image_id": row["cover_image_id"],
        "is_demo": bool(row["is_demo"]),
        "version": row["version"],
        "updated_at": row["updated_at"],
    }
    if full:
        d["characters"] = [character_dict(c, pid_by_id) for c in chars]
        sms = db.all("SELECT * FROM start_messages WHERE story_id=? ORDER BY position", (row["id"],))
        d["start_messages"] = [
            {"speaker": "narrator" if m["speaker_kind"] == "narrator" else pid_by_id.get(m["character_id"], "narrator"),
             "text": m["text"]}
            for m in sms
        ]
    else:
        d["character_names"] = [c["name"] for c in chars if c["role"] == "npc"]
        d["avatar_image_id"] = next((c["avatar_image_id"] for c in chars if c["avatar_image_id"] and c["role"] == "npc"), None)
    return d


def list_stories(db: Database, user: User) -> list[dict]:
    rows = db.all("SELECT * FROM stories WHERE owner_id=? ORDER BY is_demo DESC, updated_at DESC", (user.id,))
    return [story_dict(db, r, full=False) for r in rows]


def _validate_story(db: Database, user: User, s: StoryIn) -> None:
    if len(s.characters) > settings.max_characters:
        raise ApiError(400, "too_many_characters", f"В истории может быть не больше {settings.max_characters} персонажей.")
    if sum(1 for c in s.characters if c.role == "hero") > 2:
        raise ApiError(400, "too_many_heroes", "Героев игроков может быть не больше двух.")
    if not any(c.role == "npc" for c in s.characters):
        raise ApiError(400, "no_npc", "Добавь хотя бы одного персонажа, которого ведёт ИИ.")
    if len(s.start_messages) > 12:
        raise ApiError(400, "too_many_start", "Слишком много стартовых сообщений (максимум 12).")
    for c in s.characters:
        if c.role not in ("npc", "hero"):
            raise ApiError(400, "bad_role", "Неизвестная роль персонажа.")
        _check_fields(c)
        _check_image(db, user, c.avatar_image_id)
    _check_image(db, user, s.cover_image_id)
    names = [c.name.strip().casefold() for c in s.characters]
    if len(set(names)) != len(names):
        raise ApiError(400, "duplicate_names", "У персонажей должны быть разные имена.")


def _write_story_children(db: Database, story_id: int, s: StoryIn, existing: dict[str, Any]) -> None:
    """Upsert characters (keeping ids/versions of unchanged ones) and start messages.
    Must be called inside a transaction."""
    ts = now_ms()
    ref_to_id: dict[str, int] = {}
    ref_to_pid: dict[str, str] = {}
    keep_ids: set[int] = set()
    created_ids: set[int] = set()
    for pos, c in enumerate(s.characters):
        old = existing.get(c.id) if c.id else None
        values = {
            "role": c.role, "name": c.name.strip(), "avatar_image_id": c.avatar_image_id,
            **{f: (getattr(c, f) or "").strip() for f in CARD_FIELDS},
        }
        if old:
            changed = any(old[k] != v for k, v in values.items()) or old["position"] != pos
            db.run(
                "UPDATE characters SET position=?, role=?, name=?, avatar_image_id=?, age=?, appearance=?, habits=?, "
                "personality=?, motivation=?, backstory=?, speech_style=?, example_lines=?, "
                "version=version+?, updated_at=? WHERE id=?",
                (pos, values["role"], values["name"], values["avatar_image_id"], values["age"], values["appearance"],
                 values["habits"], values["personality"], values["motivation"], values["backstory"],
                 values["speech_style"], values["example_lines"], 1 if changed else 0, ts, old["id"]),
            )
            cid, cpid = old["id"], old["public_id"]
        else:
            cpid = new_id()
            cur = db.run(
                "INSERT INTO characters(public_id, story_id, position, role, name, avatar_image_id, age, appearance, habits, "
                "personality, motivation, backstory, speech_style, relationships, example_lines, version, updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?, '{}', ?, 1, ?)",
                (cpid, story_id, pos, values["role"], values["name"], values["avatar_image_id"], values["age"],
                 values["appearance"], values["habits"], values["personality"], values["motivation"],
                 values["backstory"], values["speech_style"], values["example_lines"], ts),
            )
            cid = cur.lastrowid
            created_ids.add(cid)
        keep_ids.add(cid)
        for ref in filter(None, [c.id, c.key, cpid]):
            ref_to_id[ref] = cid
            ref_to_pid[ref] = cpid
    # relationships, resolved to public ids
    for c in s.characters:
        ref = c.id or c.key
        cid = ref_to_id.get(ref) if ref else None
        if cid is None:
            continue
        rel = {}
        for target, text in (c.relationships or {}).items():
            tp = ref_to_pid.get(target) or (target if target.startswith("seat:") else None)
            if tp and text.strip():
                rel[tp] = text.strip()
        old_rel = db.one("SELECT relationships FROM characters WHERE id=?", (cid,))["relationships"]
        new_rel = json.dumps(rel, ensure_ascii=False, sort_keys=True)
        if json.loads(old_rel or "{}") != rel:
            bump = 0 if cid in created_ids else 1
            db.run("UPDATE characters SET relationships=?, version=version+? WHERE id=?", (new_rel, bump, cid))
    for old in existing.values():
        if old["id"] not in keep_ids:
            db.run("DELETE FROM characters WHERE id=?", (old["id"],))
    db.run("DELETE FROM start_messages WHERE story_id=?", (story_id,))
    for pos, m in enumerate(s.start_messages):
        if m.speaker == "narrator" or not m.speaker:
            db.run("INSERT INTO start_messages(story_id, position, speaker_kind, character_id, text) VALUES(?,?,?,?,?)",
                   (story_id, pos, "narrator", None, m.text.strip()))
        else:
            cid = ref_to_id.get(m.speaker)
            if cid is None:
                raise ApiError(400, "bad_speaker", "Стартовое сообщение ссылается на неизвестного персонажа.")
            db.run("INSERT INTO start_messages(story_id, position, speaker_kind, character_id, text) VALUES(?,?,?,?,?)",
                   (story_id, pos, "character", cid, m.text.strip()))


def create_story(db: Database, user: User, s: StoryIn, is_demo: bool = False) -> dict:
    _validate_story(db, user, s)
    ts = now_ms()
    with db.tx():
        pid = new_id()
        cur = db.run(
            "INSERT INTO stories(public_id, owner_id, title, description, intro, world_rules, start_scene, cover_image_id, "
            "is_demo, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (pid, user.id, s.title.strip(), s.description.strip(), s.intro.strip(), s.world_rules.strip(),
             s.start_scene.strip(), s.cover_image_id, 1 if is_demo else 0, ts, ts),
        )
        _write_story_children(db, cur.lastrowid, s, {})
    return story_dict(db, db.one("SELECT * FROM stories WHERE public_id=?", (pid,)))


def replace_story(db: Database, user: User, story_pid: str, s: StoryIn) -> dict:
    row = story_row(db, user, story_pid)
    _validate_story(db, user, s)
    existing = {c["public_id"]: c for c in db.all("SELECT * FROM characters WHERE story_id=?", (row["id"],))}
    for c in s.characters:
        if c.id and c.id not in existing:
            raise ApiError(400, "bad_character", "Персонаж не найден в этой истории.")
    ts = now_ms()
    with db.tx():
        db.run(
            "UPDATE stories SET title=?, description=?, intro=?, world_rules=?, start_scene=?, cover_image_id=?, "
            "version=version+1, updated_at=? WHERE id=?",
            (s.title.strip(), s.description.strip(), s.intro.strip(), s.world_rules.strip(), s.start_scene.strip(),
             s.cover_image_id, ts, row["id"]),
        )
        _write_story_children(db, row["id"], s, existing)
        bump_story_rooms(db, row["id"])
    return story_dict(db, db.one("SELECT * FROM stories WHERE id=?", (row["id"],)))


def quick_story(db: Database, user: User, q: QuickStoryIn) -> dict:
    name = q.name.strip()
    s = StoryIn(
        title=f"{name}",
        description=f"Быстрая история с персонажем {name}.",
        world_rules="Современный мир, обычная жизнь. Тон — живой и тёплый.",
        start_scene="Тихое место, где герои встречают персонажа.",
        cover_image_id=None,
        characters=[CharacterIn(key="c1", role="npc", name=name, avatar_image_id=q.avatar_image_id,
                                personality=q.personality, speech_style=q.speech_style)],
        start_messages=[StartMessageIn(speaker="c1", text=q.start_line.strip())] if q.start_line.strip() else [
            StartMessageIn(speaker="narrator", text=f"{name} поднимает взгляд, замечая вас.")],
    )
    return create_story(db, user, s)


def create_demo_story(db: Database, user: User) -> dict:
    d = demo.DEMO
    s = StoryIn(
        title=d["title"], description=d["description"], intro=d["intro"], world_rules=d["world_rules"],
        start_scene=d["start_scene"],
        characters=[CharacterIn(**{k: v for k, v in c.items()}) for c in d["characters"]],
        start_messages=[StartMessageIn(**m) for m in d["start_messages"]],
    )
    return create_story(db, user, s, is_demo=True)


def delete_story(db: Database, user: User, story_pid: str) -> None:
    row = story_row(db, user, story_pid)
    with db.tx():
        room_ids = [r["id"] for r in db.all("SELECT id FROM rooms WHERE story_id=?", (row["id"],))]
        db.run("DELETE FROM stories WHERE id=?", (row["id"],))
    for rid in room_ids:
        hub.notify(f"room:{rid}")


def bump_story_rooms(db: Database, story_id: int) -> list[int]:
    """Mark all rooms of a story as changed (cards/metadata). Call inside a transaction."""
    rooms = db.all("SELECT id FROM rooms WHERE story_id=?", (story_id,))
    for r in rooms:
        db.run("UPDATE rooms SET rev=rev+1, meta_rev=rev+1, updated_at=? WHERE id=?", (now_ms(), r["id"]))
    for r in rooms:
        hub.notify(f"room:{r['id']}")
    return [r["id"] for r in rooms]


def patch_character(db: Database, user: User, story_pid: str, char_pid: str, p: CharacterPatch) -> dict:
    row = story_row(db, user, story_pid)
    c = db.one("SELECT * FROM characters WHERE public_id=? AND story_id=?", (char_pid, row["id"]))
    if not c:
        raise not_found("Персонаж не найден")
    _check_fields(p)
    updates: dict[str, Any] = {}
    if p.name is not None and p.name.strip() != c["name"]:
        other = db.one("SELECT 1 FROM characters WHERE story_id=? AND lower(name)=lower(?) AND id<>?",
                       (row["id"], p.name.strip(), c["id"]))
        if other:
            raise ApiError(400, "duplicate_names", "У персонажей должны быть разные имена.")
        updates["name"] = p.name.strip()
    if p.clear_avatar:
        updates["avatar_image_id"] = None
    elif p.avatar_image_id is not None and p.avatar_image_id != c["avatar_image_id"]:
        updates["avatar_image_id"] = _check_image(db, user, p.avatar_image_id)
    for f in CARD_FIELDS:
        v = getattr(p, f)
        if v is not None and v.strip() != c[f]:
            updates[f] = v.strip()
    if p.relationships is not None:
        valid = {x["public_id"] for x in db.all("SELECT public_id FROM characters WHERE story_id=?", (row["id"],))}
        rel = {k: v.strip() for k, v in p.relationships.items() if (k in valid or k.startswith("seat:")) and v.strip()}
        if rel != json.loads(c["relationships"] or "{}"):
            updates["relationships"] = json.dumps(rel, ensure_ascii=False, sort_keys=True)
    if updates:
        ts = now_ms()
        with db.tx():
            sets = ", ".join(f"{k}=?" for k in updates)
            db.run(f"UPDATE characters SET {sets}, version=version+1, updated_at=? WHERE id=?",
                   (*updates.values(), ts, c["id"]))
            db.run("UPDATE stories SET updated_at=? WHERE id=?", (ts, row["id"]))
            bump_story_rooms(db, row["id"])
    c = db.one("SELECT * FROM characters WHERE id=?", (c["id"],))
    return character_dict(c, {})
