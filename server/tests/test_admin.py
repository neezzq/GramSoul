"""Players' photos in the chat (kept a week) and the password-protected admin API."""
import io
import uuid

import pytest

from .conftest import register, wait_generation
from .test_api import shared_room

pytestmark = pytest.mark.asyncio


def png(color=(200, 30, 120)):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (120, 90), color).save(buf, "PNG")
    return buf.getvalue()


async def upload(client, h, rid, caption=""):
    return await client.post(f"/v1/rooms/{rid}/upload", files={"file": ("a.png", png(), "image/png")},
                             data={"caption": caption, "client_id": uuid.uuid4().hex}, headers=h)


async def test_own_photo_in_chat_visible_to_members_and_expires(client):
    ha, hb, a, b, room = await shared_room(client)
    hc, _ = await register(client, "Чужой", ip="9.9.9.9")
    rid = room["id"]
    r = await upload(client, ha, rid, "мой кот")
    assert r.status_code == 201, r.text
    m = r.json()["message"]
    assert m["kind"] == "player" and m["image_id"] and m["text"] == "мой кот"
    # the friend sees it, a stranger can not
    assert (await client.get(f"/v1/rooms/{rid}/images/{m['image_id']}", headers=hb)).status_code == 200
    assert (await client.get(f"/v1/rooms/{rid}/images/{m['image_id']}", headers=hc)).status_code == 404
    assert (await upload(client, hc, rid)).status_code == 404
    # a photo does not start an AI reply and is not part of the prompt
    import app.main as main
    img = main.state.db.one("SELECT * FROM images WHERE id=?", (m["image_id"],))
    assert img["purpose"] == "chat" and img["expires_at"] - img["created_at"] == 7 * 86_400_000
    # a week later it is gone; its line says so
    main.state.db.run("UPDATE images SET expires_at=1 WHERE id=?", (m["image_id"],))
    from app.rooms import expire_chat_photos
    assert expire_chat_photos(main.state.db) == 1
    msgs = (await client.get(f"/v1/rooms/{rid}/sync", params={"since": 0}, headers=hb)).json()["messages"]
    line = next(x for x in msgs if x["id"] == m["id"])
    assert line["image_id"] is None and line["kind"] == "system" and "7 дней" in line["text"]
    assert (await client.get(f"/v1/rooms/{rid}/images/{m['image_id']}", headers=ha)).status_code == 404


async def test_admin_api(client, monkeypatch):
    import app.main as main
    from app.common import hash_password
    # no password configured: the admin API does not exist
    assert (await client.post("/v1/admin/login", json={"password": "x"})).status_code == 404
    monkeypatch.setattr(main.settings, "admin_password_hash", hash_password("очень-секретно"))
    assert (await client.get("/v1/admin/users")).status_code == 401
    assert (await client.post("/v1/admin/login", json={"password": "не тот"})).status_code == 400
    r = await client.post("/v1/admin/login", json={"password": "очень-секретно"})
    assert r.status_code == 200
    ah = {"X-Admin-Token": r.json()["token"]}
    # a user session is not an admin session
    ha, hb, a, b, room = await shared_room(client)
    assert (await client.get("/v1/admin/users", headers=ha)).status_code == 401
    # spend some tokens: a chat reply, an avatar, a scene photo, an own photo
    rid = room["id"]
    await client.post(f"/v1/rooms/{rid}/messages", json={"client_id": uuid.uuid4().hex, "text": "Привет"}, headers=ha)
    await wait_generation(client, ha, rid)
    await client.post("/v1/avatars/generate", json={"name": "Ива", "description": "рыжая, в плаще", "style": "anime"}, headers=ha)
    up = (await upload(client, hb, rid, "закат")).json()["message"]
    users = (await client.get("/v1/admin/users", headers=ah)).json()
    mira = next(u for u in users["users"] if u["nick"] == "Mira")
    lev = next(u for u in users["users"] if u["nick"] == "Лев_2")
    assert mira["text_tokens"] > 0 and mira["avatar_tokens"] > 0 and mira["avatars"] == 1 and mira["cost"] > 0
    assert lev["photos"] == 1 and lev["avatar_tokens"] == 0
    assert users["total"]["users"] >= 2 and users["total"]["text"] >= mira["text_tokens"]
    # players' photos: list, view, delete earlier than a week
    ph = (await client.get("/v1/admin/photos", headers=ah)).json()
    item = next(p for p in ph["photos"] if p["id"] == up["image_id"])
    assert item["nick"] == "Лев_2" and item["room"] and ph["ttl_days"] == 7
    r = await client.get(f"/v1/admin/photos/{up['image_id']}", headers=ah)
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    assert (await client.delete(f"/v1/admin/photos/{up['image_id']}", headers=ah)).json()["ok"] is True
    msgs = (await client.get(f"/v1/rooms/{rid}/sync", params={"since": 0}, headers=ha)).json()["messages"]
    assert next(x for x in msgs if x["id"] == up["id"])["text"] == "Фото удалено администратором."
    assert (await client.get("/v1/admin/photos", headers=ah)).json()["photos"] == []
    # logout ends the admin session
    await client.post("/v1/admin/logout", headers=ah)
    assert (await client.get("/v1/admin/users", headers=ah)).status_code == 401


async def test_admin_login_rate_limited(client, monkeypatch):
    import app.main as main
    from app.common import hash_password
    monkeypatch.setattr(main.settings, "admin_password_hash", hash_password("очень-секретно"))
    for _ in range(5):
        await client.post("/v1/admin/login", json={"password": "подбор"}, headers={"x-forwarded-for": "6.6.6.6"})
    r = await client.post("/v1/admin/login", json={"password": "очень-секретно"}, headers={"x-forwarded-for": "6.6.6.6"})
    assert r.status_code == 429
