"""Rooms (a played scene of a story for up to two players), invites, messages,
sync and the generation queue entries."""
from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from . import llm, prompt as P
from .common import ApiError, User, hub, new_id, not_found
from .config import settings
from .db import Database, now_ms
from .stories import character_dict, story_dict

USER_GEN_KINDS = ("reply", "continue", "regenerate")


class MessageIn(BaseModel):
    client_id: str = Field(min_length=8, max_length=64)
    text: str = Field(min_length=1, max_length=2000)


class ActionIn(BaseModel):
    client_id: str = Field(min_length=8, max_length=64)


class SceneIn(BaseModel):
    location: str = Field(default="", max_length=600)


class InviteIn(BaseModel):
    user_id: str


class RoomSettingsIn(BaseModel):
    ai_mode: str = Field(pattern="^(local|cloud)$")


class PhotoIn(BaseModel):
    client_id: str = Field(min_length=8, max_length=64)
    prompt: str = Field(default="", max_length=300)


class EditIn(BaseModel):
    text: str = Field(min_length=1, max_length=5000)


# ---------------------------------------------------------------------------
def member_room(db: Database, user: User, room_pid: str):
    """Return the room row if ``user`` sits in it; otherwise 404 (no existence leak)."""
    row = db.one("SELECT * FROM rooms WHERE public_id=?", (room_pid,))
    if not row or (row["owner_id"] != user.id and row["guest_id"] != user.id):
        raise not_found("Сцена не найдена")
    return row


def _bump(db: Database, room_id: int, meta: bool = False) -> int:
    if meta:
        db.run("UPDATE rooms SET rev=rev+1, meta_rev=rev+1, updated_at=? WHERE id=?", (now_ms(), room_id))
    else:
        db.run("UPDATE rooms SET rev=rev+1, updated_at=? WHERE id=?", (now_ms(), room_id))
    return db.one("SELECT rev FROM rooms WHERE id=?", (room_id,))["rev"]


def _notify_room(room_id: int) -> None:
    hub.notify(f"room:{room_id}")


def _user_pub(db: Database, uid: int | None) -> dict | None:
    if uid is None:
        return None
    u = db.one("SELECT public_id, nick FROM users WHERE id=?", (uid,))
    return {"id": u["public_id"], "nick": u["nick"]} if u else None


def heroes_of(db: Database, story_id: int) -> list:
    return db.all("SELECT * FROM characters WHERE story_id=? AND role='hero' ORDER BY position", (story_id,))


def seats_of(db: Database, room) -> list[dict]:
    if room["story_id"] is None:  # personal chat: the player is just themself
        u = _user_pub(db, room["owner_id"])
        return [{"index": 0, "user": u, "hero_character_id": None, "hero_name": u["nick"] if u else "Игрок"}]
    heroes = heroes_of(db, room["story_id"])
    seats = []
    for idx, uid in enumerate([room["owner_id"], room["guest_id"]]):
        hero = heroes[idx] if idx < len(heroes) else None
        u = _user_pub(db, uid)
        seats.append({
            "index": idx,
            "user": u,
            "hero_character_id": hero["public_id"] if hero else None,
            "hero_name": hero["name"] if hero else (u["nick"] if u else ("Гость" if idx else "Хозяин")),
        })
    return seats


def room_personas(db: Database, room) -> list:
    return db.all("SELECT p.* FROM room_personas rp JOIN personas p ON p.id=rp.persona_id WHERE rp.room_id=? "
                  "ORDER BY rp.position", (room["id"],))


def _persona_as_character(p) -> dict:
    """A persona in the shape of a story character, so the chat screen shows it the same way.
    Backstory / personality stay on the server."""
    return {"id": p["public_id"], "role": "npc", "position": 0, "name": p["name"], "avatar_image_id": p["avatar_image_id"],
            "appearance": p["description"], "version": p["version"], "updated_at": p["updated_at"]}


def _chat_story(db: Database, room) -> dict:
    ps = room_personas(db, room)
    return {"id": None, "title": room["title"], "description": ps[0]["description"] if ps else "",
            "intro": "", "world_rules": room["setting"], "start_scene": "", "cover_image_id": None, "is_demo": False,
            "version": 1, "updated_at": room["updated_at"], "characters": [_persona_as_character(p) for p in ps],
            "start_messages": []}


