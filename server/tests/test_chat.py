"""Stage 3: personal chat with a character — greeting first, streamed replies, regenerate,
edit, three reply suggestions, scene photo, summary memory."""
import asyncio
import uuid

import pytest

from .conftest import register, wait_generation

pytestmark = pytest.mark.asyncio


def cid():
    return uuid.uuid4().hex


async def demo_persona(client, h, name="Ян Корсак"):
    ps = (await client.get("/v1/personas", headers=h)).json()["personas"]
    return next(p for p in ps if p["name"] == name)


async def start(client, h, persona_id):
    r = await client.post(f"/v1/personas/{persona_id}/chats", headers=h)
    assert r.status_code == 201, r.text
    return r.json()["room"]


async def visible(client, h, rid):
    msgs = (await client.get(f"/v1/rooms/{rid}/sync", params={"since": 0}, headers=h)).json()["messages"]
    return [m for m in msgs if not m["hidden"]]


async def test_chat_starts_with_greeting_and_replies_as_character(client):
    h, me = await register(client, "Mira")
    p = await demo_persona(client, h)
    room = await start(client, h, p["id"])
    assert room["kind"] == "chat" and room["title"] == "Ян Корсак" and room["my_role"] == "owner"
    chars = room["story"]["characters"]
    assert [c["id"] for c in chars] == [p["id"]] and "personality" not in chars[0] and "backstory" not in chars[0]
    msgs = await visible(client, h, room["id"])
    assert len(msgs) == 1 and msgs[0]["kind"] == "character" and msgs[0]["character_id"] == p["id"]
    assert msgs[0]["text"] == p["first_message"]
    # the player talks, the character answers (one message, in its own name)
    await client.post(f"/v1/rooms/{room['id']}/messages", json={"client_id": cid(), "text": "*сажусь у стойки* Как обычно."}, headers=h)
    s = await wait_generation(client, h, room["id"])
    assert s["generation"]["status"] == "done"
    msgs = await visible(client, h, room["id"])
    assert [m["kind"] for m in msgs] == ["character", "player", "character"]
    assert msgs[1]["speaker_name"] == "Mira" and msgs[2]["speaker_name"] == "Ян Корсак" and msgs[2]["character_id"] == p["id"]
    # what the model saw: the character's hidden card, the style rules, the greeting as its own line
    lp = (await client.get(f"/v1/rooms/{room['id']}/last-prompt", headers=h)).json()
    assert "Ты — Ян Корсак" in lp["prompt"] and "Предыстория:" in lp["prompt"] and "в *звёздочках*" in lp["prompt"]
    assert "<assistant>\n" + p["first_message"][:30] in lp["prompt"] and "Mira" in lp["prompt"]
    # the room shows up in the list with the character's name
    rooms = (await client.get("/v1/rooms", headers=h)).json()["rooms"]
    assert rooms[0]["kind"] == "chat" and rooms[0]["story_title"] == "Ян Корсак"
    # and on the character page
    chats = (await client.get(f"/v1/personas/{p['id']}", headers=h)).json()["persona"]["chats"]
    assert [c["id"] for c in chats] == [room["id"]]


async def test_chat_regenerate_continue_and_edit(client):
    h, _ = await register(client, "Mira")
    hb, _ = await register(client, "Lev", ip="2.2.2.2")
    room = await start(client, h, (await demo_persona(client, h))["id"])
    rid = room["id"]
    await client.post(f"/v1/rooms/{rid}/messages", json={"client_id": cid(), "text": "Привет"}, headers=h)
    await wait_generation(client, h, rid)
    first = (await visible(client, h, rid))[-1]
    r = await client.post(f"/v1/rooms/{rid}/regenerate", json={"client_id": cid()}, headers=h)
    assert r.status_code == 200
    await wait_generation(client, h, rid)
    msgs = await visible(client, h, rid)
    assert len(msgs) == 3 and msgs[-1]["id"] != first["id"] and msgs[-1]["kind"] == "character"
    await client.post(f"/v1/rooms/{rid}/continue", json={"client_id": cid()}, headers=h)
    await wait_generation(client, h, rid)
    assert len(await visible(client, h, rid)) == 4
    # edit my own line — the next prompt uses the new text
    mine = next(m for m in await visible(client, h, rid) if m["kind"] == "player")
    r = await client.patch(f"/v1/rooms/{rid}/messages/{mine['id']}", json={"text": "Привет, бариста МАРКЕР"}, headers=h)
    assert r.status_code == 200 and r.json()["message"]["edited"] is True
    # the owner may also fix the character's line
    ai = (await visible(client, h, rid))[-1]
    r = await client.patch(f"/v1/rooms/{rid}/messages/{ai['id']}", json={"text": "*кивает* — Поправлено."}, headers=h)
    assert r.json()["message"]["text"] == "*кивает* — Поправлено."
    await client.post(f"/v1/rooms/{rid}/messages", json={"client_id": cid(), "text": "Дальше"}, headers=h)
    await wait_generation(client, h, rid)
    lp = (await client.get(f"/v1/rooms/{rid}/last-prompt", headers=h)).json()["prompt"]
    assert "МАРКЕР" in lp and "Поправлено" in lp
    # strangers can not see or edit anything
    assert (await client.patch(f"/v1/rooms/{rid}/messages/{mine['id']}", json={"text": "x"}, headers=hb)).status_code == 404
    assert (await client.get(f"/v1/rooms/{rid}/sync", params={"since": 0}, headers=hb)).status_code == 404
    # system lines and empty edits are refused
    r = await client.patch(f"/v1/rooms/{rid}/messages/{mine['id']}", json={"text": "   "}, headers=h)
    assert r.status_code == 400


