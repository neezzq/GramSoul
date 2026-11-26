"""Per-chat picture settings (style + fixed scene description), the «Эстетика» style, nick change,
removing the sample content, deleting an account from the admin page."""
import uuid

import pytest

from .conftest import register, wait_generation
from .test_api import cid, shared_room, wait_photo

pytestmark = pytest.mark.asyncio


def job_prompt(main, rid_public):
    room = main.state.db.one("SELECT id FROM rooms WHERE public_id=?", (rid_public,))
    return main.state.db.one("SELECT prompt FROM image_jobs WHERE room_id=? ORDER BY id DESC LIMIT 1", (room["id"],))["prompt"]


async def test_chat_picture_settings_style_and_notes(client):
    import app.main as main
    ha, hb, a, b, room = await shared_room(client)
    rid = room["id"]
    d = (await client.get(f"/v1/rooms/{rid}", headers=ha)).json()["room"]
    assert d["image_style"] == "aesthetic" and d["image_notes"] == ""  # new chats draw in «Эстетика»
    # only the owner changes them; unknown styles are refused
    r = await client.patch(f"/v1/rooms/{rid}/settings", json={"image_notes": "снег"}, headers=hb)
    assert r.status_code == 403
    r = await client.patch(f"/v1/rooms/{rid}/settings", json={"image_style": "pixel"}, headers=ha)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "bad_style"
    notes = "Зимний посёлок у моря, вечер, тёплые окна; Ива в чёрной куртке, Ян с длинными тёмными волосами"
    r = await client.patch(f"/v1/rooms/{rid}/settings", json={"image_style": "anime", "image_notes": "  " + notes}, headers=ha)
    assert r.status_code == 200 and r.json()["image_style"] == "anime" and r.json()["image_notes"] == notes
    d = (await client.get(f"/v1/rooms/{rid}", headers=hb)).json()["room"]
    assert d["image_style"] == "anime" and d["image_notes"] == notes  # the friend sees them too
    # auto picture: the chat's description and style are in the prompt
    await client.post(f"/v1/rooms/{rid}/photo", json={"client_id": cid()}, headers=ha)
    s = await wait_photo(client, ha, rid)
    assert s["image_job"]["status"] == "done"
    p1 = job_prompt(main, rid)
    assert notes in p1 and "anime" in p1 and "Постоянное описание" in p1
    assert "предыдущий кадр" not in p1  # nothing drawn before
    # the next auto picture also gets the previous one, so the place and people stay the same
    await client.post(f"/v1/rooms/{rid}/photo", json={"client_id": cid()}, headers=ha)
    await wait_photo(client, ha, rid)
    import asyncio
    for _ in range(100):
        if (await client.get(f"/v1/rooms/{rid}/sync", params={"since": 0}, headers=ha)).json()["image_job"]["status"] == "done":
            break
        await asyncio.sleep(0.05)
    p2 = job_prompt(main, rid)
    assert "предыдущий кадр" in p2 and notes in p2
    # by own description: the request comes first, the fixed description still applies
    await client.post(f"/v1/rooms/{rid}/photo", json={"client_id": cid(), "prompt": "они пьют чай на кухне"}, headers=ha)
    for _ in range(100):
        j = (await client.get(f"/v1/rooms/{rid}/sync", params={"since": 0}, headers=ha)).json()["image_job"]
        if j["prompt"] == "они пьют чай на кухне" and j["status"] == "done":
            break
        await asyncio.sleep(0.05)
    p3 = job_prompt(main, rid)
    assert p3.startswith("Нарисуй одну иллюстрацию: они пьют чай на кухне") and notes in p3
    # default style for a chat that never chose one is the aesthetic photo look
    room2 = (await client.post(f"/v1/stories/{room['story']['id']}/rooms", headers=ha)).json()["room"]
    await client.post(f"/v1/rooms/{room2['id']}/photo", json={"client_id": cid()}, headers=ha)
    await wait_photo(client, ha, room2["id"])
    assert "aesthetic moody photo" in job_prompt(main, room2["id"])


async def test_nick_change(client):
    ha, hb, a, b, room = await shared_room(client)
    rid = room["id"]
    await client.post(f"/v1/rooms/{rid}/messages", json={"client_id": cid(), "text": "Привет"}, headers=hb)
    await wait_generation(client, ha, rid)
    old = b["user"]["nick"]
    # taken (any case / look-alike letters) and invalid nicks are refused
    r = await client.patch("/v1/me", json={"nick": a["user"]["nick"].upper()}, headers=hb)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "nick_taken"
    r = await client.patch("/v1/me", json={"nick": "a b"}, headers=hb)
    assert r.status_code == 400
    r = await client.patch("/v1/me", json={"nick": "Лев_Новый"}, headers=hb)
    assert r.status_code == 200 and r.json()["user"]["nick"] == "Лев_Новый"
    # friends and the scene see the new nick; the old one is free again
    seats = (await client.get(f"/v1/rooms/{rid}", headers=ha)).json()["room"]["seats"]
    assert any(s["user"] and s["user"]["nick"] == "Лев_Новый" for s in seats)
    fr = (await client.get("/v1/friends", headers=ha)).json()
    assert "Лев_Новый" in str(fr) and old not in str(fr)
    hc, c = await register(client, old, ip="5.5.5.5")
    assert c["user"]["nick"] == old
    # case-only change of one's own nick is fine
    r = await client.patch("/v1/me", json={"nick": "лев_новый"}, headers=hb)
    assert r.status_code == 200 and r.json()["user"]["nick"] == "лев_новый"
    # limited per day
    for i in range(3):
        await client.patch("/v1/me", json={"nick": f"lev_{i}x"}, headers=hb)
    r = await client.patch("/v1/me", json={"nick": "lev_last"}, headers=hb)
    assert r.status_code == 429