def room_detail(db: Database, user: User, room) -> dict:
    if room["story_id"] is None:
        sd = _chat_story(db, room)
    else:
        sd = story_dict(db, db.one("SELECT * FROM stories WHERE id=?", (room["story_id"],)), full=True)
    invite = db.one("SELECT ri.*, u.public_id upid, u.nick FROM room_invites ri JOIN users u ON u.id=ri.to_user "
                    "WHERE ri.room_id=? ORDER BY ri.updated_at DESC LIMIT 1", (room["id"],))
    return {
        "id": room["public_id"],
        "kind": room["kind"],
        "title": room["title"] or sd["title"],
        "story": sd,
        "my_role": "owner" if room["owner_id"] == user.id else "guest",
        "my_seat": 0 if room["owner_id"] == user.id else 1,
        "seats": seats_of(db, room),
        "scene_location": room["scene_location"],
        "ai_mode": room["ai_mode"],
        "cloud_available": settings.cloud_available,
        "images_available": settings.cloud_available,
        "ai_models": {"local": settings.llm_model, "cloud": settings.cloud_text_model, "image": settings.cloud_image_model},
        "summary": room["summary"],
        "invite": ({"id": invite["public_id"], "status": invite["status"],
                    "to": {"id": invite["upid"], "nick": invite["nick"]}} if invite else None),
        "rev": room["rev"],
        "meta_rev": room["meta_rev"],
        "created_at": room["created_at"],
    }


def create_room(db: Database, user: User, story_pid: str) -> dict:
    story = db.one("SELECT * FROM stories WHERE public_id=?", (story_pid,))
    if not story or story["owner_id"] != user.id:
        raise not_found("История не найдена")
    count = db.one("SELECT COUNT(*) n FROM rooms WHERE owner_id=?", (user.id,))["n"]
    if count >= 200:
        raise ApiError(400, "too_many_rooms", "Слишком много сцен. Удали старые.")
    ts = now_ms()
    with db.tx():
        pid = new_id()
        cur = db.run(
            "INSERT INTO rooms(public_id, story_id, owner_id, rev, meta_rev, next_seq, scene_location, ai_mode, created_at, updated_at) "
            "VALUES(?,?,?,1,1,1,?,?,?,?)",
            (pid, story["id"], user.id, story["start_scene"], settings.new_room_ai_mode(), ts, ts),
        )
        room_id = cur.lastrowid
        chars = {c["id"]: c for c in db.all("SELECT * FROM characters WHERE story_id=?", (story["id"],))}
        seq = 1
        if story["intro"].strip():
            _insert_msg(db, room_id, seq, 1, "system", None, None, "", story["intro"].strip(), None, None)
            seq += 1
        for m in db.all("SELECT * FROM start_messages WHERE story_id=? ORDER BY position", (story["id"],)):
            if m["speaker_kind"] == "narrator" or m["character_id"] not in chars:
                _insert_msg(db, room_id, seq, 1, "narrator", None, None, P.NARRATOR, m["text"], None, None)
            else:
                c = chars[m["character_id"]]
                mid = _insert_msg(db, room_id, seq, 1, "character", None, c["id"], c["name"], m["text"], None, None)
                for f in P.extract_facts(c["name"], m["text"]):
                    db.run("INSERT INTO scene_facts(room_id, message_id, generation_id, seq, text) VALUES(?,?,?,?,?)",
                           (room_id, mid, None, seq, f))
            seq += 1
        db.run("UPDATE rooms SET next_seq=? WHERE id=?", (seq, room_id))
    room = db.one("SELECT * FROM rooms WHERE id=?", (room_id,))
    return room_detail(db, user, room)


def delete_room(db: Database, user: User, room_pid: str) -> None:
    room = member_room(db, user, room_pid)
    if room["owner_id"] == user.id:
        with db.tx():
            db.run("DELETE FROM rooms WHERE id=?", (room["id"],))
    else:  # guest leaves
        with db.tx():
            db.run("UPDATE rooms SET guest_id=NULL WHERE id=?", (room["id"],))
            db.run("UPDATE room_invites SET status='cancelled', updated_at=? WHERE room_id=? AND to_user=?",
                   (now_ms(), room["id"], user.id))
            _bump(db, room["id"], meta=True)
    _notify_room(room["id"])


