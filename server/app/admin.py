"""Admin page data: every user with tokens spent on text / avatars / scene photos, and players' photos."""
from __future__ import annotations

from .config import settings
from .db import Database


def users(db: Database) -> dict:
    rows = db.all(
        "SELECT u.id, u.public_id, u.nick, u.created_at, (u.password_hash IS NOT NULL) has_password, "
        "(SELECT MAX(last_seen_at) FROM sessions s WHERE s.user_id=u.id) last_seen, "
        "(SELECT COUNT(*) FROM personas p WHERE p.author_id=u.id) personas, "
        "(SELECT COUNT(*) FROM rooms r WHERE r.owner_id=u.id) rooms, "
        "(SELECT COUNT(*) FROM images i WHERE i.owner_id=u.id AND i.purpose='chat') photos "
        "FROM users u ORDER BY u.created_at DESC")
    usage: dict[int, dict] = {}
    for r in db.all("SELECT user_id, kind, model, SUM(prompt_tokens) pt, SUM(completion_tokens) ct, SUM(cost) cost, COUNT(*) n "
                    "FROM usage_events GROUP BY user_id, kind, model"):
        u = usage.setdefault(r["user_id"], {"text": 0, "avatar": 0, "avatars": 0, "photo": 0, "scene_photos": 0, "cost": 0.0})
        tokens = (r["pt"] or 0) + (r["ct"] or 0)
        u[r["kind"]] = u.get(r["kind"], 0) + tokens
        if r["kind"] == "avatar" and r["model"] == settings.cloud_image_model:
            u["avatars"] += r["n"]
        if r["kind"] == "photo":
            u["scene_photos"] += r["n"]
        u["cost"] += r["cost"] or 0.0
    out, total = [], {"text": 0, "avatar": 0, "photo": 0, "cost": 0.0, "users": len(rows)}
    for r in rows:
        u = usage.get(r["id"], {})
        item = {
            "id": r["public_id"], "nick": r["nick"], "created_at": r["created_at"], "last_seen_at": r["last_seen"],
            "has_password": bool(r["has_password"]), "personas": r["personas"], "rooms": r["rooms"], "photos": r["photos"],
            "text_tokens": u.get("text", 0), "avatar_tokens": u.get("avatar", 0), "avatars": u.get("avatars", 0),
            "photo_tokens": u.get("photo", 0), "scene_photos": u.get("scene_photos", 0), "cost": round(u.get("cost", 0.0), 4),
        }
        for k in ("text", "avatar", "photo"):
            total[k] += item[f"{k}_tokens"]
        total["cost"] += item["cost"]
        out.append(item)
    # usage of deleted accounts still counts in the totals
    orphan = db.one("SELECT SUM(prompt_tokens+completion_tokens) t, SUM(cost) c FROM usage_events WHERE user_id IS NULL")
    total["cost"] = round(total["cost"] + (orphan["c"] or 0.0), 4)
    return {"users": out, "total": total}


def photos(db: Database) -> dict:
    rows = db.all(
        "SELECT i.id, i.size, i.width, i.height, i.created_at, i.expires_at, u.nick, "
        "(SELECT COALESCE(s.title, r.title) FROM messages m JOIN rooms r ON r.id=m.room_id LEFT JOIN stories s ON s.id=r.story_id "
        " WHERE m.image_id=i.id LIMIT 1) room_title "
        "FROM images i LEFT JOIN users u ON u.id=i.owner_id WHERE i.purpose='chat' ORDER BY i.created_at DESC LIMIT 500")
    return {"photos": [{"id": r["id"], "nick": r["nick"], "room": r["room_title"], "size": r["size"], "width": r["width"],
                        "height": r["height"], "created_at": r["created_at"], "expires_at": r["expires_at"]} for r in rows],
            "ttl_days": settings.chat_photo_ttl_days}


def delete_user(db: Database, public_id: str) -> dict | None:
    """Removes an account with everything it made: characters, stories, its chats and scenes, pictures.
    Scenes where it was only a guest stay with their owner (the seat becomes free)."""
    from .common import hub
    from .images import delete_image_files
    from .rooms import _bump
    u = db.one("SELECT id, nick FROM users WHERE public_id=?", (public_id,))
    if not u:
        return None
    uid = u["id"]
    images = [r["id"] for r in db.all("SELECT id FROM images WHERE owner_id=?", (uid,))]
    guest_rooms = [r["id"] for r in db.all("SELECT id FROM rooms WHERE guest_id=?", (uid,))]
    owned = [r["id"] for r in db.all("SELECT id FROM rooms WHERE owner_id=?", (uid,))]
    with db.tx():
        # its pictures in other people's scenes become a short note instead of a broken image
        for iid in images:
            for m in db.all("SELECT id, room_id FROM messages WHERE image_id=?", (iid,)):
                if m["room_id"] not in owned:
                    rev = _bump(db, m["room_id"])
                    db.run("UPDATE messages SET image_id=NULL, kind='system', text='Картинка удалена.', rev=? WHERE id=?",
                           (rev, m["id"]))
        db.run("DELETE FROM users WHERE id=?", (uid,))  # cascades: sessions, friends, stories, rooms, personas, images
        for rid in guest_rooms:
            _bump(db, rid, meta=True)
    delete_image_files(images)
    for rid in guest_rooms + owned:
        hub.notify(f"room:{rid}")
    return {"nick": u["nick"], "rooms": len(owned), "images": len(images)}