async def test_nick_change_renames_personal_chat_lines(client):
    h, me = await register(client, "Мира")
    p = (await client.get("/v1/personas", headers=h)).json()["personas"][0]
    room = (await client.post(f"/v1/personas/{p['id']}/chats", headers=h)).json()["room"]
    await client.post(f"/v1/rooms/{room['id']}/messages", json={"client_id": cid(), "text": "Привет"}, headers=h)
    await wait_generation(client, h, room["id"])
    s0 = (await client.get(f"/v1/rooms/{room['id']}/sync", params={"since": 0}, headers=h)).json()
    assert any(m["kind"] == "player" and m["speaker_name"] == "Мира" for m in s0["messages"])
    await client.patch("/v1/me", json={"nick": "Мира_2"}, headers=h)
    # the change reaches clients through sync (newer rev)
    s1 = (await client.get(f"/v1/rooms/{room['id']}/sync", params={"since": s0["rev"]}, headers=h)).json()
    assert any(m["kind"] == "player" and m["speaker_name"] == "Мира_2" for m in s1["messages"])


async def test_sample_content_off_and_purged(client, monkeypatch):
    import app.main as main
    import app.personas as PS
    db = main.state.db
    h, me = await register(client, "Мира")  # DEMO_CONTENT=on in tests: sample story + 6 characters
    demo_persona = next(p for p in (await client.get("/v1/personas", headers=h)).json()["personas"] if p["is_demo"])
    chat = (await client.post(f"/v1/personas/{demo_persona['id']}/chats", headers=h)).json()["room"]
    story = next(s for s in (await client.get("/v1/stories", headers=h)).json()["stories"] if s["is_demo"])
    scene = (await client.post(f"/v1/stories/{story['id']}/rooms", headers=h)).json()["room"]
    own = (await client.post("/v1/stories/quick", json={"name": "Своя", "start_line": "Привет"}, headers=h)).json()["story"]
    # production: no sample content
    monkeypatch.setattr(PS.settings, "demo_content", False)
    monkeypatch.setattr(main.settings, "demo_content", False)
    res = PS.purge_demo(db)
    assert res["personas"] == 6 and res["stories"] >= 1 and res["rooms"] >= 2
    personas = (await client.get("/v1/personas", headers=h)).json()["personas"]
    assert not any(p["is_demo"] for p in personas)
    stories = (await client.get("/v1/stories", headers=h)).json()["stories"]
    assert [s["id"] for s in stories] == [own["id"]]  # the player's own story stays
    for rid in (chat["id"], scene["id"]):
        assert (await client.get(f"/v1/rooms/{rid}", headers=h)).status_code == 404
    # new accounts get nothing made up
    r = await client.post("/v1/register", json={"nick": "Новичок", "password": "secret-12"}, headers={"x-forwarded-for": "7.7.7.7"})
    assert r.status_code == 201 and r.json()["demo_story_id"] is None
    h2 = {"Authorization": "Bearer " + r.json()["token"]}
    assert (await client.get("/v1/stories", headers=h2)).json()["stories"] == []
    assert (await client.post("/v1/stories/demo", headers=h2)).status_code == 404
    PS.seed_demo(db)  # startup with DEMO_CONTENT off does not bring them back
    assert not db.one("SELECT 1 FROM personas WHERE is_demo=1")


async def test_admin_deletes_an_account(client, monkeypatch):
    import app.main as main
    from app.common import hash_password
    from .test_admin import upload
    monkeypatch.setattr(main.settings, "admin_password_hash", hash_password("очень-секретно"))
    tok = (await client.post("/v1/admin/login", json={"password": "очень-секретно"})).json()["token"]
    hd = {"X-Admin-Token": tok}
    ha, hb, a, b, room = await shared_room(client)
    rid = room["id"]
    # B (guest) posts a photo in A's scene, then B's account is deleted
    m = (await upload(client, hb, rid, "фото гостя")).json()["message"]
    assert (await client.delete(f"/v1/admin/users/{b['user']['id']}")).status_code == 401
    r = await client.delete(f"/v1/admin/users/{b['user']['id']}", headers=hd)
    assert r.status_code == 200 and r.json()["nick"] == b["user"]["nick"]
    assert (await client.get("/v1/me", headers=hb)).status_code == 401
    users = (await client.get("/v1/admin/users", headers=hd)).json()["users"]
    assert b["user"]["nick"] not in [u["nick"] for u in users]
    # A's scene stays; the guest's seat is free and the photo became a note
    d = (await client.get(f"/v1/rooms/{rid}", headers=ha)).json()["room"]
    assert d["seats"][1]["user"] is None
    msgs = (await client.get(f"/v1/rooms/{rid}/sync", params={"since": 0}, headers=ha)).json()["messages"]
    line = next(x for x in msgs if x["id"] == m["id"])
    assert line["image_id"] is None and line["kind"] == "system"
    assert (await client.delete(f"/v1/admin/users/{b['user']['id']}", headers=hd)).status_code == 404