def list_rooms(db: Database, user: User) -> list[dict]:
    rows = db.all(
        "SELECT r.*, COALESCE(s.title, r.title) AS story_title_, s.cover_image_id, "
        "(SELECT p.avatar_image_id FROM room_personas rp JOIN personas p ON p.id=rp.persona_id "
        " WHERE rp.room_id=r.id ORDER BY rp.position LIMIT 1) AS persona_avatar "
        "FROM rooms r LEFT JOIN stories s ON s.id=r.story_id "
        "WHERE r.owner_id=? OR r.guest_id=? ORDER BY r.updated_at DESC LIMIT 100",
        (user.id, user.id),
    )
    out = []
    for r in rows:
        last = db.one("SELECT speaker_name, text, image_id FROM messages WHERE room_id=? AND hidden=0 ORDER BY seq DESC LIMIT 1",
                      (r["id"],))
        if last and last["image_id"]:
            last = {"speaker_name": "", "text": "📷 Фото сцены"}
        partner_id = r["guest_id"] if r["owner_id"] == user.id else r["owner_id"]
        out.append({
            "id": r["public_id"],
            "kind": r["kind"],
            "story_title": r["story_title_"],
            "cover_image_id": r["cover_image_id"] or r["persona_avatar"],
            "my_role": "owner" if r["owner_id"] == user.id else "guest",
            "partner": _user_pub(db, partner_id),
            "last_message": (f"{last['speaker_name']}: {last['text']}" if last and last["speaker_name"] else
                             (last["text"] if last else ""))[:160],
            "updated_at": r["updated_at"],
        })
    return out


# ---------------------------------------------------------------------------
# invites
# ---------------------------------------------------------------------------
def are_friends(db: Database, a: int, b: int) -> bool:
    return db.one(
        "SELECT 1 FROM friend_requests WHERE status='accepted' AND ((from_user=? AND to_user=?) OR (from_user=? AND to_user=?))",
        (a, b, b, a),
    ) is not None


def invite(db: Database, user: User, room_pid: str, target_pid: str) -> dict:
    room = member_room(db, user, room_pid)
    if room["owner_id"] != user.id:
        raise ApiError(403, "not_owner", "Пригласить друга может только хозяин сцены.")
    target = db.one("SELECT id, public_id, nick FROM users WHERE public_id=?", (target_pid,))
    if not target or not are_friends(db, user.id, target["id"]):
        raise ApiError(400, "not_friend", "Пригласить можно только друга, который принял заявку.")
    if room["guest_id"] is not None and room["guest_id"] != target["id"]:
        raise ApiError(409, "room_full", "В сцене уже два игрока.")
    if room["guest_id"] == target["id"]:
        raise ApiError(409, "already_in_room", "Друг уже в этой сцене.")
    ts = now_ms()
    with db.tx():
        existing = db.one("SELECT * FROM room_invites WHERE room_id=? AND to_user=?", (room["id"], target["id"]))
        # only one active invite per room
        db.run("UPDATE room_invites SET status='cancelled', updated_at=? WHERE room_id=? AND status='pending' AND to_user<>?",
               (ts, room["id"], target["id"]))
        if existing:
            if existing["status"] != "pending":
                db.run("UPDATE room_invites SET status='pending', updated_at=? WHERE id=?", (ts, existing["id"]))
            ipid = existing["public_id"]
        else:
            ipid = new_id()
            db.run("INSERT INTO room_invites(public_id, room_id, from_user, to_user, status, created_at, updated_at) "
                   "VALUES(?,?,?,?, 'pending', ?, ?)", (ipid, room["id"], user.id, target["id"], ts, ts))
        _bump(db, room["id"], meta=True)
    hub.notify(f"user:{target['id']}")
    _notify_room(room["id"])
    return {"id": ipid, "status": "pending", "to": {"id": target["public_id"], "nick": target["nick"]}}


def list_invites(db: Database, user: User) -> list[dict]:
    rows = db.all(
        "SELECT ri.public_id, ri.status, ri.created_at, r.public_id rpid, COALESCE(s.title, r.title) title, u.public_id upid, u.nick "
        "FROM room_invites ri JOIN rooms r ON r.id=ri.room_id LEFT JOIN stories s ON s.id=r.story_id "
        "JOIN users u ON u.id=ri.from_user WHERE ri.to_user=? AND ri.status='pending' ORDER BY ri.updated_at DESC",
        (user.id,),
    )
    return [{"id": r["public_id"], "status": r["status"], "room_id": r["rpid"], "story_title": r["title"],
             "from": {"id": r["upid"], "nick": r["nick"]}, "created_at": r["created_at"]} for r in rows]


