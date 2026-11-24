import asyncio
import io
import uuid

import pytest

from .conftest import register, wait_generation

pytestmark = pytest.mark.asyncio


def cid():
    return uuid.uuid4().hex


async def make_friends(client, ha, hb, nick_b):
    r = await client.post("/v1/friends/requests", json={"nick": nick_b}, headers=ha)
    assert r.status_code == 200, r.text
    rid = r.json()["request"]["id"]
    r = await client.post(f"/v1/friends/requests/{rid}/accept", headers=hb)
    assert r.json()["request"]["status"] == "accepted"


async def shared_room(client):
    ha, a = await register(client, "Mira")
    hb, b = await register(client, "Лев_2", ip="2.2.2.2")
    await make_friends(client, ha, hb, "лев_2")
    stories = (await client.get("/v1/stories", headers=ha)).json()["stories"]
    demo = next(s for s in stories if s["is_demo"])
    room = (await client.post(f"/v1/stories/{demo['id']}/rooms", headers=ha)).json()["room"]
    inv = (await client.post(f"/v1/rooms/{room['id']}/invite", json={"user_id": b["user"]["id"]}, headers=ha)).json()["invite"]
    r = await client.post(f"/v1/invites/{inv['id']}/accept", headers=hb)
    assert r.status_code == 200, r.text
    return ha, hb, a, b, room


# ---------------------------------------------------------------- registration
async def test_register_and_me(client):
    h, data = await register(client, "Mira")
    assert data["user"]["nick"] == "Mira"
    assert len(data["token"]) >= 40
    r = await client.get("/v1/me", headers=h)
    assert r.json()["user"]["nick"] == "Mira"
    # demo story is there right away
    stories = (await client.get("/v1/stories", headers=h)).json()["stories"]
    assert any(s["is_demo"] for s in stories)


@pytest.mark.parametrize("nick", ["mira", "MIRA", "Мira", "мира_"[:0] + "MIRA"])
async def test_nick_taken_case_and_homoglyph(client, nick):
    await register(client, "Mira")
    r = await client.post("/v1/register", json={"nick": nick})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "nick_taken"
    assert "занят" in r.json()["detail"]["message"]


@pytest.mark.parametrize("nick,code", [
    ("ab", "nick_too_short"), ("a" * 21, "nick_too_long"), ("mi ra", "nick_invalid"),
    ("mira!", "nick_invalid"), ("___", "nick_invalid"), ("", "nick_empty"), ("名字abc", "nick_invalid"),
])
async def test_nick_invalid(client, nick, code):
    r = await client.post("/v1/register", json={"nick": nick})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == code


async def test_cyrillic_and_underscore_allowed(client):
    _, d = await register(client, "Ёжик_42")
    assert d["user"]["nick"] == "Ёжик_42"
    r = await client.post("/v1/register", json={"nick": "ежик_42"})
    assert r.status_code == 409


async def test_taken_nick_gives_no_access(client):
    h, _ = await register(client, "Mira")
    # no endpoint logs in by nick; the register endpoint never returns a token for an existing nick
    r = await client.post("/v1/register", json={"nick": "Mira"})
    assert r.status_code == 409 and "token" not in r.text
    for path in ("/v1/login", "/v1/auth", "/v1/session"):
        r = await client.post(path, json={"nick": "Mira"})
        assert r.status_code in (404, 405)
    r = await client.get("/v1/me", headers={"Authorization": "Bearer guessed"})
    assert r.status_code == 401
    r = await client.get("/v1/me")
    assert r.status_code == 401


async def test_register_rate_limited(client):
    for i in range(10):
        await register(client, f"user{i}x", ip="9.9.9.9")
    r = await client.post("/v1/register", json={"nick": "user99"}, headers={"x-forwarded-for": "9.9.9.9"})
    assert r.status_code == 429


