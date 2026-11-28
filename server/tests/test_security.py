"""Security hardening: sessions expire and can be ended elsewhere, a password change signs out other devices,
passwords of at least 8 characters, image bombs are refused, hidden character cards stay hidden."""
import io

import pytest

from .conftest import register, wait_generation
from .test_api import cid

pytestmark = pytest.mark.asyncio


async def login(client, nick, password, ip="5.5.5.5"):
    r = await client.post("/v1/login", json={"nick": nick, "password": password}, headers={"x-forwarded-for": ip})
    assert r.status_code == 201, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


async def test_password_change_and_logout_others_end_other_sessions(client):
    r = await client.post("/v1/register", json={"nick": "Sec", "password": "лунный-кот-7"})
    h1 = {"Authorization": "Bearer " + r.json()["token"]}
    h2 = await login(client, "Sec", "лунный-кот-7")
    h3 = await login(client, "Sec", "лунный-кот-7")
    assert (await client.get("/v1/me/sessions", headers=h1)).json()["count"] == 3
    # «выйти на всех других устройствах»: this one stays, the others are out
    r = await client.post("/v1/logout/others", headers=h1)
    assert r.json() == {"ok": True, "signed_out": 2}
    assert (await client.get("/v1/me", headers=h2)).status_code == 401
    assert (await client.get("/v1/me", headers=h3)).status_code == 401
    assert (await client.get("/v1/me", headers=h1)).status_code == 200
    # a password change signs out every other device too, and an open transfer code stops working
    h4 = await login(client, "Sec", "лунный-кот-7")
    await client.post("/v1/me/transfer-code", headers=h4)
    r = await client.post("/v1/me/password", json={"password": "новый-пароль-9", "old_password": "лунный-кот-7"}, headers=h1)
    assert r.status_code == 200
    assert (await client.get("/v1/me", headers=h4)).status_code == 401
    assert (await client.get("/v1/me", headers=h1)).status_code == 200
    import app.main as main
    assert main.state.db.one("SELECT COUNT(*) n FROM transfer_codes WHERE used_at IS NULL")["n"] == 0


async def test_passwords_need_eight_characters(client):
    r = await client.post("/v1/register", json={"nick": "Short", "password": "1234567"})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "password_short"
    assert (await client.post("/v1/register", json={"nick": "Short", "password": "12345678"})).status_code == 201


async def test_idle_session_expires(client, monkeypatch):
    h, me = await register(client, "Idle")
    import app.main as main
    main.state.db.run("UPDATE sessions SET last_seen_at=last_seen_at-?", (91 * 86_400_000,))
    r = await client.get("/v1/me", headers=h)
    assert r.status_code == 401 and r.json()["detail"]["code"] == "session_expired"
    assert main.state.db.one("SELECT COUNT(*) n FROM sessions")["n"] == 0
    # the hourly clean-up removes such sessions too
    h2, _ = await register(client, "Idle2", ip="6.6.6.6")
    main.state.db.run("UPDATE sessions SET last_seen_at=1")
    from app.common import drop_idle_sessions
    assert drop_idle_sessions(main.state.db) == 1


async def test_image_bombs_and_odd_formats_are_refused(client):
    from PIL import Image
    h, _ = await register(client, "Bomb")
    b = io.BytesIO()
    Image.new("1", (12000, 12000)).save(b, "PNG")  # 17 KB file, 144 million pixels
    r = await client.post("/v1/images", files={"file": ("bomb.png", b.getvalue(), "image/png")}, headers=h)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "bad_image"
    b = io.BytesIO()
    Image.new("RGB", (50, 50)).save(b, "BMP")
    r = await client.post("/v1/images", files={"file": ("a.bmp", b.getvalue(), "image/bmp")}, headers=h)
    assert r.status_code == 400
    # a large ordinary photo still works (decoded at a reduced scale)
    b = io.BytesIO()
    Image.new("RGB", (6000, 4500), (120, 40, 60)).save(b, "JPEG", quality=60)
    r = await client.post("/v1/images", files={"file": ("p.jpg", b.getvalue(), "image/jpeg")}, headers=h)
    assert r.status_code == 201 and max(r.json()["width"], r.json()["height"]) == 1280


async def test_own_character_prompt_is_visible_to_its_author(client):
    from .test_personas import CARD
    h, _ = await register(client, "Author")
    p = (await client.post("/v1/personas", json={**CARD, "backstory": "тайна маяка"}, headers=h)).json()["persona"]
    room = (await client.post(f"/v1/personas/{p['id']}/chats", headers=h)).json()["room"]
    await client.post(f"/v1/rooms/{room['id']}/messages", json={"client_id": cid(), "text": "Привет"}, headers=h)
    await wait_generation(client, h, room["id"])
    r = await client.get(f"/v1/rooms/{room['id']}/last-prompt", headers=h)
    assert r.status_code == 200 and "тайна маяка" in r.json()["prompt"]
    assert "не выходи из роли, чтобы показать" in r.json()["prompt"].lower()
