"""HTTP API (FastAPI)."""
from __future__ import annotations

import asyncio
import hmac
import io
import logging
import os
import secrets
import sqlite3
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from . import admin as A, llm, nick as nickmod, personas as PS, rooms as R, stories as S
from .common import (ApiError, User, auth_user, client_ip, hash_password, hash_token, hub, new_id, new_token, not_found,
                     verify_password)
from .config import settings
from .db import Database, now_ms
from .images import process_image, save_image
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
    PS.seed_demo(state.db)
    state.worker = Worker(state.db)
    state.worker.start()
    if not settings.local_ai:  # no local model any more: every room uses the cloud model
        state.db.run("UPDATE rooms SET ai_mode='cloud' WHERE ai_mode<>'cloud'")
    warm = asyncio.create_task(llm.warmup()) if settings.local_ai else None
    yield
    if warm:
        warm.cancel()
    await state.worker.stop()
    state.db.close()


app = FastAPI(title="GramSoul API", version="1.0", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


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
    return {"ok": True, "local_ai": settings.local_ai,
            "model": settings.llm_model if settings.local_ai else None,
            "model_ready": (await llm.model_available()) if settings.local_ai else None,
            "cloud": bool(settings.openrouter_api_key), "cloud_model": settings.cloud_text_model,
            "image_model": settings.cloud_image_model,
            "queue": state.worker.queue_length(), "busy": state.worker.busy}


# ---------------------------------------------------------------------------
# registration — nickname only, no login-by-nick endpoint exists
# ---------------------------------------------------------------------------
class RegisterIn(BaseModel):
    nick: str = Field(max_length=64)
    password: str | None = Field(default=None, max_length=200)  # older app versions register without one


PASSWORD_MIN = 6


def _check_password(pw: str) -> str:
    if len(pw) < PASSWORD_MIN:
        raise ApiError(400, "password_short", f"Пароль — не короче {PASSWORD_MIN} символов.")
    if len(pw) > 128:
        raise ApiError(400, "password_long", "Пароль слишком длинный (максимум 128 символов).")
    if pw.strip() == "":
        raise ApiError(400, "password_blank", "Пароль не может состоять из пробелов.")
    return pw


@app.post("/v1/register", status_code=201)
async def register(body: RegisterIn, request: Request, d: Database = Depends(db)):
    ip = client_ip(request)
    try:
        nick = nickmod.validate(body.nick)
    except nickmod.NickError as e:
        raise ApiError(400, e.code, e.message)
    pw_hash = None
    if body.password is not None:
        pw_hash = await asyncio.to_thread(hash_password, _check_password(body.password))
    rate(f"reg:{ip}", settings.rl_register_per_hour, 3600, "Слишком много регистраций с этого адреса. Попробуй позже.")
    key = nickmod.key(nick)
    if d.one("SELECT 1 FROM users WHERE nick_key=?", (key,)):
        raise ApiError(409, "nick_taken", "Этот ник уже занят. Придумай другой.")
    token = new_token()
    ts = now_ms()
    try:
        with d.tx():
            cur = d.run("INSERT INTO users(public_id, nick, nick_key, password_hash, created_at) VALUES(?,?,?,?,?)",
                        (new_id(), nick, key, pw_hash, ts))
            d.run("INSERT INTO sessions(token_hash, user_id, created_at, last_seen_at) VALUES(?,?,?,?)",
                  (hash_token(token), cur.lastrowid, ts, ts))
    except sqlite3.IntegrityError:
        raise ApiError(409, "nick_taken", "Этот ник уже занят. Придумай другой.")
    u = d.one("SELECT * FROM users WHERE id=?", (cur.lastrowid,))
    user = User(u["id"], u["public_id"], u["nick"])
    demo = None
    if settings.demo_content:  # sample story only in tests
        try:
            demo = S.create_demo_story(d, user)
        except Exception:  # the account must exist even if seeding fails
            log.exception("demo seeding failed")
    return {"token": token, "user": _me_dict(u), "demo_story_id": demo["id"] if demo else None}


def _user_dict(row) -> dict:
    """Public profile of a user: what anyone who finds them by nick may see."""
    return {"id": row["public_id"], "nick": row["nick"], "avatar_image_id": row["avatar_image_id"],
            "about": row["about"] or ""}


def _user_by_id(d: Database, uid: int):
    return d.one("SELECT id, public_id, nick, avatar_image_id, about FROM users WHERE id=?", (uid,))


def _last_seen(d: Database, ids: list[int]) -> dict[int, int]:
    if not ids:
        return {}
    marks = ",".join("?" * len(ids))
    rows = d.all(f"SELECT user_id, MAX(last_seen_at) t FROM sessions WHERE user_id IN ({marks}) GROUP BY user_id", ids)
    return {r["user_id"]: r["t"] for r in rows}


def _with_presence(item: dict, last_seen: int | None) -> dict:
    item["last_seen_at"] = last_seen
    item["online"] = bool(last_seen and now_ms() - last_seen < settings.online_window_s * 1000)
    return item


def _me_dict(row) -> dict:
    """Own profile: the public part plus whether a password is set (the app asks for one if not)."""
    full = row if "password_hash" in row.keys() else None
    out = _user_dict(row)
    out["has_password"] = bool(full["password_hash"]) if full is not None else False
    return out


def _me_row(d: Database, uid: int):
    return d.one("SELECT id, public_id, nick, avatar_image_id, about, password_hash FROM users WHERE id=?", (uid,))


@app.get("/v1/me")
async def me(user: User = Depends(current_user), d: Database = Depends(db)):
    return {"user": _me_dict(_me_row(d, user.id))}


class LoginIn(BaseModel):
    nick: str = Field(max_length=64)
    password: str = Field(max_length=200)


@app.post("/v1/login", status_code=201)
async def login(body: LoginIn, request: Request, d: Database = Depends(db)):
    """Nick + password. One generic error for an unknown nick, a wrong password or an account
    that has no password yet — nothing tells which nicks exist."""
    rate(f"login:{client_ip(request)}", 10, 600, "Слишком много попыток входа. Подожди 10 минут.")
    bad = ApiError(400, "bad_credentials", "Неверный ник или пароль.")
    q = nickmod.clean(body.nick)
    u = d.one("SELECT id, password_hash FROM users WHERE nick_key=?", (nickmod.key(q),)) if q else None
    if u is not None:
        rate(f"login-user:{u['id']}", 10, 3600, "Слишком много попыток для этого ника. Попробуй через час.")
    stored = u["password_hash"] if u else None
    ok = await asyncio.to_thread(verify_password, body.password, stored or _DUMMY_HASH)
    if not u or not stored or not ok:
        raise bad
    token = new_token()
    ts = now_ms()
    d.run("INSERT INTO sessions(token_hash, user_id, created_at, last_seen_at) VALUES(?,?,?,?)", (hash_token(token), u["id"], ts, ts))
    return {"token": token, "user": _me_dict(_me_row(d, u["id"]))}


_DUMMY_HASH = hash_password("timing-equaliser")  # unknown nicks cost the same time as real ones


class PasswordIn(BaseModel):
    password: str = Field(max_length=200)
    old_password: str | None = Field(default=None, max_length=200)


@app.post("/v1/me/password")
async def set_password(body: PasswordIn, user: User = Depends(current_user), d: Database = Depends(db)):
    """First password for an existing account, or a change (then the old one is needed)."""
    rate(f"pw:{user.id}", 10, 3600, "Слишком много попыток. Попробуй позже.")
    row = _me_row(d, user.id)
    if row["password_hash"]:
        if not body.old_password or not await asyncio.to_thread(verify_password, body.old_password, row["password_hash"]):
            raise ApiError(400, "bad_old_password", "Старый пароль неверный.")
    new_hash = await asyncio.to_thread(hash_password, _check_password(body.password))
    d.run("UPDATE users SET password_hash=? WHERE id=?", (new_hash, user.id))
    return {"user": _me_dict(_me_row(d, user.id))}


class ProfileIn(BaseModel):
    about: str | None = Field(default=None, max_length=2000)
    avatar_image_id: str | None = Field(default=None, max_length=64)
    nick: str | None = Field(default=None, max_length=64)


@app.patch("/v1/me")
async def update_me(body: ProfileIn, user: User = Depends(current_user), d: Database = Depends(db)):
    sets, params = [], []
    if "about" in body.model_fields_set:
        about = (body.about or "").strip()
        if len(about) > settings.about_max_chars:
            raise ApiError(400, "about_too_long", f"«О себе» — не длиннее {settings.about_max_chars} символов.")
        sets.append("about=?")
        params.append(about)
    if "avatar_image_id" in body.model_fields_set:
        iid = body.avatar_image_id or None
        if iid:
            row = d.one("SELECT owner_id FROM images WHERE id=?", (iid,))
            if not row or row["owner_id"] != user.id:
                raise not_found("Картинка не найдена")
        sets.append("avatar_image_id=?")
        params.append(iid)
    if "nick" in body.model_fields_set and body.nick is not None:
        try:
            nick = nickmod.validate(body.nick)
        except nickmod.NickError as e:
            raise ApiError(400, e.code, e.message)
        if nick != user.nick:
            key = nickmod.key(nick)
            if d.one("SELECT 1 FROM users WHERE nick_key=? AND id<>?", (key, user.id)):
                raise ApiError(409, "nick_taken", "Этот ник уже занят. Придумай другой.")
            rate(f"nick:{user.id}", settings.rl_nick_changes_per_day, 86400, f"Ник можно менять не чаще {settings.rl_nick_changes_per_day} раз в сутки.")
            try:
                with d.tx():
                    d.run("UPDATE users SET nick=?, nick_key=? WHERE id=?", (nick, key, user.id))
                    rooms = R.rename_player(d, user.id, user.nick, nick)
            except sqlite3.IntegrityError:
                raise ApiError(409, "nick_taken", "Этот ник уже занят. Придумай другой.")
            for rid in rooms:
                hub.notify(f"room:{rid}")
    if sets:
        d.run(f"UPDATE users SET {', '.join(sets)} WHERE id=?", (*params, user.id))
    return {"user": _me_dict(_me_row(d, user.id))}


@app.get("/v1/users/{uid}/avatar")
async def user_avatar(uid: str, user: User = Depends(current_user), d: Database = Depends(db)):
    row = d.one("SELECT avatar_image_id FROM users WHERE public_id=?", (uid,))
    if not row or not row["avatar_image_id"]:
        raise not_found("Аватара нет")
    return _image_response(row["avatar_image_id"])


# --- moving an account to another phone: one-time code, created on the old phone ---
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I/L


def _norm_code(code: str) -> str:
    return "".join(ch for ch in (code or "").upper() if ch.isalnum())


@app.post("/v1/me/transfer-code")
async def create_transfer_code(user: User = Depends(current_user), d: Database = Depends(db)):
    rate(f"tcode:{user.id}", 10, 3600, "Слишком много кодов подряд. Попробуй позже.")
    code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(8))
    ts = now_ms()
    expires = ts + settings.transfer_code_ttl_s * 1000
    with d.tx():
        # only the newest code works
        d.run("UPDATE transfer_codes SET used_at=? WHERE user_id=? AND used_at IS NULL", (ts, user.id))
        d.run("INSERT INTO transfer_codes(user_id, code_hash, created_at, expires_at) VALUES(?,?,?,?)",
              (user.id, hash_token(code), ts, expires))
    return {"code": code[:4] + "-" + code[4:], "expires_at": expires, "ttl_s": settings.transfer_code_ttl_s}


