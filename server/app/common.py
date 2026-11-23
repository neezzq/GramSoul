"""Shared helpers: ids, errors, auth, change notification hub."""
from __future__ import annotations

import asyncio
import hashlib
import secrets
import time
from dataclasses import dataclass, field

from fastapi import HTTPException, Request

from .db import Database, now_ms


def new_id(n: int = 9) -> str:
    return secrets.token_urlsafe(n)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class ApiError(HTTPException):
    def __init__(self, status: int, code: str, message: str, retry_after: float | None = None):
        headers = {"Retry-After": str(int(retry_after))} if retry_after else None
        super().__init__(status_code=status, detail={"code": code, "message": message}, headers=headers)


def not_found(what: str = "Не найдено") -> ApiError:
    return ApiError(404, "not_found", what)


def client_ip(request: Request) -> str:
    # Caddy is the only thing that can reach the API container and it sets X-Forwarded-For.
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@dataclass
class User:
    id: int
    public_id: str
    nick: str


def auth_user(db: Database, request: Request) -> User:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise ApiError(401, "no_session", "Нужна сессия. Открой приложение заново.")
    token = header[7:].strip()
    if not token or len(token) > 200:
        raise ApiError(401, "invalid_session", "Сессия недействительна.")
    row = db.one(
        "SELECT u.id, u.public_id, u.nick, s.last_seen_at FROM sessions s JOIN users u ON u.id = s.user_id "
        "WHERE s.token_hash = ?",
        (hash_token(token),),
    )
    if not row:
        raise ApiError(401, "invalid_session", "Сессия недействительна.")
    ts = now_ms()
    if ts - row["last_seen_at"] > 60_000:
        db.run("UPDATE sessions SET last_seen_at=? WHERE token_hash=?", (ts, hash_token(token)))
    return User(row["id"], row["public_id"], row["nick"])


# ---------------------------------------------------------------------------
# Change hub: long-poll waiters per room / per user inbox
# ---------------------------------------------------------------------------
@dataclass
class _Channel:
    version: int = 0
    waiters: list[asyncio.Future] = field(default_factory=list)


class Hub:
    def __init__(self) -> None:
        self._ch: dict[str, _Channel] = {}
        self.partial: dict[int, dict] = {}  # room_id -> {"generation": public_id, "text": str, "v": int}
        self._last_partial_notify: dict[int, float] = {}

    def _get(self, key: str) -> _Channel:
        ch = self._ch.get(key)
        if ch is None:
            ch = self._ch[key] = _Channel()
        return ch

    def notify(self, key: str) -> None:
        ch = self._get(key)
        ch.version += 1
        waiters, ch.waiters = ch.waiters, []
        for f in waiters:
            if not f.done():
                f.set_result(True)

    def version(self, key: str) -> int:
        return self._get(key).version

    async def wait(self, key: str, timeout: float) -> bool:
        ch = self._get(key)
        fut = asyncio.get_running_loop().create_future()
        ch.waiters.append(fut)
        try:
            await asyncio.wait_for(fut, timeout)
            return True
        except asyncio.TimeoutError:
            return False
        finally:
            if fut in ch.waiters:
                ch.waiters.remove(fut)

    # partial text of a running generation
    def partial_start(self, room_id: int, gen_public_id: str) -> None:
        self.partial[room_id] = {"generation": gen_public_id, "text": "", "v": 0}
        self.notify(f"room:{room_id}")

    def partial_add(self, room_id: int, piece: str) -> None:
        p = self.partial.get(room_id)
        if not p:
            return
        p["text"] += piece
        p["v"] += 1
        now = time.monotonic()
        if now - self._last_partial_notify.get(room_id, 0) > 0.4:
            self._last_partial_notify[room_id] = now
            self.notify(f"room:{room_id}")

    def partial_clear(self, room_id: int) -> None:
        self.partial.pop(room_id, None)


hub = Hub()