def answer_invite(db: Database, user: User, invite_pid: str, accept: bool) -> dict:
    inv = db.one("SELECT * FROM room_invites WHERE public_id=?", (invite_pid,))
    if not inv or inv["to_user"] != user.id:
        raise not_found("Приглашение не найдено")
    if inv["status"] != "pending":
        raise ApiError(409, "invite_closed", "Приглашение уже неактуально.")
    room = db.one("SELECT * FROM rooms WHERE id=?", (inv["room_id"],))
    ts = now_ms()
    with db.tx():
        if accept:
            if room["guest_id"] is not None and room["guest_id"] != user.id:
                raise ApiError(409, "room_full", "В сцене уже два игрока.")
            if not are_friends(db, room["owner_id"], user.id):
                raise ApiError(403, "not_friend", "Вы больше не друзья.")
            db.run("UPDATE rooms SET guest_id=? WHERE id=?", (user.id, room["id"]))
            db.run("UPDATE room_invites SET status='accepted', updated_at=? WHERE id=?", (ts, inv["id"]))
            owner_nick = db.one("SELECT nick FROM users WHERE id=?", (room["owner_id"],))["nick"]
            seats = seats_of(db, db.one("SELECT * FROM rooms WHERE id=?", (room["id"],)))
            _insert_system(db, room["id"], f"{user.nick} присоединяется к сцене как {seats[1]['hero_name']}.")
        else:
            db.run("UPDATE room_invites SET status='declined', updated_at=? WHERE id=?", (ts, inv["id"]))
        _bump(db, room["id"], meta=True)
    _notify_room(room["id"])
    hub.notify(f"user:{room['owner_id']}")
    return {"id": invite_pid, "status": "accepted" if accept else "declined", "room_id": room["public_id"]}


# ---------------------------------------------------------------------------
# messages
# ---------------------------------------------------------------------------
def _insert_msg(db, room_id, seq, rev, kind, user_id, character_id, speaker, text, client_id, generation_id,
                image_id=None, persona_id=None) -> int:
    cur = db.run(
        "INSERT INTO messages(public_id, room_id, seq, rev, kind, user_id, character_id, persona_id, speaker_name, text, "
        "client_id, generation_id, image_id, hidden, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,0,?)",
        (new_id(), room_id, seq, rev, kind, user_id, character_id, persona_id, speaker, text, client_id, generation_id,
         image_id, now_ms()),
    )
    return cur.lastrowid


def _append(db, room_id, kind, user_id, character_id, speaker, text, client_id=None, generation_id=None,
            image_id=None, persona_id=None) -> int:
    """Append a message at the end of the room in server order. Inside a transaction."""
    rev = _bump(db, room_id)
    seq = db.one("SELECT next_seq FROM rooms WHERE id=?", (room_id,))["next_seq"]
    db.run("UPDATE rooms SET next_seq=next_seq+1 WHERE id=?", (room_id,))
    return _insert_msg(db, room_id, seq, rev, kind, user_id, character_id, speaker, text, client_id, generation_id,
                       image_id, persona_id)


def _insert_system(db, room_id, text) -> int:
    return _append(db, room_id, "system", None, None, "", text)


def message_dict(db: Database, m, viewer: User | None = None, user_cache: dict | None = None,
                 char_cache: dict | None = None) -> dict:
    user_cache = user_cache if user_cache is not None else {}
    char_cache = char_cache if char_cache is not None else {}
    upid = None
    if m["user_id"] is not None:
        if m["user_id"] not in user_cache:
            u = db.one("SELECT public_id FROM users WHERE id=?", (m["user_id"],))
            user_cache[m["user_id"]] = u["public_id"] if u else None
        upid = user_cache[m["user_id"]]
    cpid = None
    if m["character_id"] is not None:
        if m["character_id"] not in char_cache:
            c = db.one("SELECT public_id FROM characters WHERE id=?", (m["character_id"],))
            char_cache[m["character_id"]] = c["public_id"] if c else None
        cpid = char_cache[m["character_id"]]
    elif m["persona_id"] is not None:  # personal chat: the persona plays the "character" part
        key = ("p", m["persona_id"])
        if key not in char_cache:
            p = db.one("SELECT public_id FROM personas WHERE id=?", (m["persona_id"],))
            char_cache[key] = p["public_id"] if p else None
        cpid = char_cache[key]
    gpid = None
    if m["generation_id"] is not None:
        g = db.one("SELECT public_id FROM generations WHERE id=?", (m["generation_id"],))
        gpid = g["public_id"] if g else None
    return {
        "id": m["public_id"],
        "seq": m["seq"],
        "rev": m["rev"],
        "kind": m["kind"],
        "user_id": upid,
        "character_id": cpid,
        "speaker_name": m["speaker_name"],
        "text": m["text"],
        "generation_id": gpid,
        "image_id": m["image_id"],
        "hidden": bool(m["hidden"]),
        "edited": m["edited_at"] is not None,
        "client_id": m["client_id"] if (viewer and m["user_id"] == viewer.id) else None,
        "created_at": m["created_at"],
    }