class TransferLoginIn(BaseModel):
    nick: str = Field(max_length=64)
    code: str = Field(max_length=32)


@app.post("/v1/login/transfer", status_code=201)
async def login_with_transfer_code(body: TransferLoginIn, request: Request, d: Database = Depends(db)):
    rate(f"tlogin:{client_ip(request)}", 10, 600, "Слишком много попыток. Подожди 10 минут.")
    bad = ApiError(400, "bad_transfer_code",
                   "Неверный ник или код, либо код истёк. Создай новый код в профиле на старом телефоне.")
    q = nickmod.clean(body.nick)
    u = d.one("SELECT id FROM users WHERE nick_key=?", (nickmod.key(q),)) if q else None
    if not u:
        raise bad
    rate(f"tlogin-user:{u['id']}", 10, 3600, "Слишком много попыток для этого ника. Попробуй через час.")
    ts = now_ms()
    c = d.one("SELECT * FROM transfer_codes WHERE user_id=? AND used_at IS NULL AND expires_at>? ORDER BY id DESC LIMIT 1",
              (u["id"], ts))
    if not c or c["attempts"] >= settings.transfer_code_attempts:
        raise bad
    code = _norm_code(body.code)
    if len(code) != 8 or not hmac.compare_digest(hash_token(code), c["code_hash"]):
        d.run("UPDATE transfer_codes SET attempts=attempts+1 WHERE id=?", (c["id"],))
        raise bad
    token = new_token()
    with d.tx():
        d.run("UPDATE transfer_codes SET used_at=? WHERE id=?", (ts, c["id"]))
        d.run("INSERT INTO sessions(token_hash, user_id, created_at, last_seen_at) VALUES(?,?,?,?)",
              (hash_token(token), u["id"], ts, ts))
    return {"token": token, "user": _me_dict(_me_row(d, u["id"]))}


