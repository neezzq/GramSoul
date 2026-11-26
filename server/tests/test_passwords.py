"""Nick + password: registration, login, setting a first password for older accounts, changing it."""
import pytest

from .conftest import register

pytestmark = pytest.mark.asyncio


async def reg_pw(client, nick, pw, ip="1.1.1.1"):
    r = await client.post("/v1/register", json={"nick": nick, "password": pw}, headers={"x-forwarded-for": ip})
    return r


async def test_register_with_password_and_login_elsewhere(client):
    r = await reg_pw(client, "Mira", "лунный-кот-7")
    assert r.status_code == 201 and r.json()["user"]["has_password"] is True
    # another device: nick (any case) + password
    r = await client.post("/v1/login", json={"nick": "MIRA", "password": "лунный-кот-7"}, headers={"x-forwarded-for": "2.2.2.2"})
    assert r.status_code == 201
    h = {"Authorization": "Bearer " + r.json()["token"]}
    me = (await client.get("/v1/me", headers=h)).json()["user"]
    assert me["nick"] == "Mira" and me["has_password"] is True
    # wrong password / unknown nick: the same answer
    r1 = await client.post("/v1/login", json={"nick": "Mira", "password": "не-тот"}, headers={"x-forwarded-for": "3.3.3.3"})
    r2 = await client.post("/v1/login", json={"nick": "Nobody", "password": "лунный-кот-7"}, headers={"x-forwarded-for": "3.3.3.3"})
    assert r1.status_code == r2.status_code == 400 and r1.json() == r2.json()
    assert "token" not in r1.text


async def test_password_rules(client):
    r = await reg_pw(client, "Mira", "12345")
    assert r.status_code == 400 and r.json()["detail"]["code"] == "password_short"
    r = await reg_pw(client, "Mira", "      ")
    assert r.status_code == 400
    # the nick was not taken by the failed attempts
    assert (await reg_pw(client, "Mira", "хорошийпароль")).status_code == 201


async def test_old_account_sets_a_password_then_can_log_in(client):
    h, d = await register(client, "Lev")  # an older app: no password
    assert d["user"]["has_password"] is False
    assert (await client.get("/v1/me", headers=h)).json()["user"]["has_password"] is False
    # no password yet → login by nick is impossible
    r = await client.post("/v1/login", json={"nick": "Lev", "password": "anything1"})
    assert r.status_code == 400
    r = await client.post("/v1/me/password", json={"password": "новыйпароль"}, headers=h)
    assert r.status_code == 200 and r.json()["user"]["has_password"] is True
    r = await client.post("/v1/login", json={"nick": "lev", "password": "новыйпароль"}, headers={"x-forwarded-for": "4.4.4.4"})
    assert r.status_code == 201
    # changing needs the old one
    r = await client.post("/v1/me/password", json={"password": "другойпароль"}, headers=h)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "bad_old_password"
    r = await client.post("/v1/me/password", json={"password": "другойпароль", "old_password": "новыйпароль"}, headers=h)
    assert r.status_code == 200
    r = await client.post("/v1/login", json={"nick": "Lev", "password": "новыйпароль"}, headers={"x-forwarded-for": "5.5.5.5"})
    assert r.status_code == 400


async def test_login_is_rate_limited(client):
    await reg_pw(client, "Mira", "правильный")
    for _ in range(10):
        await client.post("/v1/login", json={"nick": "Mira", "password": "x" * 8}, headers={"x-forwarded-for": "7.7.7.7"})
    r = await client.post("/v1/login", json={"nick": "Mira", "password": "правильный"}, headers={"x-forwarded-for": "7.7.7.7"})
    assert r.status_code == 429
    # the stored hash is not the password
    import app.main as main
    stored = main.state.db.one("SELECT password_hash FROM users WHERE nick='Mira'")["password_hash"]
    assert stored.startswith("scrypt:") and "правильный" not in stored