def _active_generation(db: Database, room_id: int):
    return db.one("SELECT * FROM generations WHERE room_id=? AND kind IN ('reply','continue','regenerate') "
                  "AND status IN ('queued','running') ORDER BY id LIMIT 1", (room_id,))


def _last_user_generation(db: Database, room_id: int):
    return db.one("SELECT * FROM generations WHERE room_id=? AND kind IN ('reply','continue','regenerate') "
                  "ORDER BY id DESC LIMIT 1", (room_id,))


def generation_dict(db: Database, g) -> dict | None:
    if g is None:
        return None
    partial = hub.partial.get(g["room_id"])
    return {
        "id": g["public_id"],
        "kind": g["kind"],
        "status": g["status"],
        "error": g["error"],
        "partial": partial["text"] if (partial and partial["generation"] == g["public_id"] and g["status"] == "running") else None,
        "queue_position": _queue_position(db, g) if g["status"] == "queued" else None,
        "stats": ({"prompt_tokens": g["prompt_tokens"], "output_tokens": g["output_tokens"],
                   "prompt_ms": g["prompt_ms"], "output_ms": g["output_ms"], "total_ms": g["total_ms"]}
                  if g["status"] == "done" else None),
    }


def _queue_position(db: Database, g) -> int:
    return db.one("SELECT COUNT(*) n FROM generations WHERE status IN ('queued','running') AND id<?", (g["id"],))["n"]


def _enqueue(db: Database, room_id: int, kind: str, user: User | None, client_id: str | None,
             replaces: int | None = None, delay_ms: int = 0) -> int:
    cur = db.run(
        "INSERT INTO generations(public_id, room_id, kind, status, requested_by, client_id, replaces_generation_id, "
        "not_before_ms, created_at) VALUES(?,?,?, 'queued', ?,?,?,?,?)",
        (new_id(), room_id, kind, user.id if user else None, client_id, replaces, now_ms() + delay_ms, now_ms()),
    )
    _bump(db, room_id)
    return cur.lastrowid


def post_message(db: Database, user: User, room_pid: str, body: MessageIn, wake_worker) -> dict:
    room = member_room(db, user, room_pid)
    text = body.text.strip()
    if not text:
        raise ApiError(400, "empty", "Сообщение пустое.")
    dup = db.one("SELECT * FROM messages WHERE room_id=? AND user_id=? AND client_id=?", (room["id"], user.id, body.client_id))
    if dup:  # idempotent retry
        return {"message": message_dict(db, dup, user), "generation": generation_dict(db, _last_user_generation(db, room["id"])),
                "duplicate": True}
    active = _active_generation(db, room["id"])
    if active and active["kind"] == "regenerate":
        raise ApiError(409, "regenerating", "Идёт перегенерация ответа. Подожди пару секунд.")
    seat = 0 if room["owner_id"] == user.id else 1
    hero_name = seats_of(db, room)[seat]["hero_name"]
    with db.tx():
        mid = _append(db, room["id"], "player", user.id, None, hero_name, text, client_id=body.client_id)
        seq = db.one("SELECT seq FROM messages WHERE id=?", (mid,))["seq"]
        for f in P.extract_facts(hero_name, text):
            db.run("INSERT INTO scene_facts(room_id, message_id, generation_id, seq, text) VALUES(?,?,?,?,?)",
                   (room["id"], mid, None, seq, f))
        queued = db.one("SELECT * FROM generations WHERE room_id=? AND status='queued' AND kind IN ('reply','continue') "
                        "ORDER BY id LIMIT 1", (room["id"],))
        if queued:
            # coalesce: one reaction to both simultaneous turns
            db.run("UPDATE generations SET kind='reply', not_before_ms=? WHERE id=?",
                   (now_ms() + settings.reply_debounce_ms, queued["id"]))
            gid = queued["id"]
        else:
            gid = _enqueue(db, room["id"], "reply", user, None, delay_ms=settings.reply_debounce_ms)
    _notify_room(room["id"])
    wake_worker()
    m = db.one("SELECT * FROM messages WHERE id=?", (mid,))
    return {"message": message_dict(db, m, user), "generation": generation_dict(db, db.one("SELECT * FROM generations WHERE id=?", (gid,))),
            "duplicate": False}