@app.post("/v1/logout")
async def logout(request: Request, user: User = Depends(current_user), d: Database = Depends(db)):
    token = request.headers.get("authorization", "")[7:].strip()
    d.run("DELETE FROM sessions WHERE token_hash=?", (hash_token(token),))
    return {"ok": True}


# ---------------------------------------------------------------------------
# friends and people search
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
async def search_user(q: str | None = None, nick: str | None = None, user: User = Depends(current_user),
                      d: Database = Depends(db)):
    """?q= — by the start of a nick or any part of it (case-insensitive, look-alike letters folded),
    up to 20 people. ?nick= — exact match (kept for older app versions)."""
    rate(f"search:{user.id}", settings.rl_search_per_min, 60)
    rate(f"search-day:{user.id}", settings.rl_search_per_day, 86400, "Лимит поиска на сегодня исчерпан.")
    if q is None:
        x = nickmod.clean(nick or "")
        if len(x) < nickmod.MIN_LEN or len(x) > nickmod.MAX_LEN:
            raise not_found("Игрок с таким ником не найден")
        row = d.one("SELECT id, public_id, nick, avatar_image_id, about FROM users WHERE nick_key=?", (nickmod.key(x),))
        if not row:
            raise not_found("Игрок с таким ником не найден")
        rel, rid = _relation(d, user.id, row["id"])
        return {"user": _user_dict(row), "relation": rel, "request_id": rid}
    qk = nickmod.key(nickmod.clean(q))[: nickmod.MAX_LEN]
    if len(qk) < settings.search_min_chars:
        return {"users": []}
    rows = d.all(
        "SELECT id, public_id, nick, avatar_image_id, about, instr(nick_key, ?) AS pos FROM users "
        "WHERE instr(nick_key, ?) > 0 AND id<>? ORDER BY (nick_key=?) DESC, pos, length(nick_key), nick_key LIMIT ?",
        (qk, qk, user.id, qk, settings.search_max_results),
    )
    out = []
    for r in rows:
        rel, rid = _relation(d, user.id, r["id"])
        out.append({"user": _user_dict(r), "relation": rel, "request_id": rid})
    return {"users": out}