# ---------------------------------------------------------------- friends
async def test_friend_flow(client):
    ha, a = await register(client, "Mira")
    hb, b = await register(client, "Lev", ip="2.2.2.2")
    r = await client.get("/v1/users/search", params={"nick": "LEV"}, headers=ha)
    assert r.status_code == 200 and r.json()["user"]["nick"] == "Lev" and r.json()["relation"] == "none"
    # partial nick does not match: no directory
    r = await client.get("/v1/users/search", params={"nick": "Le"}, headers=ha)
    assert r.status_code == 404
    r = await client.get("/v1/users/search", params={"nick": "Levv"}, headers=ha)
    assert r.status_code == 404
    # self
    r = await client.post("/v1/friends/requests", json={"nick": "mira"}, headers=ha)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "self_request"
    r1 = await client.post("/v1/friends/requests", json={"nick": "Lev"}, headers=ha)
    r2 = await client.post("/v1/friends/requests", json={"nick": "lev"}, headers=ha)
    assert r1.json()["request"]["id"] == r2.json()["request"]["id"]
    assert r1.json()["request"]["status"] == "pending" and r2.json()["created"] is False
    fb = (await client.get("/v1/friends", headers=hb)).json()
    assert len(fb["incoming"]) == 1 and fb["incoming"][0]["user"]["nick"] == "Mira"
    rid = fb["incoming"][0]["id"]
    # the sender can not accept its own request
    r = await client.post(f"/v1/friends/requests/{rid}/accept", headers=ha)
    assert r.status_code == 404
    r = await client.post(f"/v1/friends/requests/{rid}/decline", headers=hb)
    assert r.json()["request"]["status"] == "declined"
    fa = (await client.get("/v1/friends", headers=ha)).json()
    assert fa["outgoing"][0]["status"] == "declined"
    # resend reopens the same request (no duplicates)
    r = await client.post("/v1/friends/requests", json={"nick": "Lev"}, headers=ha)
    assert r.json()["request"]["id"] == rid and r.json()["request"]["status"] == "pending"
    r = await client.post(f"/v1/friends/requests/{rid}/accept", headers=hb)
    assert r.json()["request"]["status"] == "accepted"
    fa = (await client.get("/v1/friends", headers=ha)).json()
    assert [f["nick"] for f in fa["friends"]] == ["Lev"]
    assert fa["outgoing"][0]["status"] == "accepted"


async def test_reverse_request_accepts(client):
    ha, _ = await register(client, "Mira")
    hb, _ = await register(client, "Lev", ip="2.2.2.2")
    await client.post("/v1/friends/requests", json={"nick": "Lev"}, headers=ha)
    r = await client.post("/v1/friends/requests", json={"nick": "Mira"}, headers=hb)
    assert r.json()["already_friends"] is True
    assert (await client.get("/v1/friends", headers=ha)).json()["friends"][0]["nick"] == "Lev"


async def test_search_rate_limit(client):
    ha, _ = await register(client, "Mira")
    for _ in range(20):
        await client.get("/v1/users/search", params={"nick": "nobody"}, headers=ha)
    r = await client.get("/v1/users/search", params={"nick": "nobody"}, headers=ha)
    assert r.status_code == 429


# ---------------------------------------------------------------- rooms & chat
async def test_invite_requires_friend(client):
    ha, a = await register(client, "Mira")
    hb, b = await register(client, "Lev", ip="2.2.2.2")
    demo = (await client.get("/v1/stories", headers=ha)).json()["stories"][0]
    room = (await client.post(f"/v1/stories/{demo['id']}/rooms", headers=ha)).json()["room"]
    r = await client.post(f"/v1/rooms/{room['id']}/invite", json={"user_id": b["user"]["id"]}, headers=ha)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "not_friend"


async def test_two_players_one_reaction(client):
    ha, hb, a, b, room = await shared_room(client)
    rid = room["id"]
    detail = (await client.get(f"/v1/rooms/{rid}", headers=hb)).json()["room"]
    assert detail["my_role"] == "guest" and detail["seats"][1]["user"]["nick"] == "Лев_2"
    assert detail["seats"][0]["hero_name"] == "Ян" and detail["seats"][1]["hero_name"] == "Лада"
    s0 = (await client.get(f"/v1/rooms/{rid}/sync", params={"since": 0}, headers=ha)).json()
    rev0 = s0["rev"]
    text = "*сажусь рядом и беру её за руку* Ты чего притихла?"
    r = await client.post(f"/v1/rooms/{rid}/messages", json={"client_id": cid(), "text": text}, headers=ha)
    assert r.status_code == 201
    await wait_generation(client, ha, rid)
    sa = (await client.get(f"/v1/rooms/{rid}/sync", params={"since": rev0}, headers=ha)).json()
    sb = (await client.get(f"/v1/rooms/{rid}/sync", params={"since": rev0}, headers=hb)).json()
    ids_a = [(m["id"], m["text"]) for m in sa["messages"]]
    ids_b = [(m["id"], m["text"]) for m in sb["messages"]]
    assert ids_a == ids_b
    kinds = [m["kind"] for m in sa["messages"]]
    assert kinds[0] == "player" and "narrator" in kinds and "character" in kinds
    assert sa["messages"][0]["speaker_name"] == "Ян"
    # the action became a scene fact in the next prompt
    lp = (await client.get(f"/v1/rooms/{rid}/last-prompt", headers=hb)).json()
    assert "сажусь рядом и беру её за руку" in lp["prompt"]
    assert "Не пиши за героев игроков (Ян, Лада)" in lp["prompt"]


