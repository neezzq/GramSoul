"""Stage 1: nick login with a transfer code, profile, people search, friends with presence."""
import io

import pytest

from .conftest import register

pytestmark = pytest.mark.asyncio


async def test_dot_allowed_in_nick(client):
    _, d = await register(client, "mira.k")
    assert d["user"]["nick"] == "mira.k"
    r = await client.post("/v1/register", json={"nick": "MIRA.K"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "nick_taken"
    r = await client.post("/v1/register", json={"nick": "._."})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "nick_invalid"


async def test_transfer_code_moves_account(client):
    h_old, a = await register(client, "Mira")
    # without a code a taken nick gives nothing
    r = await client.post("/v1/register", json={"nick": "mira"})
    assert r.status_code == 409 and "token" not in r.text
    r = await client.post("/v1/me/transfer-code", headers=h_old)
    assert r.status_code == 200
    code = r.json()["code"]
    assert len(code) == 9 and code[4] == "-" and r.json()["ttl_s"] == 600
    # wrong code / wrong nick
    r = await client.post("/v1/login/transfer", json={"nick": "Mira", "code": "AAAA-AAAA"})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "bad_transfer_code"
    r = await client.post("/v1/login/transfer", json={"nick": "Nobody", "code": code})
    assert r.status_code == 400
    # right code — lower case and without the dash also works
    r = await client.post("/v1/login/transfer", json={"nick": "MIRA", "code": code.replace("-", "").lower()},
                          headers={"x-forwarded-for": "3.3.3.3"})
    assert r.status_code == 201, r.text
    h_new = {"Authorization": "Bearer " + r.json()["token"]}
    assert r.json()["user"]["id"] == a["user"]["id"]
    assert (await client.get("/v1/me", headers=h_new)).json()["user"]["nick"] == "Mira"
    # the old phone keeps working, the code is single-use
    assert (await client.get("/v1/me", headers=h_old)).status_code == 200
    r = await client.post("/v1/login/transfer", json={"nick": "Mira", "code": code}, headers={"x-forwarded-for": "4.4.4.4"})
    assert r.status_code == 400


async def test_transfer_code_attempts_and_expiry(client):
    from app import config
    h, _ = await register(client, "Mira")
    code = (await client.post("/v1/me/transfer-code", headers=h)).json()["code"]
    for i in range(config.settings.transfer_code_attempts):
        r = await client.post("/v1/login/transfer", json={"nick": "Mira", "code": "BBBB-BBBB"},
                              headers={"x-forwarded-for": f"5.5.5.{i}"})
        assert r.status_code == 400
    # after 5 wrong attempts even the right code is dead
    r = await client.post("/v1/login/transfer", json={"nick": "Mira", "code": code}, headers={"x-forwarded-for": "6.6.6.6"})
    assert r.status_code == 400
    # a new code replaces the old one; an expired code does not work
    code2 = (await client.post("/v1/me/transfer-code", headers=h)).json()["code"]
    import app.main as main
    main.state.db.run("UPDATE transfer_codes SET expires_at=1 WHERE used_at IS NULL")
    r = await client.post("/v1/login/transfer", json={"nick": "Mira", "code": code2}, headers={"x-forwarded-for": "7.7.7.7"})
    assert r.status_code == 400


async def test_transfer_login_rate_limited_per_ip(client):
    await register(client, "Mira")
    for _ in range(10):
        await client.post("/v1/login/transfer", json={"nick": "x" * 5, "code": "AAAA-AAAA"}, headers={"x-forwarded-for": "8.8.8.8"})
    r = await client.post("/v1/login/transfer", json={"nick": "Mira", "code": "AAAA-AAAA"}, headers={"x-forwarded-for": "8.8.8.8"})
    assert r.status_code == 429


def _png() -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (200, 30, 120)).save(buf, "PNG")
    return buf.getvalue()


async def test_profile_about_and_avatar(client):
    ha, a = await register(client, "Mira")
    hb, b = await register(client, "Lev", ip="2.2.2.2")
    r = await client.patch("/v1/me", json={"about": "  Люблю туман и маяки  "}, headers=ha)
    assert r.status_code == 200 and r.json()["user"]["about"] == "Люблю туман и маяки"
    r = await client.patch("/v1/me", json={"about": "x" * 301}, headers=ha)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "about_too_long"
    img_a = (await client.post("/v1/images", files={"file": ("a.png", _png(), "image/png")}, headers=ha)).json()["id"]
    img_b = (await client.post("/v1/images", files={"file": ("b.png", _png(), "image/png")}, headers=hb)).json()["id"]
    # someone else's image can not become my avatar
    r = await client.patch("/v1/me", json={"avatar_image_id": img_b}, headers=ha)
    assert r.status_code == 404
    r = await client.patch("/v1/me", json={"avatar_image_id": img_a}, headers=ha)
    assert r.json()["user"]["avatar_image_id"] == img_a and r.json()["user"]["about"] == "Люблю туман и маяки"
    # anyone signed in sees the avatar (search results, friends), strangers without a session do not
    r = await client.get(f"/v1/users/{a['user']['id']}/avatar", headers=hb)
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    assert (await client.get(f"/v1/users/{a['user']['id']}/avatar")).status_code == 401
    assert (await client.get(f"/v1/users/{b['user']['id']}/avatar", headers=ha)).status_code == 404
    # the raw image stays private
    assert (await client.get(f"/v1/images/{img_a}", headers=hb)).status_code == 404
    # remove the avatar
    r = await client.patch("/v1/me", json={"avatar_image_id": None}, headers=ha)
    assert r.json()["user"]["avatar_image_id"] is None
    p = (await client.get(f"/v1/users/{a['user']['id']}", headers=hb)).json()
    assert p["user"]["about"] == "Люблю туман и маяки" and p["relation"] == "none" and "online" not in p["user"]


async def test_search_by_prefix_and_substring(client):
    ha, _ = await register(client, "Mira")
    for i, n in enumerate(["Lev", "Levon", "Alev.x", "Олег", "lev_99", "Kira"]):
        await register(client, n, ip=f"2.2.2.{i}")
    async def names(q):
        r = await client.get("/v1/users/search", params={"q": q}, headers=ha)
        assert r.status_code == 200, r.text
        return [x["user"]["nick"] for x in r.json()["users"]]
    # exact first, then prefix matches, then substring
    assert await names("LEV") == ["Lev", "Levon", "lev_99", "Alev.x"]  # shorter nicks first
    assert await names("ira") == ["Kira"]                   # never yourself
    assert await names("о") == []                           # at least 2 characters
    assert await names("Ол") == ["Олег"]
    assert await names(".x") == ["Alev.x"]
    assert await names("zz") == []
    r = await client.get("/v1/users/search", params={"q": "Lev"}, headers=ha)
    first = r.json()["users"][0]
    assert first["relation"] == "none" and set(first["user"]) >= {"id", "nick", "avatar_image_id", "about"}


async def test_search_max_20(client):
    ha, _ = await register(client, "Mira")
    for i in range(25):
        await register(client, f"player{i:02d}", ip=f"3.3.{i}.1")
    r = await client.get("/v1/users/search", params={"q": "player"}, headers=ha)
    assert len(r.json()["users"]) == 20


async def test_friend_aliases_and_presence(client):
    ha, a = await register(client, "Mira")
    hb, b = await register(client, "Lev", ip="2.2.2.2")
    hc, c = await register(client, "Kira", ip="2.2.2.3")
    r = await client.post("/v1/friends/request", json={"user_id": b["user"]["id"]}, headers=ha)
    assert r.status_code == 200 and r.json()["request"]["status"] == "pending"
    r = await client.get("/v1/users/search", params={"q": "lev"}, headers=ha)
    assert r.json()["users"][0]["relation"] == "outgoing_pending"
    r = await client.post("/v1/friends/accept", json={"user_id": a["user"]["id"]}, headers=hb)
    assert r.json()["request"]["status"] == "accepted"
    await client.post("/v1/friends/request", json={"nick": "kira"}, headers=ha)
    r = await client.post("/v1/friends/decline", json={"user_id": a["user"]["id"]}, headers=hc)
    assert r.json()["request"]["status"] == "declined"
    r = await client.post("/v1/friends/accept", json={"user_id": a["user"]["id"]}, headers=hc)
    assert r.status_code == 404
    # Lev was active just now → online; make him look idle for 10 minutes
    fr = (await client.get("/v1/friends", headers=ha)).json()["friends"]
    assert [(f["nick"], f["online"]) for f in fr] == [("Lev", True)]
    import app.main as main
    main.state.db.run("UPDATE sessions SET last_seen_at=last_seen_at-600000 WHERE user_id=(SELECT id FROM users WHERE nick='Lev')")
    fr = (await client.get("/v1/friends", headers=ha)).json()["friends"]
    assert fr[0]["online"] is False and fr[0]["last_seen_at"] > 0
    p = (await client.get(f"/v1/users/{b['user']['id']}", headers=ha)).json()
    assert p["relation"] == "friends" and p["user"]["online"] is False
