"""HTTP API (FastAPI)."""
from __future__ import annotations

import asyncio
import io
import logging
import os
import sqlite3
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from . import llm, nick as nickmod, rooms as R, stories as S
from .common import ApiError, User, auth_user, client_ip, hash_token, hub, new_id, new_token, not_found
from .config import settings
from .db import Database, now_ms
from .ratelimit import limiter
from .worker import Worker

log = logging.getLogger("fonar")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


class State:
    db: Database
    worker: Worker


state = State()


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(settings.images_dir, exist_ok=True)
    state.db = Database(settings.db_path)
    state.worker = Worker(state.db)
    state.worker.start()
    warm = asyncio.create_task(llm.warmup())
    yield
    warm.cancel()
    await state.worker.stop()
    state.db.close()


app = FastAPI(title="Fonar API", version="1.0", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.exception_handler(RequestValidationError)
async def _validation(request: Request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    loc = ".".join(str(x) for x in first.get("loc", []) if x != "body")
    return JSONResponse(status_code=400, content={"detail": {"code": "bad_request",
                                                             "message": f"Некорректные данные ({loc})."}})


@app.exception_handler(sqlite3.IntegrityError)
async def _integrity(request: Request, exc: sqlite3.IntegrityError):
    return JSONResponse(status_code=409, content={"detail": {"code": "conflict", "message": "Конфликт данных, повтори."}})


async def db() -> Database:
    return state.db


async def current_user(request: Request) -> User:
    return auth_user(state.db, request)


def rate(key: str, limit: int, window: float, msg: str = "Слишком часто. Подожди немного.") -> None:
    wait = limiter.check(key, limit, window)
    if wait is not None:
        raise ApiError(429, "rate_limited", msg, retry_after=wait)


# ---------------------------------------------------------------------------
# health
# ---------------------------------------------------------------------------
@app.get("/v1/health")
async def health():
    return {"ok": True, "model": settings.llm_model, "model_ready": await llm.model_available(),
            "queue": state.worker.queue_length(), "busy": state.worker.busy}


# ---------------------------------------------------------------------------
# registration — nickname only, no login-by-nick endpoint exists
# ---------------------------------------------------------------------------
class RegisterIn(BaseModel):
    nick: str = Field(max_length=64)


@app.post("/v1/register", status_code=201)
async def register(body: RegisterIn, request: Request, d: Database = Depends(db)):
    ip = client_ip(request)
    try:
        nick = nickmod.validate(body.nick)
    except nickmod.NickError as e:
        raise ApiError(400, e.code, e.message)
    rate(f"reg:{ip}", settings.rl_register_per_hour, 3600, "Слишком много регистраций с этого адреса. Попробуй позже.")
    key = nickmod.key(nick)
    if d.one("SELECT 1 FROM users WHERE nick_key=?", (key,)):
        raise ApiError(409, "nick_taken", "Этот ник уже занят. Придумай другой.")
    token = new_token()
    ts = now_ms()
    try:
        with d.tx():
            cur = d.run("INSERT INTO users(public_id, nick, nick_key, created_at) VALUES(?,?,?,?)", (new_id(), nick, key, ts))
            d.run("INSERT INTO sessions(token_hash, user_id, created_at, last_seen_at) VALUES(?,?,?,?)",
                  (hash_token(token), cur.lastrowid, ts, ts))
    except sqlite3.IntegrityError:
        raise ApiError(409, "nick_taken", "Этот ник уже занят. Придумай другой.")
    u = d.one("SELECT * FROM users WHERE id=?", (cur.lastrowid,))
    user = User(u["id"], u["public_id"], u["nick"])
    try:
        demo = S.create_demo_story(d, user)
    except Exception:  # the account must exist even if seeding fails
        log.exception("demo seeding failed")
        demo = None
    return {"token": token, "user": {"id": u["public_id"], "nick": u["nick"]},
            "demo_story_id": demo["id"] if demo else None}


@app.get("/v1/me")
async def me(user: User = Depends(current_user)):
    return {"user": {"id": user.public_id, "nick": user.nick}}


@app.post("/v1/logout")
async def logout(request: Request, user: User = Depends(current_user), d: Database = Depends(db)):
    token = request.headers.get("authorization", "")[7:].strip()
    d.run("DELETE FROM sessions WHERE token_hash=?", (hash_token(token),))
    return {"ok": True}


# ---------------------------------------------------------------------------
# friends — exact nickname search only, no user directory
# ---------------------------------------------------------------------------
def _relation(d: Database, me_id: int, other_id: int) -> tuple[str, str | None]:
    if me_id == other_id:
        return "self", None
    out = d.one("SELECT * FROM friend_requests WHERE from_user=? AND to_user=?", (me_id, other_id))
    inc = d.one("SELECT * FROM friend_requests WHERE from_user=? AND to_user=?", (other_id, me_id))
    if (out and out["status"] == "accepted") or (inc and inc["status"] == "accepted"):
        return "friends", (out or inc)["public_id"]
    if inc and inc["status"] == "pending":
        return "incoming_pending", inc["public_id"]
    if out:
        return f"outgoing_{out['status']}", out["public_id"]
    return "none", None


@app.get("/v1/users/search")
async def search_user(nick: str, user: User = Depends(current_user), d: Database = Depends(db)):
    rate(f"search:{user.id}", settings.rl_search_per_min, 60)
    rate(f"search-day:{user.id}", settings.rl_search_per_day, 86400, "Лимит поиска на сегодня исчерпан.")
    q = nickmod.clean(nick)
    if len(q) < nickmod.MIN_LEN or len(q) > nickmod.MAX_LEN:
        raise not_found("Игрок с таким ником не найден")
    row = d.one("SELECT id, public_id, nick FROM users WHERE nick_key=?", (nickmod.key(q),))
    if not row:
        raise not_found("Игрок с таким ником не найден")
    rel, rid = _relation(d, user.id, row["id"])
    return {"user": {"id": row["public_id"], "nick": row["nick"]}, "relation": rel, "request_id": rid}


class FriendRequestIn(BaseModel):
    nick: str = Field(max_length=64)


def _req_dict(d: Database, r, me_id: int) -> dict:
    other = r["to_user"] if r["from_user"] == me_id else r["from_user"]
    u = d.one("SELECT public_id, nick FROM users WHERE id=?", (other,))
    return {"id": r["public_id"], "status": r["status"],
            "direction": "outgoing" if r["from_user"] == me_id else "incoming",
            "user": {"id": u["public_id"], "nick": u["nick"]}, "updated_at": r["updated_at"]}


@app.post("/v1/friends/requests")
async def send_friend_request(body: FriendRequestIn, user: User = Depends(current_user), d: Database = Depends(db)):
    q = nickmod.clean(body.nick)
    row = d.one("SELECT id, public_id, nick FROM users WHERE nick_key=?", (nickmod.key(q),)) if q else None
    if not row:
        raise not_found("Игрок с таким ником не найден")
    if row["id"] == user.id:
        raise ApiError(400, "self_request", "Нельзя отправить заявку самому себе.")
    ts = now_ms()
    out = d.one("SELECT * FROM friend_requests WHERE from_user=? AND to_user=?", (user.id, row["id"]))
    inc = d.one("SELECT * FROM friend_requests WHERE from_user=? AND to_user=?", (row["id"], user.id))
    if (out and out["status"] == "accepted") or (inc and inc["status"] == "accepted"):
        return {"request": _req_dict(d, out or inc, user.id), "created": False, "already_friends": True}
    if inc and inc["status"] == "pending":
        # they already asked us — sending back means "yes"
        with d.tx():
            d.run("UPDATE friend_requests SET status='accepted', updated_at=? WHERE id=?", (ts, inc["id"]))
        hub.notify(f"user:{row['id']}")
        return {"request": _req_dict(d, d.one("SELECT * FROM friend_requests WHERE id=?", (inc["id"],)), user.id),
                "created": False, "already_friends": True}
    if out and out["status"] == "pending":
        return {"request": _req_dict(d, out, user.id), "created": False, "already_friends": False}
    rate(f"freq:{user.id}", settings.rl_friend_req_per_hour, 3600, "Слишком много заявок. Попробуй позже.")
    with d.tx():
        if out:  # previously declined → re-open the same request, no duplicate rows
            d.run("UPDATE friend_requests SET status='pending', updated_at=? WHERE id=?", (ts, out["id"]))
            rid = out["id"]
        else:
            rid = d.run("INSERT INTO friend_requests(public_id, from_user, to_user, status, created_at, updated_at) "
                        "VALUES(?,?,?, 'pending', ?, ?)", (new_id(), user.id, row["id"], ts, ts)).lastrowid
    hub.notify(f"user:{row['id']}")
    return {"request": _req_dict(d, d.one("SELECT * FROM friend_requests WHERE id=?", (rid,)), user.id),
            "created": out is None, "already_friends": False}


@app.get("/v1/friends")
async def friends(user: User = Depends(current_user), d: Database = Depends(db)):
    rows = d.all("SELECT * FROM friend_requests WHERE from_user=? OR to_user=? ORDER BY updated_at DESC", (user.id, user.id))
    fr, inc, outg = [], [], []
    seen = set()
    for r in rows:
        item = _req_dict(d, r, user.id)
        if r["status"] == "accepted" and item["user"]["id"] not in seen:
            seen.add(item["user"]["id"])
            fr.append(item["user"])
        if item["direction"] == "incoming":
            if r["status"] == "pending":
                inc.append(item)
        else:
            outg.append(item)  # sent / accepted / declined — the sender sees every state
    return {"friends": fr, "incoming": inc, "outgoing": outg, "invites": R.list_invites(d, user)}


def _answer_request(d: Database, user: User, rid: str, accept: bool) -> dict:
    r = d.one("SELECT * FROM friend_requests WHERE public_id=?", (rid,))
    if not r or r["to_user"] != user.id:
        raise not_found("Заявка не найдена")
    if r["status"] != "pending":
        return {"request": _req_dict(d, r, user.id)}
    with d.tx():
        d.run("UPDATE friend_requests SET status=?, updated_at=? WHERE id=?",
              ("accepted" if accept else "declined", now_ms(), r["id"]))
    hub.notify(f"user:{r['from_user']}")
    return {"request": _req_dict(d, d.one("SELECT * FROM friend_requests WHERE id=?", (r["id"],)), user.id)}


@app.post("/v1/friends/requests/{rid}/accept")
async def accept_request(rid: str, user: User = Depends(current_user), d: Database = Depends(db)):
    return _answer_request(d, user, rid, True)


@app.post("/v1/friends/requests/{rid}/decline")
async def decline_request(rid: str, user: User = Depends(current_user), d: Database = Depends(db)):
    return _answer_request(d, user, rid, False)


@app.get("/v1/inbox/wait")
async def inbox_wait(since: int = 0, wait: int = 25, user: User = Depends(current_user)):
    """Long-poll that returns when friend requests / invites for this user change."""
    key = f"user:{user.id}"
    v = hub.version(key)
    if since >= v and wait > 0:
        await hub.wait(key, min(wait, settings.sync_wait_max_s))
    return {"version": hub.version(key)}


# ---------------------------------------------------------------------------
# images
# ---------------------------------------------------------------------------
def _process_image(raw: bytes) -> tuple[bytes, int, int]:
    from PIL import Image, ImageOps

    img = Image.open(io.BytesIO(raw))
    img.load()
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB",):
        bg = Image.new("RGB", img.size, (16, 18, 32))
        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            img = img.convert("RGBA")
            bg.paste(img, mask=img.split()[-1])
            img = bg
        else:
            img = img.convert("RGB")
    img.thumbnail((1280, 1280))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=85, optimize=True)  # re-encode strips EXIF/GPS
    return out.getvalue(), img.width, img.height


@app.post("/v1/images", status_code=201)
async def upload_image(file: UploadFile = File(...), user: User = Depends(current_user)):
    rate(f"upload:{user.id}", settings.rl_uploads_per_hour, 3600)
    raw = await file.read(settings.max_image_bytes + 1)
    if len(raw) > settings.max_image_bytes:
        raise ApiError(413, "too_large", "Картинка слишком большая (максимум 6 МБ).")
    try:
        data, w, h = await asyncio.to_thread(_process_image, raw)
    except Exception:
        raise ApiError(400, "bad_image", "Не удалось прочитать картинку. Выбери JPG или PNG.")
    iid = new_id(16)
    path = os.path.join(settings.images_dir, iid + ".jpg")
    with open(path, "wb") as f:
        f.write(data)
    state.db.run("INSERT INTO images(id, owner_id, mime, size, width, height, created_at) VALUES(?,?,?,?,?,?,?)",
                 (iid, user.id, "image/jpeg", len(data), w, h, now_ms()))
    return {"id": iid, "width": w, "height": h}


def _image_response(iid: str) -> FileResponse:
    path = os.path.join(settings.images_dir, iid + ".jpg")
    if not os.path.exists(path):
        raise not_found("Изображение не найдено")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


@app.get("/v1/images/{iid}")
async def get_own_image(iid: str, user: User = Depends(current_user), d: Database = Depends(db)):
    row = d.one("SELECT owner_id FROM images WHERE id=?", (iid,))
    if not row or row["owner_id"] != user.id:
        raise not_found("Изображение не найдено")
    return _image_response(iid)


@app.get("/v1/rooms/{room_id}/images/{iid}")
async def get_room_image(room_id: str, iid: str, user: User = Depends(current_user), d: Database = Depends(db)):
    if not R.room_image_allowed(d, user, room_id, iid):
        raise not_found("Изображение не найдено")
    return _image_response(iid)


# ---------------------------------------------------------------------------
# stories & characters (owner only)
# ---------------------------------------------------------------------------
@app.get("/v1/stories")
async def stories(user: User = Depends(current_user), d: Database = Depends(db)):
    return {"stories": S.list_stories(d, user)}


@app.post("/v1/stories", status_code=201)
async def create_story(body: S.StoryIn, user: User = Depends(current_user), d: Database = Depends(db)):
    rate(f"story:{user.id}", 60, 3600)
    return {"story": S.create_story(d, user, body)}


@app.post("/v1/stories/quick", status_code=201)
async def quick_story(body: S.QuickStoryIn, user: User = Depends(current_user), d: Database = Depends(db)):
    rate(f"story:{user.id}", 60, 3600)
    return {"story": S.quick_story(d, user, body)}


@app.post("/v1/stories/demo", status_code=201)
async def demo_story(user: User = Depends(current_user), d: Database = Depends(db)):
    rate(f"story:{user.id}", 60, 3600)
    return {"story": S.create_demo_story(d, user)}


@app.get("/v1/stories/{sid}")
async def get_story(sid: str, user: User = Depends(current_user), d: Database = Depends(db)):
    return {"story": S.story_dict(d, S.story_row(d, user, sid))}


@app.put("/v1/stories/{sid}")
async def put_story(sid: str, body: S.StoryIn, user: User = Depends(current_user), d: Database = Depends(db)):
    return {"story": S.replace_story(d, user, sid, body)}


@app.delete("/v1/stories/{sid}")
async def del_story(sid: str, user: User = Depends(current_user), d: Database = Depends(db)):
    S.delete_story(d, user, sid)
    return {"ok": True}


@app.patch("/v1/stories/{sid}/characters/{cid}")
async def patch_character(sid: str, cid: str, body: S.CharacterPatch, user: User = Depends(current_user),
                    d: Database = Depends(db)):
    return {"character": S.patch_character(d, user, sid, cid, body)}


# ---------------------------------------------------------------------------
# rooms
# ---------------------------------------------------------------------------
@app.post("/v1/stories/{sid}/rooms", status_code=201)
async def create_room(sid: str, user: User = Depends(current_user), d: Database = Depends(db)):
    rate(f"room:{user.id}", 60, 3600)
    return {"room": R.create_room(d, user, sid)}


@app.get("/v1/rooms")
async def rooms(user: User = Depends(current_user), d: Database = Depends(db)):
    return {"rooms": R.list_rooms(d, user), "invites": R.list_invites(d, user)}


@app.get("/v1/rooms/{room_id}")
async def room(room_id: str, user: User = Depends(current_user), d: Database = Depends(db)):
    return {"room": R.room_detail(d, user, R.member_room(d, user, room_id))}


@app.delete("/v1/rooms/{room_id}")
async def delete_room(room_id: str, user: User = Depends(current_user), d: Database = Depends(db)):
    R.delete_room(d, user, room_id)
    return {"ok": True}


@app.post("/v1/rooms/{room_id}/invite")
async def invite(room_id: str, body: R.InviteIn, user: User = Depends(current_user), d: Database = Depends(db)):
    rate(f"invite:{user.id}", 30, 3600, "Слишком много приглашений. Попробуй позже.")
    return {"invite": R.invite(d, user, room_id, body.user_id)}


@app.get("/v1/invites")
async def invites(user: User = Depends(current_user), d: Database = Depends(db)):
    return {"invites": R.list_invites(d, user)}


@app.post("/v1/invites/{iid}/accept")
async def accept_invite(iid: str, user: User = Depends(current_user), d: Database = Depends(db)):
    return {"invite": R.answer_invite(d, user, iid, True)}


@app.post("/v1/invites/{iid}/decline")
async def decline_invite(iid: str, user: User = Depends(current_user), d: Database = Depends(db)):
    return {"invite": R.answer_invite(d, user, iid, False)}


@app.get("/v1/rooms/{room_id}/sync")
async def sync(room_id: str, since: int = 0, pv: int = -1, wait: int = 0, user: User = Depends(current_user)):
    """Returns everything that changed after revision ``since``. With ``wait`` > 0
    it long-polls until something changes (new/hidden messages, generation
    progress, card edits) or the timeout passes. ``pv`` is the partial-text
    version the client already has."""
    d = state.db
    room = R.member_room(d, user, room_id)
    key = f"room:{room['id']}"

    def partial_v() -> int:
        p = hub.partial.get(room["id"])
        return p["v"] if p else -1

    if wait > 0 and room["rev"] <= since and partial_v() == pv:
        await hub.wait(key, min(wait, settings.sync_wait_max_s))
        room = R.member_room(d, user, room_id)  # re-check membership after waiting
    payload = R.sync_payload(d, user, room, since)
    payload["pv"] = partial_v()
    return payload


@app.post("/v1/rooms/{room_id}/messages", status_code=201)
async def post_message(room_id: str, body: R.MessageIn, user: User = Depends(current_user), d: Database = Depends(db)):
    rate(f"msg:{user.id}", settings.rl_messages_per_min, 60)
    return R.post_message(d, user, room_id, body, state.worker.wake)


@app.post("/v1/rooms/{room_id}/continue")
async def continue_scene(room_id: str, body: R.ActionIn, user: User = Depends(current_user), d: Database = Depends(db)):
    rate(f"msg:{user.id}", settings.rl_messages_per_min, 60)
    return R.request_generation(d, user, room_id, "continue", body.client_id, state.worker.wake)


@app.post("/v1/rooms/{room_id}/regenerate")
async def regenerate(room_id: str, body: R.ActionIn, user: User = Depends(current_user), d: Database = Depends(db)):
    rate(f"msg:{user.id}", settings.rl_messages_per_min, 60)
    return R.request_generation(d, user, room_id, "regenerate", body.client_id, state.worker.wake)


@app.post("/v1/rooms/{room_id}/retry")
async def retry(room_id: str, body: R.ActionIn, user: User = Depends(current_user), d: Database = Depends(db)):
    rate(f"msg:{user.id}", settings.rl_messages_per_min, 60)
    return R.request_generation(d, user, room_id, "retry", body.client_id, state.worker.wake)


@app.patch("/v1/rooms/{room_id}/scene")
async def scene(room_id: str, body: R.SceneIn, user: User = Depends(current_user), d: Database = Depends(db)):
    return R.set_scene(d, user, room_id, body)


@app.get("/v1/rooms/{room_id}/last-prompt")
async def last_prompt(room_id: str, user: User = Depends(current_user), d: Database = Depends(db)):
    return R.last_prompt(d, user, room_id)