def request_generation(db: Database, user: User, room_pid: str, kind: str, client_id: str, wake_worker) -> dict:
    """kind: continue | regenerate | retry"""
    room = member_room(db, user, room_pid)
    dup = db.one("SELECT * FROM generations WHERE room_id=? AND requested_by=? AND client_id=?",
                 (room["id"], user.id, client_id))
    if dup:
        return {"generation": generation_dict(db, dup), "duplicate": True}
    active = _active_generation(db, room["id"])
    if active:
        if kind == "continue" and active["kind"] in ("reply", "continue"):
            return {"generation": generation_dict(db, active), "duplicate": True}
        raise ApiError(409, "busy", "ИИ уже отвечает. Дождись окончания.")
    last_visible = db.one("SELECT * FROM messages WHERE room_id=? AND hidden=0 AND image_id IS NULL AND kind<>'system' "
                          "ORDER BY seq DESC LIMIT 1", (room["id"],))
    if kind == "retry":
        last = _last_user_generation(db, room["id"])
        if last and last["status"] == "failed" and last["kind"] == "regenerate":
            kind = "regenerate"
        elif last_visible is not None and last_visible["kind"] == "player":
            kind = "reply"
        else:
            kind = "continue"
    replaces = None
    if kind == "regenerate":
        if not last_visible or last_visible["generation_id"] is None:
            raise ApiError(409, "nothing_to_regenerate",
                           "Перегенерировать можно только последний ответ ИИ, после которого ещё никто не писал.")
        replaces = last_visible["generation_id"]
    with db.tx():
        gid = _enqueue(db, room["id"], kind, user, client_id, replaces=replaces)
    _notify_room(room["id"])
    wake_worker()
    return {"generation": generation_dict(db, db.one("SELECT * FROM generations WHERE id=?", (gid,))), "duplicate": False}


def set_scene(db: Database, user: User, room_pid: str, body: SceneIn) -> dict:
    room = member_room(db, user, room_pid)
    if room["owner_id"] != user.id:
        raise ApiError(403, "not_owner", "Менять сцену может только хозяин.")
    with db.tx():
        db.run("UPDATE rooms SET scene_location=? WHERE id=?", (body.location.strip(), room["id"]))
        _bump(db, room["id"], meta=True)
    _notify_room(room["id"])
    return {"scene_location": body.location.strip()}


def sync_payload(db: Database, user: User, room, since: int) -> dict:
    rows = db.all("SELECT * FROM messages WHERE room_id=? AND rev>? ORDER BY seq", (room["id"], since))
    uc, cc = {}, {}
    msgs = [message_dict(db, m, user, uc, cc) for m in rows]
    payload: dict[str, Any] = {
        "rev": room["rev"],
        "messages": msgs,
        "generation": generation_dict(db, _last_user_generation(db, room["id"])),
        "image_job": image_job_dict(db.one("SELECT * FROM image_jobs WHERE room_id=? ORDER BY id DESC LIMIT 1", (room["id"],))),
        "full": since == 0,
    }
    if since < room["meta_rev"]:
        payload["room"] = room_detail(db, user, room)
    return payload


def last_prompt(db: Database, user: User, room_pid: str) -> dict:
    room = member_room(db, user, room_pid)
    g = db.one("SELECT * FROM generations WHERE room_id=? AND prompt IS NOT NULL AND kind<>'summary' ORDER BY id DESC LIMIT 1",
               (room["id"],))
    if not g:
        raise not_found("Запросов к модели ещё не было")
    return {"generation_id": g["public_id"], "kind": g["kind"], "status": g["status"], "model": g["model"],
            "prompt": g["prompt"], "card_versions": json.loads(g["card_versions"] or "{}"),
            "raw_output": g["raw_output"], "error": g["error"],
            "stats": {"prompt_tokens": g["prompt_tokens"], "output_tokens": g["output_tokens"],
                      "prompt_ms": g["prompt_ms"], "output_ms": g["output_ms"], "total_ms": g["total_ms"]},
            "started_at": g["started_at"], "finished_at": g["finished_at"]}