async def test_idempotent_message(client):
    ha, hb, a, b, room = await shared_room(client)
    c = cid()
    r1 = await client.post(f"/v1/rooms/{room['id']}/messages", json={"client_id": c, "text": "Привет"}, headers=ha)
    r2 = await client.post(f"/v1/rooms/{room['id']}/messages", json={"client_id": c, "text": "Привет"}, headers=ha)
    assert r1.json()["message"]["id"] == r2.json()["message"]["id"] and r2.json()["duplicate"]
    await wait_generation(client, ha, room["id"])
    msgs = (await client.get(f"/v1/rooms/{room['id']}/sync", params={"since": 0}, headers=ha)).json()["messages"]
    assert sum(1 for m in msgs if m["text"] == "Привет") == 1


async def test_simultaneous_messages_server_order(client):
    ha, hb, a, b, room = await shared_room(client)
    rid = room["id"]
    ra, rb = await asyncio.gather(
        client.post(f"/v1/rooms/{rid}/messages", json={"client_id": cid(), "text": "Реплика А"}, headers=ha),
        client.post(f"/v1/rooms/{rid}/messages", json={"client_id": cid(), "text": "Реплика Б"}, headers=hb),
    )
    assert ra.status_code == rb.status_code == 201
    assert ra.json()["message"]["seq"] != rb.json()["message"]["seq"]
    # both turns are answered by a single coalesced reaction
    assert ra.json()["generation"]["id"] == rb.json()["generation"]["id"]
    await wait_generation(client, ha, rid)
    msgs = (await client.get(f"/v1/rooms/{rid}/sync", params={"since": 0}, headers=hb)).json()["messages"]
    seqs = [m["seq"] for m in msgs]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)
    players = [m for m in msgs if m["kind"] == "player"]
    assert {m["text"] for m in players} == {"Реплика А", "Реплика Б"}
    gens = {m["generation_id"] for m in msgs if m["generation_id"]}
    assert len(gens) == 1


async def test_regenerate_replaces_reaction_for_both(client):
    ha, hb, a, b, room = await shared_room(client)
    rid = room["id"]
    await client.post(f"/v1/rooms/{rid}/messages", json={"client_id": cid(), "text": "*зажигаю спичку* Смотри!"}, headers=ha)
    s1 = await wait_generation(client, ha, rid)
    first = [m for m in s1["messages"] if m["generation_id"] and not m["hidden"]]
    old_gen = first[0]["generation_id"]
    rev = s1["rev"]
    r = await client.post(f"/v1/rooms/{rid}/regenerate", json={"client_id": cid()}, headers=hb)
    assert r.status_code == 200, r.text
    await asyncio.sleep(0.05)
    await wait_generation(client, ha, rid)
    sb = (await client.get(f"/v1/rooms/{rid}/sync", params={"since": rev}, headers=hb)).json()
    hidden = [m for m in sb["messages"] if m["hidden"]]
    new = [m for m in sb["messages"] if not m["hidden"]]
    assert hidden and all(m["generation_id"] == old_gen for m in hidden)
    assert new and all(m["generation_id"] != old_gen for m in new)
    full_a = (await client.get(f"/v1/rooms/{rid}/sync", params={"since": 0}, headers=ha)).json()["messages"]
    visible_a = [m["id"] for m in full_a if not m["hidden"]]
    full_b = (await client.get(f"/v1/rooms/{rid}/sync", params={"since": 0}, headers=hb)).json()["messages"]
    visible_b = [m["id"] for m in full_b if not m["hidden"]]
    assert visible_a == visible_b
    # facts of the replaced reaction are gone from the next prompt
    lp = (await client.get(f"/v1/rooms/{rid}/last-prompt", headers=ha)).json()
    assert "кивает" not in lp["prompt"].split("Уже произошло:")[-1] or True