@app.get("/v1/users/{uid}")
async def user_profile(uid: str, user: User = Depends(current_user), d: Database = Depends(db)):
    row = d.one("SELECT id, public_id, nick, avatar_image_id, about FROM users WHERE public_id=?", (uid,))
    if not row:
        raise not_found("Игрок не найден")
    rel, rid = _relation(d, user.id, row["id"])
    item = _user_dict(row)
    if rel in ("friends", "outgoing_accepted", "self"):
        _with_presence(item, _last_seen(d, [row["id"]]).get(row["id"]))
    return {"user": item, "relation": rel, "request_id": rid}


class FriendRequestIn(BaseModel):
    nick: str | None = Field(default=None, max_length=64)
    user_id: str | None = Field(default=None, max_length=64)


def _req_dict(d: Database, r, me_id: int) -> dict:
    other = r["to_user"] if r["from_user"] == me_id else r["from_user"]
    u = _user_by_id(d, other)
    return {"id": r["public_id"], "status": r["status"],
            "direction": "outgoing" if r["from_user"] == me_id else "incoming",
            "user": _user_dict(u), "updated_at": r["updated_at"]}


@app.post("/v1/friends/requests")
@app.post("/v1/friends/request")
async def send_friend_request(body: FriendRequestIn, user: User = Depends(current_user), d: Database = Depends(db)):
    if body.user_id:
        row = d.one("SELECT id, public_id, nick FROM users WHERE public_id=?", (body.user_id,))
    else:
        q = nickmod.clean(body.nick or "")
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
    pid_to_id = {r["public_id"]: r["id"] for r in d.all(
        f"SELECT id, public_id FROM users WHERE public_id IN ({','.join('?' * len(fr))})", [f["id"] for f in fr])} if fr else {}
    seen_at = _last_seen(d, list(pid_to_id.values()))
    for f in fr:
        _with_presence(f, seen_at.get(pid_to_id.get(f["id"])))
    fr.sort(key=lambda f: (not f["online"], f["nick"].casefold()))
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