def room_image_allowed(db: Database, user: User, room_pid: str, image_id: str) -> bool:
    room = member_room(db, user, room_pid)
    if room["story_id"] is not None:
        if db.one("SELECT 1 FROM stories WHERE id=? AND cover_image_id=?", (room["story_id"], image_id)):
            return True
        if db.one("SELECT 1 FROM characters WHERE story_id=? AND avatar_image_id=?", (room["story_id"], image_id)):
            return True
    if db.one("SELECT 1 FROM room_personas rp JOIN personas p ON p.id=rp.persona_id WHERE rp.room_id=? AND p.avatar_image_id=?",
              (room["id"], image_id)):
        return True
    if db.one("SELECT 1 FROM messages WHERE room_id=? AND image_id=?", (room["id"], image_id)):
        return True  # a scene photo posted in this room
    return False


# ---------------------------------------------------------------------------
# AI mode and scene photos
# ---------------------------------------------------------------------------
def set_settings(db: Database, user: User, room_pid: str, body: RoomSettingsIn) -> dict:
    room = member_room(db, user, room_pid)
    if room["owner_id"] != user.id:
        raise ApiError(403, "not_owner", "Переключать ИИ может только хозяин сцены.")
    if body.ai_mode == "cloud" and not settings.cloud_available:
        raise ApiError(400, "cloud_unavailable", "Облачный ИИ не настроен на сервере (нет ключа OpenRouter).")
    if body.ai_mode != room["ai_mode"]:
        with db.tx():
            db.run("UPDATE rooms SET ai_mode=? WHERE id=?", (body.ai_mode, room["id"]))
            _insert_system(db, room["id"], "ИИ переключён: " + ("облачный" if body.ai_mode == "cloud" else "локальный") + ".")
            _bump(db, room["id"], meta=True)
        _notify_room(room["id"])
    return {"ai_mode": body.ai_mode}


def image_job_dict(j) -> dict | None:
    if j is None:
        return None
    return {"id": j["public_id"], "status": j["status"], "error": j["error"], "prompt": j["user_prompt"],
            "image_id": j["image_id"]}


def request_photo(db: Database, user: User, room_pid: str, body: PhotoIn, wake_worker) -> dict:
    room = member_room(db, user, room_pid)
    if not settings.cloud_available:
        raise ApiError(400, "cloud_unavailable", "Фото доступны только с облачным ИИ (на сервере нет ключа OpenRouter).")
    dup = db.one("SELECT * FROM image_jobs WHERE room_id=? AND requested_by=? AND client_id=?", (room["id"], user.id, body.client_id))
    if dup:
        return {"image_job": image_job_dict(dup), "duplicate": True}
    active = db.one("SELECT * FROM image_jobs WHERE room_id=? AND status IN ('queued','running')", (room["id"],))
    if active:
        return {"image_job": image_job_dict(active), "duplicate": True}
    day_ago = now_ms() - 86_400_000
    used = db.one("SELECT COUNT(*) n FROM image_jobs WHERE requested_by=? AND created_at>?", (user.id, day_ago))["n"]
    if used >= settings.rl_images_per_day:
        raise ApiError(429, "rate_limited", f"Лимит фото на сегодня исчерпан ({settings.rl_images_per_day}).")
    with db.tx():
        jid = db.run(
            "INSERT INTO image_jobs(public_id, room_id, requested_by, client_id, user_prompt, status, created_at) "
            "VALUES(?,?,?,?,?, 'queued', ?)",
            (new_id(), room["id"], user.id, body.client_id, body.prompt.strip(), now_ms()),
        ).lastrowid
        _bump(db, room["id"])
    _notify_room(room["id"])
    wake_worker()
    return {"image_job": image_job_dict(db.one("SELECT * FROM image_jobs WHERE id=?", (jid,))), "duplicate": False}