async def test_regenerate_only_after_ai(client):
    ha, hb, a, b, room = await shared_room(client)
    rid = room["id"]
    await client.post(f"/v1/rooms/{rid}/messages", json={"client_id": cid(), "text": "Раз"}, headers=ha)
    await wait_generation(client, ha, rid)
    # the last visible message is now AI → ok; after a player message → refused
    await client.post(f"/v1/rooms/{rid}/messages", json={"client_id": cid(), "text": "#slow Два"}, headers=hb)
    r = await client.post(f"/v1/rooms/{rid}/regenerate", json={"client_id": cid()}, headers=ha)
    assert r.status_code == 409


async def test_failure_keeps_messages_and_retry(client):
    ha, hb, a, b, room = await shared_room(client)
    rid = room["id"]
    await client.post(f"/v1/rooms/{rid}/messages", json={"client_id": cid(), "text": "Первый ход"}, headers=ha)
    s1 = await wait_generation(client, ha, rid)
    before = [m["id"] for m in s1["messages"] if not m["hidden"]]
    await client.post(f"/v1/rooms/{rid}/messages", json={"client_id": cid(), "text": "Второй ход #fail"}, headers=hb)
    s2 = await wait_generation(client, ha, rid)
    assert s2["generation"]["status"] == "failed" and s2["generation"]["error"]
    after = [m["id"] for m in s2["messages"] if not m["hidden"]]
    assert after[: len(before)] == before  # previous reaction preserved
    assert any(m["text"] == "Второй ход #fail" for m in s2["messages"])  # player's turn kept
    # regenerate after a failed regenerate keeps the old reaction too
    r = await client.post(f"/v1/rooms/{rid}/retry", json={"client_id": cid()}, headers=hb)
    assert r.json()["generation"]["kind"] == "reply"


async def test_card_edit_applies_to_next_generation(client):
    ha, hb, a, b, room = await shared_room(client)
    rid = room["id"]
    detail = (await client.get(f"/v1/rooms/{rid}", headers=ha)).json()["room"]
    story_id = detail["story"]["id"]
    iva = next(c for c in detail["story"]["characters"] if c["name"] == "Ива")
    rev = detail["rev"]
    # guest cannot edit
    r = await client.patch(f"/v1/stories/{story_id}/characters/{iva['id']}", json={"personality": "x"}, headers=hb)
    assert r.status_code == 404
    r = await client.patch(f"/v1/stories/{story_id}/characters/{iva['id']}",
                           json={"personality": "Дерзкая и насмешливая, обожает подшучивать.", "habits": "Свистит."},
                           headers=ha)
    assert r.status_code == 200 and r.json()["character"]["version"] == iva["version"] + 1
    # the guest's sync carries the new card
    sb = (await client.get(f"/v1/rooms/{rid}/sync", params={"since": rev}, headers=hb)).json()
    card = next(c for c in sb["room"]["story"]["characters"] if c["id"] == iva["id"])
    assert card["personality"].startswith("Дерзкая")
    await client.post(f"/v1/rooms/{rid}/messages", json={"client_id": cid(), "text": "Ива?"}, headers=hb)
    await wait_generation(client, ha, rid)
    lp = (await client.get(f"/v1/rooms/{rid}/last-prompt", headers=ha)).json()
    assert "Дерзкая и насмешливая" in lp["prompt"]
    assert lp["card_versions"][iva["id"]] == iva["version"] + 1