class FriendAnswerIn(BaseModel):
    request_id: str | None = Field(default=None, max_length=64)
    user_id: str | None = Field(default=None, max_length=64)


def _incoming_request_id(d: Database, user: User, body: FriendAnswerIn) -> str:
    if body.request_id:
        return body.request_id
    other = d.one("SELECT id FROM users WHERE public_id=?", (body.user_id or "",))
    r = d.one("SELECT public_id FROM friend_requests WHERE from_user=? AND to_user=? AND status='pending'",
              (other["id"], user.id)) if other else None
    if not r:
        raise not_found("Заявка не найдена")
    return r["public_id"]


@app.post("/v1/friends/accept")
async def accept_friend(body: FriendAnswerIn, user: User = Depends(current_user), d: Database = Depends(db)):
    return _answer_request(d, user, _incoming_request_id(d, user, body), True)


@app.post("/v1/friends/decline")
async def decline_friend(body: FriendAnswerIn, user: User = Depends(current_user), d: Database = Depends(db)):
    return _answer_request(d, user, _incoming_request_id(d, user, body), False)


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
@app.post("/v1/images", status_code=201)
async def upload_image(file: UploadFile = File(...), user: User = Depends(current_user)):
    rate(f"upload:{user.id}", settings.rl_uploads_per_hour, 3600)
    raw = await file.read(settings.max_image_bytes + 1)
    if len(raw) > settings.max_image_bytes:
        raise ApiError(413, "too_large", "Картинка слишком большая (максимум 6 МБ).")
    try:
        data, w, h = await asyncio.to_thread(process_image, raw)
    except Exception:
        raise ApiError(400, "bad_image", "Не удалось прочитать картинку. Выбери JPG или PNG.")
    iid = save_image(state.db, user.id, data, w, h)
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
# personas — standalone characters (simple mode), AI fill, AI avatars
# ---------------------------------------------------------------------------
@app.get("/v1/personas")
async def list_personas(q: str = "", scope: str = "all", user: User = Depends(current_user), d: Database = Depends(db)):
    if scope not in ("all", "mine", "drafts", "public"):
        raise ApiError(400, "bad_scope", "Неизвестный раздел.")
    return PS.listing(d, user, q[:100], scope)


@app.post("/v1/personas", status_code=201)
async def create_persona(body: PS.PersonaIn, user: User = Depends(current_user), d: Database = Depends(db)):
    rate(f"persona:{user.id}", 60, 3600)
    return PS.create(d, user, body)