# ---------------------------------------------------------------------------
# personal chat with a character (persona)
# ---------------------------------------------------------------------------
def create_chat(db: Database, user: User, persona_row) -> dict:
    count = db.one("SELECT COUNT(*) n FROM rooms WHERE owner_id=?", (user.id,))["n"]
    if count >= 200:
        raise ApiError(400, "too_many_rooms", "Слишком много чатов и сцен. Удали старые.")
    p = persona_row
    name = p["name"].strip() or "Персонаж"
    ts = now_ms()
    with db.tx():
        cur = db.run(
            "INSERT INTO rooms(public_id, kind, story_id, owner_id, title, rev, meta_rev, next_seq, ai_mode, created_at, updated_at) "
            "VALUES(?, 'chat', NULL, ?, ?, 1, 1, 1, ?, ?, ?)",
            (new_id(), user.id, name, settings.new_room_ai_mode(), ts, ts),
        )
        room_id = cur.lastrowid
        db.run("INSERT INTO room_personas(room_id, persona_id, position) VALUES(?,?,0)", (room_id, p["id"]))
        greeting = p["first_message"].strip() or f"*{name} замечает тебя и улыбается.*"
        _insert_msg(db, room_id, 1, 1, "character", None, None, name, greeting, None, None, persona_id=p["id"])
        db.run("UPDATE rooms SET next_seq=2 WHERE id=?", (room_id,))
    return room_detail(db, user, db.one("SELECT * FROM rooms WHERE id=?", (room_id,)))


def chats_with_persona(db: Database, user: User, persona_id: int) -> list[dict]:
    rows = db.all(
        "SELECT r.public_id, r.updated_at FROM rooms r JOIN room_personas rp ON rp.room_id=r.id "
        "WHERE r.kind='chat' AND r.owner_id=? AND rp.persona_id=? ORDER BY r.updated_at DESC LIMIT 20",
        (user.id, persona_id),
    )
    return [{"id": r["public_id"], "updated_at": r["updated_at"]} for r in rows]


def edit_message(db: Database, user: User, room_pid: str, message_pid: str, body: EditIn) -> dict:
    """Players edit their own lines; anyone in the room may fix the AI's lines.
    The next generation sees the edited text."""
    room = member_room(db, user, room_pid)
    m = db.one("SELECT * FROM messages WHERE room_id=? AND public_id=? AND hidden=0", (room["id"], message_pid))
    if not m or m["kind"] == "system" or m["image_id"]:
        raise not_found("Сообщение не найдено")
    if m["kind"] == "player" and m["user_id"] != user.id:
        raise ApiError(403, "not_yours", "Можно изменить только своё сообщение.")
    text = body.text.strip()
    if not text:
        raise ApiError(400, "empty", "Сообщение пустое.")
    with db.tx():
        rev = _bump(db, room["id"])
        db.run("UPDATE messages SET text=?, edited_at=?, rev=? WHERE id=?", (text, now_ms(), rev, m["id"]))
        db.run("DELETE FROM scene_facts WHERE message_id=?", (m["id"],))
        if m["kind"] in ("player", "character"):
            for f in P.extract_facts(m["speaker_name"], text):
                db.run("INSERT INTO scene_facts(room_id, message_id, generation_id, seq, text) VALUES(?,?,?,?,?)",
                       (room["id"], m["id"], m["generation_id"], m["seq"], f))
    _notify_room(room["id"])
    return {"message": message_dict(db, db.one("SELECT * FROM messages WHERE id=?", (m["id"],)), user)}


async def suggest_replies(db: Database, user: User, room_pid: str) -> dict:
    """Three short options for the player's next turn (not stored)."""
    room = member_room(db, user, room_pid)
    seats = seats_of(db, room)
    hero = next((s["hero_name"] for s in seats if s["user"] and s["user"]["id"] == user.public_id), user.nick)
    if room["story_id"] is None:
        others = [p["name"] for p in room_personas(db, room)]
    else:
        others = [c["name"] for c in db.all("SELECT name FROM characters WHERE story_id=? AND role='npc' ORDER BY position",
                                            (room["story_id"],))]
    rows = db.all("SELECT * FROM messages WHERE room_id=? AND hidden=0 AND kind<>'system' AND image_id IS NULL "
                  "ORDER BY seq DESC LIMIT 12", (room["id"],))
    history = [P.HistoryItem(r["seq"], r["kind"], r["speaker_name"] or P.NARRATOR, r["text"]) for r in reversed(rows)]
    provider = "cloud" if room["ai_mode"] == "cloud" and settings.cloud_available else "local"
    try:
        res = await llm.chat(P.suggest_messages(hero, others, history), num_predict=260, temperature=0.95, provider=provider)
    except llm.LLMError as e:
        raise ApiError(502, "ai_failed", f"ИИ не ответил: {e}")
    options = P.parse_suggestions(res.text)
    if not options:
        raise ApiError(502, "ai_bad_output", "ИИ не смог предложить варианты. Попробуй ещё раз.")
    return {"suggestions": options}