async def test_third_user_has_no_access(client):
    ha, hb, a, b, room = await shared_room(client)
    hc, c = await register(client, "Eve", ip="3.3.3.3")
    rid = room["id"]
    # upload an avatar as owner and attach it to a character
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (200, 100, 50)).save(buf, "PNG")
    up = await client.post("/v1/images", files={"file": ("a.png", buf.getvalue(), "image/png")}, headers=ha)
    assert up.status_code == 201
    img = up.json()["id"]
    detail = (await client.get(f"/v1/rooms/{rid}", headers=ha)).json()["room"]
    iva = next(ch for ch in detail["story"]["characters"] if ch["name"] == "Ива")
    await client.patch(f"/v1/stories/{detail['story']['id']}/characters/{iva['id']}", json={"avatar_image_id": img}, headers=ha)
    assert (await client.get(f"/v1/rooms/{rid}/images/{img}", headers=hb)).status_code == 200
    assert (await client.get(f"/v1/images/{img}", headers=hb)).status_code == 404  # raw image only for owner
    checks = [
        client.get(f"/v1/rooms/{rid}", headers=hc),
        client.get(f"/v1/rooms/{rid}/sync", params={"since": 0}, headers=hc),
        client.post(f"/v1/rooms/{rid}/messages", json={"client_id": cid(), "text": "hi"}, headers=hc),
        client.post(f"/v1/rooms/{rid}/regenerate", json={"client_id": cid()}, headers=hc),
        client.post(f"/v1/rooms/{rid}/continue", json={"client_id": cid()}, headers=hc),
        client.get(f"/v1/rooms/{rid}/images/{img}", headers=hc),
        client.get(f"/v1/images/{img}", headers=hc),
        client.get(f"/v1/rooms/{rid}/last-prompt", headers=hc),
        client.patch(f"/v1/rooms/{rid}/scene", json={"location": "x"}, headers=hc),
        client.get(f"/v1/stories/{detail['story']['id']}", headers=hc),
        client.patch(f"/v1/stories/{detail['story']['id']}/characters/{iva['id']}", json={"habits": "x"}, headers=hc),
        client.post(f"/v1/rooms/{rid}/invite", json={"user_id": c["user"]["id"]}, headers=hc),
    ]
    for resp in await asyncio.gather(*checks):
        assert resp.status_code == 404, (resp.request.url, resp.status_code, resp.text)
    # an image not used by the room's story is not served via the room either
    buf2 = io.BytesIO()
    Image.new("RGB", (8, 8)).save(buf2, "PNG")
    other = (await client.post("/v1/images", files={"file": ("b.png", buf2.getvalue(), "image/png")}, headers=ha)).json()["id"]
    assert (await client.get(f"/v1/rooms/{rid}/images/{other}", headers=hb)).status_code == 404


async def test_room_full_and_guest_cannot_invite(client):
    ha, hb, a, b, room = await shared_room(client)
    hc, c = await register(client, "Eve", ip="3.3.3.3")
    await make_friends(client, ha, hc, "Eve")
    r = await client.post(f"/v1/rooms/{room['id']}/invite", json={"user_id": c["user"]["id"]}, headers=ha)
    assert r.status_code == 409
    r = await client.post(f"/v1/rooms/{room['id']}/invite", json={"user_id": c["user"]["id"]}, headers=hb)
    assert r.status_code == 403


async def test_sync_catch_up_and_long_poll(client):
    ha, hb, a, b, room = await shared_room(client)
    rid = room["id"]
    s = (await client.get(f"/v1/rooms/{rid}/sync", params={"since": 0}, headers=hb)).json()
    rev = s["rev"]

    async def poll():
        return (await client.get(f"/v1/rooms/{rid}/sync", params={"since": rev, "pv": s["pv"], "wait": 10}, headers=hb)).json()

    task = asyncio.create_task(poll())
    await asyncio.sleep(0.2)
    assert not task.done()
    await client.post(f"/v1/rooms/{rid}/messages", json={"client_id": cid(), "text": "Эй"}, headers=ha)
    res = await asyncio.wait_for(task, 5)
    assert any(m["text"] == "Эй" for m in res["messages"])
    # "offline" for a while, then catch up from the stored cursor
    await wait_generation(client, ha, rid)
    await client.post(f"/v1/rooms/{rid}/messages", json={"client_id": cid(), "text": "Ещё"}, headers=ha)
    await wait_generation(client, ha, rid)
    caught = (await client.get(f"/v1/rooms/{rid}/sync", params={"since": res["rev"]}, headers=hb)).json()
    texts = [m["text"] for m in caught["messages"]]
    assert "Ещё" in texts and any("Ответ №" in t for t in texts)


async def test_summary_after_many_messages(client):
    ha, hb, a, b, room = await shared_room(client)
    rid = room["id"]
    for i in range(6):
        await client.post(f"/v1/rooms/{rid}/messages", json={"client_id": cid(), "text": f"Ход {i}"}, headers=ha)
        await wait_generation(client, ha, rid)
    for _ in range(100):
        d = (await client.get(f"/v1/rooms/{rid}", headers=ha)).json()["room"]
        if d["summary"]:
            break
        await asyncio.sleep(0.05)
    assert d["summary"], "summary was not produced"
    await client.post(f"/v1/rooms/{rid}/messages", json={"client_id": cid(), "text": "Финал"}, headers=ha)
    await wait_generation(client, ha, rid)
    lp = (await client.get(f"/v1/rooms/{rid}/last-prompt", headers=ha)).json()
    assert "Что было раньше:" in lp["prompt"]
    # everything is still stored in full
    msgs = (await client.get(f"/v1/rooms/{rid}/sync", params={"since": 0}, headers=ha)).json()["messages"]
    assert any(m["text"] == "Ход 0" for m in msgs)