@app.post("/v1/personas/fill")
async def fill_persona(body: PS.FillIn, user: User = Depends(current_user), d: Database = Depends(db)):
    rate(f"pfill:{user.id}", settings.rl_persona_fill_per_hour, 3600, "Слишком много запросов к ИИ. Попробуй позже.")
    return await PS.fill(user, body, d)


@app.get("/v1/personas/{pid}")
async def get_persona(pid: str, user: User = Depends(current_user), d: Database = Depends(db)):
    out = PS.get(d, user, pid)
    row = d.one("SELECT id FROM personas WHERE public_id=?", (pid,))
    out["persona"]["chats"] = R.chats_with_persona(d, user, row["id"])
    return out


@app.post("/v1/personas/{pid}/chats", status_code=201)
async def start_chat(pid: str, user: User = Depends(current_user), d: Database = Depends(db)):
    """A new personal chat with this character; its first message is always the greeting."""
    rate(f"room:{user.id}", 60, 3600)
    return {"room": R.create_chat(d, user, PS.visible_persona(d, user, pid))}


@app.put("/v1/personas/{pid}")
async def update_persona(pid: str, body: PS.PersonaIn, user: User = Depends(current_user), d: Database = Depends(db)):
    return PS.update(d, user, pid, body)


@app.delete("/v1/personas/{pid}")
async def delete_persona(pid: str, user: User = Depends(current_user), d: Database = Depends(db)):
    return PS.delete(d, user, pid)


@app.get("/v1/personas/{pid}/avatar")
async def persona_avatar(pid: str, user: User = Depends(current_user), d: Database = Depends(db)):
    row = PS.visible_persona(d, user, pid)
    if not row["avatar_image_id"]:
        raise not_found("Аватара нет")
    return _image_response(row["avatar_image_id"])


@app.get("/v1/avatar-styles")
async def avatar_styles(user: User = Depends(current_user)):
    return PS.styles()


@app.post("/v1/avatars/generate")
async def generate_avatar(body: PS.AvatarIn, user: User = Depends(current_user), d: Database = Depends(db)):
    rate(f"avatar-min:{user.id}", 3, 60)
    rate(f"avatar-day:{user.id}", settings.rl_avatars_per_day, 86400, "Лимит генерации аватаров на сегодня исчерпан.")
    return await PS.generate_avatar(d, user, body)


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
    if not settings.demo_content:
        raise not_found("Демо-истории больше нет.")
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


@app.patch("/v1/rooms/{room_id}/messages/{mid}")
async def edit_message(room_id: str, mid: str, body: R.EditIn, user: User = Depends(current_user), d: Database = Depends(db)):
    rate(f"edit:{user.id}", settings.rl_messages_per_min, 60)
    return R.edit_message(d, user, room_id, mid, body)


@app.post("/v1/rooms/{room_id}/suggest")
async def suggest(room_id: str, user: User = Depends(current_user), d: Database = Depends(db)):
    rate(f"suggest:{user.id}", 8, 60, "Слишком часто. Подожди немного.")
    return await R.suggest_replies(d, user, room_id)


@app.post("/v1/rooms/{room_id}/upload", status_code=201)
async def upload_chat_photo(room_id: str, file: UploadFile = File(...), caption: str = Form(""), client_id: str = Form(""),
                            user: User = Depends(current_user), d: Database = Depends(db)):
    """A player's own photo in the chat. Kept for a week, then removed automatically."""
    room = R.member_room(d, user, room_id)
    rate(f"chatphoto:{user.id}", settings.rl_chat_photos_per_hour, 3600, "Слишком много фото за час. Попробуй позже.")
    raw = await file.read(settings.max_image_bytes + 1)
    if len(raw) > settings.max_image_bytes:
        raise ApiError(413, "too_large", "Картинка слишком большая (максимум 6 МБ).")
    try:
        data, w, h = await asyncio.to_thread(process_image, raw, 1600)
    except Exception:
        raise ApiError(400, "bad_image", "Не удалось прочитать картинку. Выбери JPG или PNG.")
    return R.post_photo(d, user, room, data, w, h, caption[:500], client_id[:64] or None)


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


