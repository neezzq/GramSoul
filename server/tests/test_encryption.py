"""Encryption at rest: with DATA_KEY the database (SQLCipher), the pictures and the voice-over audio are stored
encrypted; data of a server that ran without the key is encrypted in place on the first start with it."""
import asyncio
import base64
import io
import os
import tempfile
import uuid

import pytest

from .conftest import make_client

pytestmark = pytest.mark.asyncio

KEY = base64.urlsafe_b64encode(bytes(range(32))).decode().rstrip("=")


def png():
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (80, 60), (200, 30, 120)).save(b, "PNG")
    return b.getvalue()


def head(path, n=16):
    with open(path, "rb") as f:
        return f.read(n)


async def until(cond, timeout=5.0):
    end = asyncio.get_running_loop().time() + timeout
    while not cond():
        assert asyncio.get_running_loop().time() < end, "timed out"
        await asyncio.sleep(0.02)


async def test_unencrypted_data_is_encrypted_on_the_first_start_with_a_key(monkeypatch):
    data = tempfile.mkdtemp()
    monkeypatch.delenv("DATA_KEY", raising=False)
    # 1. a server without the key: everything readable on disk
    async with make_client(data) as c:
        r = await c.post("/v1/register", json={"nick": "Lisa", "password": "лунный-кот-7"})
        h = {"Authorization": "Bearer " + r.json()["token"]}
        img = (await c.post("/v1/images", files={"file": ("a.png", png(), "image/png")}, headers=h)).json()["id"]
        before = (await c.get(f"/v1/images/{img}", headers=h)).content
        await c.patch("/v1/me", json={"about": "секретная заметка о себе"}, headers=h)
    db_file, img_file = os.path.join(data, "fonar.sqlite3"), os.path.join(data, "images", img + ".jpg")
    assert head(db_file) == b"SQLite format 3\x00" and head(img_file, 2) == b"\xff\xd8"
    # 2. the same server with DATA_KEY: the database and the pictures become encrypted, nothing is lost
    monkeypatch.setenv("DATA_KEY", KEY)
    async with make_client(data) as c:
        assert head(db_file) != b"SQLite format 3\x00"
        await until(lambda: head(img_file, 4) == b"GSE1")
        assert (await c.get("/v1/me", headers=h)).json()["user"]["about"] == "секретная заметка о себе"  # the session survived
        assert (await c.get(f"/v1/images/{img}", headers=h)).content == before
        r = await c.post("/v1/login", json={"nick": "Lisa", "password": "лунный-кот-7"})
        assert r.status_code == 201
        # new pictures and voice-over audio are written encrypted
        img2 = (await c.post("/v1/images", files={"file": ("b.png", png(), "image/png")}, headers=h)).json()["id"]
        assert head(os.path.join(data, "images", img2 + ".jpg"), 4) == b"GSE1"
        assert (await c.post("/v1/voice/preview", json={"voice": "nova", "text": "Привет"}, headers=h)).status_code == 200
        voice_dir = os.path.join(data, "voice")
        assert all(head(os.path.join(voice_dir, f), 4) == b"GSE1" for f in os.listdir(voice_dir))
        # a consistent encrypted backup (what deploy/backup.sh stores)
        import app.main as main
        bak = os.path.join(data, "backup.sqlite3")
        main.state.db.backup_to(bak)
        assert head(bak) != b"SQLite format 3\x00" and oct(os.stat(bak).st_mode & 0o777) == "0o600"
    with open(db_file, "rb") as f:
        assert "секретная заметка".encode() not in f.read()
    # the backup opens with the key, and has the data
    from app.crypto import db_key_hex
    from app.db import Database
    b = Database(bak, db_key_hex())
    assert b.one("SELECT about FROM users WHERE nick='Lisa'")["about"] == "секретная заметка о себе"
    b.close()


async def test_a_wrong_or_missing_key_does_not_open_the_data(monkeypatch):
    data = tempfile.mkdtemp()
    monkeypatch.setenv("DATA_KEY", KEY)
    async with make_client(data) as c:
        r = await c.post("/v1/register", json={"nick": "Kim", "password": "лунный-кот-7"})
        h = {"Authorization": "Bearer " + r.json()["token"]}
        img = (await c.post("/v1/images", files={"file": ("a.png", png(), "image/png")}, headers=h)).json()["id"]
    other = base64.urlsafe_b64encode(bytes(range(1, 33))).decode()
    monkeypatch.setenv("DATA_KEY", other)
    with pytest.raises(RuntimeError, match="does not open"):
        async with make_client(data):
            pass
    monkeypatch.delenv("DATA_KEY")
    with pytest.raises(RuntimeError, match="encrypted"):
        async with make_client(data):
            pass
    # a sealed picture can not be read without the key or under another name
    from app import config, crypto
    monkeypatch.setenv("DATA_KEY", KEY)
    config.reload_settings()
    blob = open(os.path.join(data, "images", img + ".jpg"), "rb").read()
    assert crypto.unseal(blob, img)[:2] == b"\xff\xd8"
    from cryptography.exceptions import InvalidTag
    with pytest.raises(InvalidTag):
        crypto.unseal(blob, "another-picture-id")
    monkeypatch.setenv("DATA_KEY", "not-a-key")
    config.reload_settings()
    with pytest.raises(crypto.DataKeyError):
        crypto.db_key_hex()
    monkeypatch.delenv("DATA_KEY")
    config.reload_settings()


async def test_without_a_key_nothing_changes(monkeypatch):
    monkeypatch.delenv("DATA_KEY", raising=False)
    data = tempfile.mkdtemp()
    async with make_client(data) as c:
        r = await c.post("/v1/register", json={"nick": "Plain" + uuid.uuid4().hex[:4]})
        assert r.status_code == 201
    assert head(os.path.join(data, "fonar.sqlite3")) == b"SQLite format 3\x00"