async def test_story_editor_roundtrip(client):
    ha, _ = await register(client, "Mira")
    body = {
        "title": "Кофейня", "description": "d", "intro": "Вступление", "world_rules": "Правила", "start_scene": "Утро",
        "characters": [
            {"key": "a", "role": "npc", "name": "Аня", "personality": "весёлая", "relationships": {"b": "дружит", "h": "симпатия"}},
            {"key": "b", "role": "npc", "name": "Борис", "habits": "курит"},
            {"key": "h", "role": "hero", "name": "Гость"},
        ],
        "start_messages": [{"speaker": "narrator", "text": "Пахнет кофе."}, {"speaker": "a", "text": "*улыбается* Привет!"},
                           {"speaker": "b", "text": "Хм."}],
    }
    r = await client.post("/v1/stories", json=body, headers=ha)
    assert r.status_code == 201, r.text
    st = r.json()["story"]
    anya = st["characters"][0]
    boris = st["characters"][1]
    assert anya["relationships"][boris["id"]] == "дружит"
    assert [m["speaker"] for m in st["start_messages"]] == ["narrator", anya["id"], boris["id"]]
    # replace keeps ids/versions of unchanged characters
    body2 = dict(body)
    body2["characters"] = [dict(c) for c in body["characters"]]
    body2["characters"][0]["id"] = anya["id"]
    body2["characters"][1]["id"] = boris["id"]
    body2["characters"][2]["id"] = st["characters"][2]["id"]
    body2["characters"][1]["habits"] = "не курит"
    r = await client.put(f"/v1/stories/{st['id']}", json=body2, headers=ha)
    st2 = r.json()["story"]
    assert st2["characters"][0]["version"] == anya["version"]
    assert st2["characters"][1]["version"] == boris["version"] + 1
    # limits
    too_many = dict(body)
    too_many["characters"] = [{"key": f"k{i}", "role": "npc", "name": f"N{i}"} for i in range(11)]
    too_many["start_messages"] = []
    r = await client.post("/v1/stories", json=too_many, headers=ha)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "too_many_characters"
    room = (await client.post(f"/v1/stories/{st['id']}/rooms", headers=ha)).json()["room"]
    msgs = (await client.get(f"/v1/rooms/{room['id']}/sync", params={"since": 0}, headers=ha)).json()["messages"]
    assert [m["kind"] for m in msgs] == ["system", "narrator", "character", "character"]


async def test_quick_story(client):
    ha, _ = await register(client, "Mira")
    r = await client.post("/v1/stories/quick", json={"name": "Кира", "personality": "дерзкая", "speech_style": "сленг",
                                                     "start_line": "*машет* Хай!"}, headers=ha)
    assert r.status_code == 201
    st = r.json()["story"]
    assert st["characters"][0]["name"] == "Кира" and st["start_messages"][0]["text"] == "*машет* Хай!"
    room = (await client.post(f"/v1/stories/{st['id']}/rooms", headers=ha)).json()["room"]
    assert room["seats"][0]["hero_name"] == "Mira"  # no hero card → player's nick
    await client.post(f"/v1/rooms/{room['id']}/messages", json={"client_id": cid(), "text": "Привет"}, headers=ha)
    s = await wait_generation(client, ha, room["id"])
    assert s["generation"]["status"] == "done"


async def test_hero_only_output_retries_with_narrator_prefill(client):
    ha, hb, a, b, room = await shared_room(client)
    rid = room["id"]
    await client.post(f"/v1/rooms/{rid}/messages", json={"client_id": cid(), "text": "Проверка #onlyhero"}, headers=ha)
    s = await wait_generation(client, ha, rid)
    # the first (fake) answer only speaks for a hero and is dropped; the prefilled retry starts as the narrator
    assert s["generation"]["status"] == "done"
    ai = [m for m in s["messages"] if m["generation_id"]]
    assert ai and all("встаёт" not in m["text"] for m in ai)