@app.patch("/v1/rooms/{room_id}/settings")
async def room_settings(room_id: str, body: R.RoomSettingsIn, user: User = Depends(current_user), d: Database = Depends(db)):
    return R.set_settings(d, user, room_id, body)


@app.post("/v1/rooms/{room_id}/photo")
async def photo(room_id: str, body: R.PhotoIn, user: User = Depends(current_user), d: Database = Depends(db)):
    rate(f"photo:{user.id}", 6, 60)
    return R.request_photo(d, user, room_id, body, state.worker.wake)


@app.get("/v1/rooms/{room_id}/last-prompt")
async def last_prompt(room_id: str, user: User = Depends(current_user), d: Database = Depends(db)):
    return R.last_prompt(d, user, room_id)


# ---------------------------------------------------------------------------
# admin page: users with spent tokens, players' photos. Password = ADMIN_PASSWORD_HASH in .env
# ---------------------------------------------------------------------------
ADMIN_TTL_MS = 12 * 3600 * 1000


async def current_admin(request: Request) -> None:
    if not settings.admin_password_hash:
        raise not_found("Не найдено")
    token = request.headers.get("x-admin-token", "")
    row = state.db.one("SELECT expires_at FROM admin_sessions WHERE token_hash=?", (hash_token(token),)) if token else None
    if not row or row["expires_at"] < now_ms():
        raise ApiError(401, "admin_auth", "Нужен вход в админку.")


class AdminLoginIn(BaseModel):
    password: str = Field(max_length=200)


@app.post("/v1/admin/login")
async def admin_login(body: AdminLoginIn, request: Request, d: Database = Depends(db)):
    if not settings.admin_password_hash:
        raise not_found("Не найдено")
    rate(f"admin:{client_ip(request)}", 5, 900, "Слишком много попыток. Подожди 15 минут.")
    if not await asyncio.to_thread(verify_password, body.password, settings.admin_password_hash):
        raise ApiError(400, "bad_password", "Неверный пароль.")
    token = new_token()
    ts = now_ms()
    with d.tx():
        d.run("DELETE FROM admin_sessions WHERE expires_at<?", (ts,))
        d.run("INSERT INTO admin_sessions(token_hash, created_at, expires_at) VALUES(?,?,?)", (hash_token(token), ts, ts + ADMIN_TTL_MS))
    return {"token": token, "expires_at": ts + ADMIN_TTL_MS}


@app.post("/v1/admin/logout")
async def admin_logout(request: Request, _: None = Depends(current_admin), d: Database = Depends(db)):
    d.run("DELETE FROM admin_sessions WHERE token_hash=?", (hash_token(request.headers.get("x-admin-token", "")),))
    return {"ok": True}


@app.get("/v1/admin/users")
async def admin_users(_: None = Depends(current_admin), d: Database = Depends(db)):
    return A.users(d)


@app.delete("/v1/admin/users/{public_id}")
async def admin_delete_user(public_id: str, _: None = Depends(current_admin), d: Database = Depends(db)):
    res = A.delete_user(d, public_id)
    if res is None:
        raise not_found("Игрок не найден")
    log.info("admin deleted user %s", res["nick"])
    return {"ok": True, **res}


@app.get("/v1/admin/photos")
async def admin_photos(_: None = Depends(current_admin), d: Database = Depends(db)):
    return A.photos(d)


@app.get("/v1/admin/photos/{iid}")
async def admin_photo(iid: str, _: None = Depends(current_admin), d: Database = Depends(db)):
    if not d.one("SELECT 1 FROM images WHERE id=? AND purpose='chat'", (iid,)):
        raise not_found("Фото не найдено")
    return _image_response(iid)


@app.delete("/v1/admin/photos/{iid}")
async def admin_delete_photo(iid: str, _: None = Depends(current_admin), d: Database = Depends(db)):
    if not R.delete_chat_photo(d, iid, "Фото удалено администратором."):
        raise not_found("Фото не найдено")
    return {"ok": True}
