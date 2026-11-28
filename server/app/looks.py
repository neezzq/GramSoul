"""The look of a profile: Elite, a glowing colored nick, avatar frames, a banner, pinned public stories.

Colors are sent to the apps (GET /v1/looks), so the web version and Android draw the same thing."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .common import ApiError, User
from .db import Database, now_ms

# a glowing nick whose colors flow along the letters (Elite only)
NICK_STYLES: list[dict[str, Any]] = [
    {"id": "aurora", "label": "Сияние", "colors": ["#ff8cc6", "#c8b4ff", "#7ad7ff"]},
    {"id": "sunset", "label": "Закат", "colors": ["#ffb36b", "#ff6f91", "#ff8cc6"]},
    {"id": "ocean", "label": "Океан", "colors": ["#4fd1ff", "#5b8cff", "#a78bfa"]},
    {"id": "gold", "label": "Золото", "colors": ["#ffe29a", "#f5b942", "#fff3c4"]},
    {"id": "neon", "label": "Неон", "colors": ["#5dff9e", "#2de2e6", "#b8ff5d"]},
    {"id": "candy", "label": "Конфета", "colors": ["#ff9de2", "#ffd36e", "#8ef0ff"]},
]
# a ring around the profile photo: the simple ones for everyone, the glowing animated ones with Elite
FRAMES: list[dict[str, Any]] = [
    {"id": "silver", "label": "Серебро", "colors": ["#d9d9de", "#8e8e96"], "elite": False, "animated": False},
    {"id": "rose", "label": "Роза", "colors": ["#ff8cc6", "#ff5fa8"], "elite": False, "animated": False},
    {"id": "lilac", "label": "Сирень", "colors": ["#c8b4ff", "#8f73ff"], "elite": False, "animated": False},
    {"id": "mint", "label": "Мята", "colors": ["#7ef0c2", "#3cc995"], "elite": False, "animated": False},
    {"id": "neon", "label": "Неон", "colors": ["#ff5fa8", "#7a5cff", "#2de2e6", "#ff5fa8"], "elite": True, "animated": True},
    {"id": "gold", "label": "Золото", "colors": ["#fff3c4", "#f5b942", "#b8860b", "#f5b942", "#fff3c4"], "elite": True, "animated": True},
    {"id": "aurora", "label": "Сияние", "colors": ["#ff8cc6", "#c8b4ff", "#7ad7ff", "#7ef0c2", "#ff8cc6"], "elite": True, "animated": True},
    {"id": "flame", "label": "Пламя", "colors": ["#ffcf5c", "#ff6b3d", "#ff2d55", "#ff6b3d", "#ffcf5c"], "elite": True, "animated": True},
]
NICK_STYLE_IDS = {s["id"] for s in NICK_STYLES}
FRAME_BY_ID = {f["id"]: f for f in FRAMES}
MAX_PINS = 3

# what the queries of users select to show someone (the dict below needs these columns)
USER_COLS = "id, public_id, nick, avatar_image_id, about, elite_until, nick_style, frame, banner_image_id"


def catalog() -> dict:
    return {"nick_styles": NICK_STYLES, "frames": FRAMES, "max_pins": MAX_PINS}


def elite_active(row) -> bool:
    keys = row.keys() if hasattr(row, "keys") else row
    until = row["elite_until"] if "elite_until" in keys else None
    return bool(until and until > now_ms())


def look_of(row) -> dict:
    """Elite status and the look a profile shows now (Elite-only things disappear when Elite ends, and come
    back when it is renewed: the choice is kept)."""
    elite = elite_active(row)
    keys = row.keys()
    style = (row["nick_style"] if "nick_style" in keys else "") or ""
    frame = (row["frame"] if "frame" in keys else "") or ""
    banner = row["banner_image_id"] if "banner_image_id" in keys else None
    f = FRAME_BY_ID.get(frame)
    return {
        "elite": elite,
        "nick_style": style if elite and style in NICK_STYLE_IDS else "",
        "frame": frame if f and (elite or not f["elite"]) else "",
        "banner_image_id": banner if elite else None,
    }


def user_dict(row) -> dict:
    """What anyone who finds a player may see: the public profile with its look."""
    return {"id": row["public_id"], "nick": row["nick"], "avatar_image_id": row["avatar_image_id"],
            "about": (row["about"] if "about" in row.keys() else "") or "", **look_of(row)}


def user_by_id(db: Database, uid: int):
    return db.one(f"SELECT {USER_COLS} FROM users WHERE id=?", (uid,))


def author_of(db: Database, uid: int | None, cache: dict | None = None) -> dict | None:
    """A compact author (for catalog cards, posts, comments)."""
    if not uid:
        return None
    if cache is not None and uid in cache:
        return cache[uid]
    row = user_by_id(db, uid)
    out = None
    if row:
        out = {"id": row["public_id"], "nick": row["nick"], "avatar_image_id": row["avatar_image_id"], **look_of(row)}
        out.pop("banner_image_id", None)
    if cache is not None:
        cache[uid] = out
    return out


class LooksIn(BaseModel):
    nick_style: str | None = Field(default=None, max_length=32)
    frame: str | None = Field(default=None, max_length=32)
    banner_image_id: str | None = Field(default=None, max_length=64)  # "" removes the banner


def set_looks(db: Database, user: User, body: LooksIn) -> None:
    row = db.one(f"SELECT {USER_COLS} FROM users WHERE id=?", (user.id,))
    elite = elite_active(row)
    old = row["banner_image_id"]
    sets, params = [], []
    if body.nick_style is not None:
        if body.nick_style and body.nick_style not in NICK_STYLE_IDS:
            raise ApiError(400, "bad_style", "Неизвестный стиль ника.")
        if body.nick_style and not elite:
            raise ApiError(403, "elite_required", "Светящийся ник — с подпиской Elite.")
        sets.append("nick_style=?")
        params.append(body.nick_style)
    if body.frame is not None:
        f = FRAME_BY_ID.get(body.frame)
        if body.frame and not f:
            raise ApiError(400, "bad_frame", "Неизвестная рамка.")
        if f and f["elite"] and not elite:
            raise ApiError(403, "elite_required", "Эта рамка — с подпиской Elite.")
        sets.append("frame=?")
        params.append(body.frame)
    if body.banner_image_id is not None:
        iid = body.banner_image_id or None
        if iid:
            if not elite:
                raise ApiError(403, "elite_required", "Баннер в профиле — с подпиской Elite.")
            img = db.one("SELECT owner_id FROM images WHERE id=?", (iid,))
            if not img or img["owner_id"] != user.id:
                raise ApiError(400, "bad_image", "Картинка не найдена. Загрузи её ещё раз.")
        sets.append("banner_image_id=?")
        params.append(iid)
    if not sets:
        return
    from .images import delete_image_files, drop_unreferenced
    with db.tx():
        db.run(f"UPDATE users SET {', '.join(sets)} WHERE id=?", (*params, user.id))
        gone = drop_unreferenced(db, [old]) if body.banner_image_id is not None and old and old != body.banner_image_id else []
    delete_image_files(gone)


# ---------------------------------------------------------------------------
# public stories pinned on a profile
# ---------------------------------------------------------------------------
class PinsIn(BaseModel):
    story_ids: list[str] = Field(default_factory=list, max_length=MAX_PINS)


def set_pins(db: Database, user: User, body: PinsIn) -> list[dict]:
    ids: list[int] = []
    for pid in dict.fromkeys(body.story_ids):  # keeps the order, drops repeats
        row = db.one("SELECT id, owner_id, visibility FROM stories WHERE public_id=?", (pid,))
        if not row or row["owner_id"] != user.id:
            raise ApiError(404, "not_found", "История не найдена.")
        if row["visibility"] != "public":
            raise ApiError(400, "not_public", "Закрепить можно только опубликованную историю.")
        ids.append(row["id"])
    with db.tx():
        db.run("DELETE FROM profile_pins WHERE user_id=?", (user.id,))
        for pos, sid in enumerate(ids):
            db.run("INSERT INTO profile_pins(user_id, story_id, position) VALUES(?,?,?)", (user.id, sid, pos))
    return pinned_stories(db, user, user.id)


def pinned_stories(db: Database, viewer: User, owner_id: int) -> list[dict]:
    """Pinned stories that are still public (a story made private again disappears from the profile)."""
    from .stories import story_dict
    rows = db.all("SELECT s.* FROM profile_pins p JOIN stories s ON s.id=p.story_id WHERE p.user_id=? "
                  "AND s.visibility='public' ORDER BY p.position", (owner_id,))
    return [story_dict(db, r, full=False, user=viewer) for r in rows]