async def test_suggest_three_options(client):
    h, _ = await register(client, "Mira")
    room = await start(client, h, (await demo_persona(client, h))["id"])
    r = await client.post(f"/v1/rooms/{room['id']}/suggest", headers=h)
    assert r.status_code == 200, r.text
    opts = r.json()["suggestions"]
    assert len(opts) == 3 and all(o.strip() for o in opts)
    # nothing is stored
    assert len(await visible(client, h, room["id"])) == 1


async def test_chat_photo_and_summary_memory(client):
    h, _ = await register(client, "Mira")
    p = await demo_persona(client, h, "Ада")
    room = await start(client, h, p["id"])
    rid = room["id"]
    r = await client.post(f"/v1/rooms/{rid}/photo", json={"client_id": cid(), "prompt": "голограмма в коридоре"}, headers=h)
    assert r.status_code == 200
    for _ in range(200):
        s = (await client.get(f"/v1/rooms/{rid}/sync", params={"since": 0}, headers=h)).json()
        if s["image_job"] and s["image_job"]["status"] in ("done", "failed"):
            break
        await asyncio.sleep(0.05)
    assert s["image_job"]["status"] == "done"
    photo = next(m for m in s["messages"] if m["image_id"])
    assert (await client.get(f"/v1/rooms/{rid}/images/{photo['image_id']}", headers=h)).status_code == 200
    for i in range(10):  # one reply per turn here: more turns than in a story scene before a summary
        await client.post(f"/v1/rooms/{rid}/messages", json={"client_id": cid(), "text": f"Ход номер {i}, иду дальше"}, headers=h)
        await wait_generation(client, h, rid)
    for _ in range(100):
        d = (await client.get(f"/v1/rooms/{rid}", headers=h)).json()["room"]
        if d["summary"]:
            break
        await asyncio.sleep(0.05)
    assert d["summary"], "summary was not produced"
    await client.post(f"/v1/rooms/{rid}/messages", json={"client_id": cid(), "text": "Финал"}, headers=h)
    await wait_generation(client, h, rid)
    assert "Что было раньше:" in (await client.get(f"/v1/rooms/{rid}/last-prompt", headers=h)).json()["prompt"]


async def test_chat_access_rules(client):
    ha, _ = await register(client, "Mira")
    hb, _ = await register(client, "Lev", ip="2.2.2.2")
    # someone else's private character: no chat; own draft: chat is fine for testing
    draft = (await client.post("/v1/personas", json={"name": "Тайна", "first_message": "*тишина*"}, headers=ha)).json()["persona"]
    assert (await client.post(f"/v1/personas/{draft['id']}/chats", headers=hb)).status_code == 404
    room = await start(client, ha, draft["id"])
    # the author deletes the character → the chat stays readable, a new turn fails with a clear error
    await client.delete(f"/v1/personas/{draft['id']}", headers=ha)
    await client.post(f"/v1/rooms/{room['id']}/messages", json={"client_id": cid(), "text": "Ты тут?"}, headers=ha)
    s = await wait_generation(client, ha, room["id"])
    assert s["generation"]["status"] == "failed" and "удалён" in s["generation"]["error"]
    assert len(await visible(client, ha, room["id"])) == 2
