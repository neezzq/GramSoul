"""Published stories (others play their own copy), quick publish of characters and stories, gender in prompts,
narrator-voiced actions, voice-over of the AI's lines, picture style vs. the previous frame."""
import asyncio

import pytest

from .conftest import register, stored_prompt, wait_generation
from .test_api import cid, make_friends, shared_room, wait_photo

pytestmark = pytest.mark.asyncio

STORY = {
    "title": "Ночной трамвай",
    "description": "Последний рейс через спящий город.",
    "world_rules": "Наши дни, большой город, немного мистики.",
    "start_scene": "Пустой вагон ночного трамвая.",
    "characters": [
        {"key": "c1", "role": "npc", "name": "Кондуктор", "appearance": "пожилой мужчина в форменной куртке",
         "voice": "onyx", "voice_manner": "устало и тихо", "voice_timbre": "низкий, бархатный"},
        {"key": "h1", "role": "hero", "name": "Пассажир"},
    ],
    "start_messages": [{"speaker": "c1", "text": "*Кондуктор поднимает глаза* — Конечная не скоро."}],
}


async def test_public_story_is_played_as_own_copy(client):
    ha, a = await register(client, "Автор")
    hb, b = await register(client, "Игрок", ip="2.2.2.2")
    st = (await client.post("/v1/stories", json=STORY, headers=ha)).json()["story"]
    assert st["visibility"] == "private" and st["mine"] is True
    assert st["characters"][0]["voice"] == "onyx" and st["characters"][0]["voice_manner"] == "устало и тихо"
    # a private story is invisible to others
    assert (await client.get(f"/v1/stories/{st['id']}", headers=hb)).status_code == 404
    assert (await client.post(f"/v1/stories/{st['id']}/rooms", headers=hb)).status_code == 404
    # the author plays it, then publishes — scenes already exist, publishing still works
    own_room = (await client.post(f"/v1/stories/{st['id']}/rooms", headers=ha)).json()["room"]
    r = await client.patch(f"/v1/stories/{st['id']}/visibility", json={"visibility": "public"}, headers=ha)
    assert r.status_code == 200 and r.json()["story"]["visibility"] == "public"
    assert (await client.patch(f"/v1/stories/{st['id']}/visibility", json={"visibility": "public"}, headers=hb)).status_code == 404
    # others find it in the catalog (not in "mine") and can read it
    pub = (await client.get("/v1/stories", params={"scope": "public", "q": "трамвай"}, headers=hb)).json()["stories"]
    assert [s["id"] for s in pub] == [st["id"]] and pub[0]["author"]["nick"] == "Автор" and pub[0]["mine"] is False
    own = lambda h: [x for x in (h or []) if not x["is_demo"]]  # noqa: E731 (tests run with the sample story)
    assert own((await client.get("/v1/stories", headers=hb)).json()["stories"]) == []  # "mine" by default (older apps)
    seen = (await client.get(f"/v1/stories/{st['id']}", headers=hb)).json()["story"]
    assert seen["title"] == "Ночной трамвай" and seen["mine"] is False
    # playing it gives the player an own private copy they may edit; the original stays untouched
    room = (await client.post(f"/v1/stories/{st['id']}/rooms", headers=hb)).json()["room"]
    copy_id = room["story"]["id"]
    assert copy_id != st["id"] and room["my_role"] == "owner"
    mine = own((await client.get("/v1/stories", headers=hb)).json()["stories"])
    assert [s["id"] for s in mine] == [copy_id] and mine[0]["visibility"] == "private"
    char = room["story"]["characters"][0]
    assert char["voice"] == "onyx"
    r = await client.patch(f"/v1/stories/{copy_id}/characters/{char['id']}", json={"personality": "весёлый"}, headers=hb)
    assert r.status_code == 200
    orig = (await client.get(f"/v1/stories/{st['id']}", headers=ha)).json()["story"]
    assert orig["characters"][0]["personality"] == ""
    # the start message of the copy still belongs to the copied character
    s = (await client.get(f"/v1/rooms/{room['id']}/sync", params={"since": 0}, headers=hb)).json()
    assert any(m["kind"] == "character" and m["speaker_name"] == "Кондуктор" for m in s["messages"])
    # hide it again: the catalog no longer shows it; the author's scene is untouched
    await client.patch(f"/v1/stories/{st['id']}/visibility", json={"visibility": "private"}, headers=ha)
    assert (await client.get("/v1/stories", params={"scope": "public"}, headers=hb)).json()["stories"] == []
    assert (await client.get(f"/v1/rooms/{own_room['id']}", headers=ha)).status_code == 200
    # an older app saving the story without "visibility" keeps the current value
    body = {**STORY, "characters": [{**c, "id": orig["characters"][i]["id"]} for i, c in enumerate(STORY["characters"])]}
    body["characters"][0].pop("voice")
    await client.patch(f"/v1/stories/{st['id']}/visibility", json={"visibility": "public"}, headers=ha)
    r = await client.put(f"/v1/stories/{st['id']}", json=body, headers=ha)
    assert r.json()["story"]["visibility"] == "public" and r.json()["story"]["characters"][0]["voice"] == "onyx"


async def test_story_cover_visible_in_catalog(client):
    from .test_admin import png
    ha, a = await register(client, "Автор")
    hb, b = await register(client, "Игрок", ip="2.2.2.2")
    img = (await client.post("/v1/images", files={"file": ("a.png", png(), "image/png")}, headers=ha)).json()
    st = (await client.post("/v1/stories", json={**STORY, "cover_image_id": img["id"]}, headers=ha)).json()["story"]
    url = f"/v1/stories/{st['id']}/images/{img['id']}"
    assert (await client.get(url, headers=hb)).status_code == 404  # private
    await client.patch(f"/v1/stories/{st['id']}/visibility", json={"visibility": "public"}, headers=ha)
    assert (await client.get(url, headers=hb)).status_code == 200
    other = (await client.post("/v1/images", files={"file": ("b.png", png((1, 2, 3)), "image/png")}, headers=ha)).json()
    assert (await client.get(f"/v1/stories/{st['id']}/images/{other['id']}", headers=hb)).status_code == 404
    # the copy has its own pictures
    room = (await client.post(f"/v1/stories/{st['id']}/rooms", headers=hb)).json()["room"]
    cover = room["story"]["cover_image_id"]
    assert cover and cover != img["id"]
    assert (await client.get(f"/v1/images/{cover}", headers=hb)).status_code == 200


async def test_persona_published_after_chats_exist(client):
    ha, a = await register(client, "Автор")
    hb, b = await register(client, "Игрок", ip="2.2.2.2")
    body = {"name": "Лиса", "first_message": "*Лиса щурится* — Ну привет.", "description": "рыжая хитрая",
            "visibility": "private", "status": "draft", "voice": "nova", "voice_manner": "игриво, с улыбкой"}
    p = (await client.post("/v1/personas", json=body, headers=ha)).json()["persona"]
    assert p["voice"] == "nova" and p["voice_manner"] == "игриво, с улыбкой"
    await client.post(f"/v1/personas/{p['id']}/chats", headers=ha)
    assert (await client.get(f"/v1/personas/{p['id']}", headers=hb)).status_code == 404
    r = await client.patch(f"/v1/personas/{p['id']}/visibility", json={"visibility": "public"}, headers=ha)
    assert r.status_code == 200 and r.json()["persona"]["visibility"] == "public" and r.json()["persona"]["status"] == "published"
    assert (await client.get(f"/v1/personas/{p['id']}", headers=hb)).status_code == 200
    assert (await client.patch(f"/v1/personas/{p['id']}/visibility", json={"visibility": "private"}, headers=hb)).status_code == 404
    # an older app saving without voice fields keeps the voice
    r = await client.put(f"/v1/personas/{p['id']}", json={k: v for k, v in body.items() if not k.startswith("voice")}, headers=ha)
    assert r.json()["persona"]["voice"] == "nova"
    r = await client.put(f"/v1/personas/{p['id']}", json={**body, "voice": "robot"}, headers=ha)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "bad_voice"


async def test_gender_and_narrator_voice_in_prompts(client):
    h, me = await register(client, "Мира")
    assert me["user"]["gender"] == ""
    r = await client.patch("/v1/me", json={"gender": "female"}, headers=h)
    assert r.status_code == 200 and r.json()["user"]["gender"] == "female"
    assert (await client.patch("/v1/me", json={"gender": "robot"}, headers=h)).status_code in (400, 422)
    p = (await client.get("/v1/personas", headers=h)).json()["personas"][0]
    room = (await client.post(f"/v1/personas/{p['id']}/chats", headers=h)).json()["room"]
    await client.post(f"/v1/rooms/{room['id']}/messages", json={"client_id": cid(), "text": "Привет"}, headers=h)
    await wait_generation(client, h, room["id"])
    lp = stored_prompt(room["id"])
    assert "Мира) — женщина, обращайся к ней в женском роде" in lp
    assert "от лица рассказчика" in lp and "третьем лице" in lp
    # in a story scene: players without a hero card are addressed by their gender
    ha, hb, a, b, sroom = await shared_room(client)
    await client.patch("/v1/me", json={"gender": "male"}, headers=hb)
    await client.post(f"/v1/rooms/{sroom['id']}/messages", json={"client_id": cid(), "text": "Привет"}, headers=ha)
    await wait_generation(client, ha, sroom["id"])
    lp = (await client.get(f"/v1/rooms/{sroom['id']}/last-prompt", headers=ha)).json()["prompt"]
    assert "от лица рассказчика" in lp


async def test_voice_over_of_ai_lines(client, monkeypatch):
    import app.main as main
    ha, hb, a, b, room = await shared_room(client)
    hc, _ = await register(client, "Чужой", ip="9.9.9.9")
    v = (await client.get("/v1/voices", headers=ha)).json()
    assert v["available"] is True and {"id": "onyx", "label": v["voices"][[x["id"] for x in v["voices"]].index("onyx")]["label"]} in v["voices"]
    assert v["manners"] and v["timbres"]
    rid = room["id"]
    await client.post(f"/v1/rooms/{rid}/messages", json={"client_id": cid(), "text": "*машу рукой* Привет"}, headers=ha)
    s = await wait_generation(client, ha, rid)
    ai = [m for m in s["messages"] if m["kind"] in ("character", "narrator") and not m["image_id"]]
    char = next(m for m in ai if m["kind"] == "character")
    r = await client.post(f"/v1/rooms/{rid}/messages/{char['id']}/speech", headers=hb)
    assert r.status_code == 200 and r.headers["content-type"] == "audio/mpeg" and len(r.content) > 1000
    # a stranger and player lines get nothing
    assert (await client.post(f"/v1/rooms/{rid}/messages/{char['id']}/speech", headers=hc)).status_code == 404
    mine = next(m for m in s["messages"] if m["kind"] == "player")
    assert (await client.post(f"/v1/rooms/{rid}/messages/{mine['id']}/speech", headers=ha)).status_code == 404
    # the same line again comes from the cache and is not counted twice
    db = main.state.db
    n1 = db.one("SELECT COUNT(*) n FROM usage_events WHERE kind='voice'")["n"]
    await client.post(f"/v1/rooms/{rid}/messages/{char['id']}/speech", headers=ha)
    assert db.one("SELECT COUNT(*) n FROM usage_events WHERE kind='voice'")["n"] == n1 == 1
    # preview of a voice for the editor
    r = await client.post("/v1/voice/preview", json={"voice": "nova", "manner": "игриво", "timbre": "звонкий"}, headers=ha)
    assert r.status_code == 200 and r.headers["content-type"] == "audio/mpeg"
    assert (await client.post("/v1/voice/preview", json={"voice": "robot"}, headers=ha)).status_code == 400
    # no key on the server: voice-over is off, with a clear message
    monkeypatch.setattr(main.settings, "llm_backend", "openrouter")
    monkeypatch.setattr(main.settings, "openrouter_api_key", "")
    monkeypatch.setattr(main.settings, "tts_api_key", "")
    import app.voice as V
    monkeypatch.setattr(V, "settings", main.settings)
    r = await client.post("/v1/voice/preview", json={"voice": "alloy", "text": "другой текст"}, headers=ha)
    assert r.status_code == 503 and r.json()["detail"]["code"] == "voice_off"


async def test_spoken_parts_and_instructions():
    from app import voice as V
    speech, acts = V.spoken_parts("*Вера улыбается* — Привет!\n*Она кивает* — Пойдём.")
    assert speech == "Привет! Пойдём." and acts == "Вера улыбается Она кивает"
    i = V.instructions(V.VoiceSpec("nova", "игриво", "звонкий"))
    assert "Манера речи: игриво" in i and "Тембр и подача голоса: звонкий" in i


async def test_style_change_drops_previous_frame(client):
    import app.main as main
    ha, hb, a, b, room = await shared_room(client)
    rid = room["id"]

    def last_prompt():
        r = main.state.db.one("SELECT id FROM rooms WHERE public_id=?", (rid,))
        return main.state.db.one("SELECT prompt, style FROM image_jobs WHERE room_id=? ORDER BY id DESC LIMIT 1", (r["id"],))

    async def draw():
        await client.post(f"/v1/rooms/{rid}/photo", json={"client_id": cid()}, headers=ha)
        for _ in range(200):
            j = (await client.get(f"/v1/rooms/{rid}/sync", params={"since": 0}, headers=ha)).json()["image_job"]
            if j and j["status"] in ("done", "failed"):
                return j
            await asyncio.sleep(0.05)

    await draw()
    assert last_prompt()["style"] == "aesthetic"
    await draw()
    assert "предыдущий кадр" in last_prompt()["prompt"]
    # another style: the old frame is not attached (the model would copy its look), the style wins
    await client.patch(f"/v1/rooms/{rid}/settings", json={"image_style": "anime"}, headers=ha)
    await draw()
    p = last_prompt()
    assert p["style"] == "anime" and "предыдущий кадр" not in p["prompt"]
    assert "важнее любых приложенных картинок" in p["prompt"] and "anime" in p["prompt"]
    await draw()
    assert "предыдущий кадр" in last_prompt()["prompt"]  # same style again: continuity is back


async def test_voice_over_through_http_picks_an_offered_model(client, monkeypatch):
    """The real HTTP path against a local stand-in for OpenRouter: an outdated TTS_MODEL is replaced by the
    model OpenRouter actually offers, and a provider error reaches the player in plain words."""
    import os, socket, sys, threading
    from http.server import ThreadingHTTPServer
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "tools"))
    import mock_openrouter
    import app.main as main
    import app.voice as V
    sock = socket.socket(); sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]; sock.close()
    srv = ThreadingHTTPServer(("127.0.0.1", port), mock_openrouter.H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        s = main.settings
        monkeypatch.setattr(s, "llm_backend", "openrouter")
        monkeypatch.setattr(s, "tts_api_key", "sk-or-mock")
        monkeypatch.setattr(s, "tts_base_url", f"http://127.0.0.1:{port}/api/v1")
        monkeypatch.setattr(s, "tts_model", "openai/gpt-4o-mini-tts-2025-12-15")  # what the server had: not offered
        monkeypatch.setattr(V, "settings", s)
        monkeypatch.setattr(V, "_resolved", {"model": None, "voices": None, "at": 0.0})
        h, _ = await register(client, "Голос")
        r = await client.post("/v1/voice/preview", json={"voice": "onyx", "manner": "устало", "text": "Конечная не скоро."}, headers=h)
        assert r.status_code == 200 and r.headers["content-type"] == "audio/mpeg" and len(r.content) > 1000
        assert V.current_model() == "openai/gpt-4o-mini-tts"
        assert (await client.get("/v1/health")).json()["voice_model"] == "openai/gpt-4o-mini-tts"
        # a model that was dropped later: re-read the list and retry once
        monkeypatch.setattr(V, "_resolved", {"model": "openai/old-tts", "voices": None, "at": __import__("time").time()})
        r = await client.post("/v1/voice/preview", json={"voice": "nova", "text": "Другая фраза."}, headers=h)
        assert r.status_code == 200 and V.current_model() == "openai/gpt-4o-mini-tts"
        # nothing offered at all: the player only learns that the voice-over is unavailable; OpenRouter's own
        # reason (it may tell about the owner's account settings) goes to the admin page
        monkeypatch.setattr(mock_openrouter, "SPEECH_MODELS", [])
        monkeypatch.setattr(V, "_resolved", {"model": None, "voices": None, "at": 0.0})
        r = await client.post("/v1/voice/preview", json={"voice": "nova", "text": "Третья фраза."}, headers=h)
        msg = r.json()["detail"]["message"]
        assert r.status_code == 502 and msg == V.UNAVAILABLE and "exist" not in msg and "OpenRouter" not in msg
        from app.common import hash_password
        monkeypatch.setattr(s, "admin_password_hash", hash_password("очень-секретно"))
        ah = {"X-Admin-Token": (await client.post("/v1/admin/login", json={"password": "очень-секретно"})).json()["token"]}
        problem = (await client.get("/v1/admin/users", headers=ah)).json()["voice_problem"]
        assert "does not exist" in problem["text"] and problem["at"] > 0
        # works again: the admin page no longer shows a problem
        monkeypatch.setattr(mock_openrouter, "SPEECH_MODELS", [{"id": "openai/gpt-4o-mini-tts", "supported_voices": ["nova"]}])
        monkeypatch.setattr(V, "_resolved", {"model": None, "voices": None, "at": 0.0})
        r = await client.post("/v1/voice/preview", json={"voice": "nova", "text": "Четвёртая фраза."}, headers=h)
        assert r.status_code == 200
        assert (await client.get("/v1/admin/users", headers=ah)).json()["voice_problem"] is None
    finally:
        srv.shutdown()
        V._last_problem.clear()


async def test_copies_of_a_public_story_are_reused_and_limited(client, monkeypatch):
    """Starting someone else's story again does not copy it (and its pictures) again, unless the player changed
    their copy or the author changed the original; the number of copies is limited."""
    import app.main as main
    import app.stories as stories_mod
    from .test_admin import png
    db = main.state.db
    ha, a = await register(client, "Автор")
    hb, b = await register(client, "Игрок", ip="2.2.2.2")
    img = (await client.post("/v1/images", files={"file": ("a.png", png(), "image/png")}, headers=ha)).json()
    st = (await client.post("/v1/stories", json={**STORY, "cover_image_id": img["id"]}, headers=ha)).json()["story"]
    await client.patch(f"/v1/stories/{st['id']}/visibility", json={"visibility": "public"}, headers=ha)
    pics = lambda: db.one("SELECT COUNT(*) n FROM images i JOIN users u ON u.id=i.owner_id WHERE u.public_id=?",  # noqa: E731
                          (b["user"]["id"],))["n"]
    play = lambda: client.post(f"/v1/stories/{st['id']}/rooms", headers=hb)  # noqa: E731
    await asyncio.sleep(0.005)
    r1 = (await play()).json()["room"]
    r2 = (await play()).json()["room"]
    assert r1["story"]["id"] == r2["story"]["id"] and pics() == 1
    # deleting the scene and starting again: still the same copy
    await client.delete(f"/v1/rooms/{r1['id']}", headers=hb)
    await client.delete(f"/v1/rooms/{r2['id']}", headers=hb)
    r3 = (await play()).json()["room"]
    assert r3["story"]["id"] == r1["story"]["id"] and pics() == 1
    # the player changed their copy: the next start makes a fresh one, the changed copy stays as it is
    char = r3["story"]["characters"][0]
    await client.patch(f"/v1/stories/{r3['story']['id']}/characters/{char['id']}", json={"personality": "весёлый"}, headers=hb)
    await asyncio.sleep(0.005)
    r4 = (await play()).json()["room"]
    assert r4["story"]["id"] != r3["story"]["id"] and pics() == 2
    # the author changed the original: a fresh copy with the new text
    orig = (await client.get(f"/v1/stories/{st['id']}", headers=ha)).json()["story"]
    body = {**STORY, "cover_image_id": img["id"], "title": "Ночной трамвай 2",
            "characters": [{**c, "id": orig["characters"][i]["id"]} for i, c in enumerate(STORY["characters"])]}
    await asyncio.sleep(0.005)
    assert (await client.put(f"/v1/stories/{st['id']}", json=body, headers=ha)).status_code == 200
    await asyncio.sleep(0.005)
    r5 = (await play()).json()["room"]
    assert r5["story"]["id"] != r4["story"]["id"] and r5["story"]["title"] == "Ночной трамвай 2" and pics() == 3
    # too many copies: refused before anything is copied
    monkeypatch.setattr(stories_mod, "MAX_STORY_COPIES", 3)
    c5 = r5["story"]["characters"][0]
    r = await client.patch(f"/v1/stories/{r5['story']['id']}/characters/{c5['id']}", json={"personality": "грустный"}, headers=hb)
    assert r.status_code == 200
    r = await play()
    assert r.status_code == 400 and r.json()["detail"]["code"] == "too_many_copies" and pics() == 3


async def test_deleting_a_copy_frees_its_pictures_and_copies_per_day_are_limited(client, monkeypatch):
    """A deleted story takes along the pictures nothing else uses (cover, portraits, scene pictures); deleting
    copies does not reset the number of copies a player may start per day."""
    import os
    import app.main as main
    from .test_api import wait_photo
    from .test_admin import png
    db = main.state.db
    monkeypatch.setattr(main.settings, "rl_story_copies_per_day", 2)
    ha, a = await register(client, "Автор")
    hb, b = await register(client, "Игрок", ip="2.2.2.2")
    img = (await client.post("/v1/images", files={"file": ("a.png", png(), "image/png")}, headers=ha)).json()
    st = (await client.post("/v1/stories", json={**STORY, "cover_image_id": img["id"]}, headers=ha)).json()["story"]
    await client.patch(f"/v1/stories/{st['id']}/visibility", json={"visibility": "public"}, headers=ha)
    await asyncio.sleep(0.005)
    exists = lambda iid: (db.one("SELECT 1 FROM images WHERE id=?", (iid,)) is not None,  # noqa: E731
                          os.path.exists(os.path.join(main.settings.images_dir, iid + ".jpg")))
    # a copy with its own cover and a scene picture
    room = (await client.post(f"/v1/stories/{st['id']}/rooms", headers=hb)).json()["room"]
    cover = room["story"]["cover_image_id"]
    assert cover and cover != img["id"] and exists(cover) == (True, True)
    await client.post(f"/v1/rooms/{room['id']}/photo", json={"client_id": cid(), "prompt": "трамвай в тумане"}, headers=hb)
    s = await wait_photo(client, hb, room["id"])
    scene = next(m["image_id"] for m in s["messages"] if m["image_id"])
    assert exists(scene) == (True, True)
    # the player deletes the copy: its pictures are gone, the author's original keeps its cover
    assert (await client.delete(f"/v1/stories/{room['story']['id']}", headers=hb)).status_code == 200
    assert exists(cover) == (False, False) and exists(scene) == (False, False)
    assert exists(img["id"]) == (True, True)
    assert (await client.get(f"/v1/stories/{st['id']}/images/{img['id']}", headers=hb)).status_code == 200
    # starting again makes a new copy (the deleted one is not counted any more) — but only twice a day
    r2 = (await client.post(f"/v1/stories/{st['id']}/rooms", headers=hb)).json()["room"]
    await client.delete(f"/v1/stories/{r2['story']['id']}", headers=hb)
    r = await client.post(f"/v1/stories/{st['id']}/rooms", headers=hb)
    assert r.status_code == 429 and r.json()["detail"]["code"] == "rate_limited"
    assert db.one("SELECT COUNT(*) n FROM stories s JOIN users u ON u.id=s.owner_id WHERE u.public_id=? AND s.is_demo=0",
                  (b["user"]["id"],))["n"] == 0
    # a picture used elsewhere stays: the author's cover is also their profile photo
    await client.patch("/v1/me", json={"avatar_image_id": img["id"]}, headers=ha)
    assert (await client.delete(f"/v1/stories/{st['id']}", headers=ha)).status_code == 200
    assert exists(img["id"]) == (True, True)
    assert (await client.get(f"/v1/users/{a['user']['id']}/avatar", headers=hb)).status_code == 200


async def test_deleted_scene_and_character_take_their_pictures_and_stale_copies_are_replaced(client, monkeypatch):
    import os
    import app.main as main
    from .test_api import wait_photo
    from .test_admin import png
    from .test_personas import CARD
    db = main.state.db
    on_disk = lambda iid: (db.one("SELECT 1 FROM images WHERE id=?", (iid,)) is not None,  # noqa: E731
                           os.path.exists(os.path.join(main.settings.images_dir, iid + ".jpg")))
    ha, a = await register(client, "Автор")
    hb, b = await register(client, "Игрок", ip="2.2.2.2")
    # a deleted scene takes its pictures along
    st = (await client.post("/v1/stories", json=STORY, headers=hb)).json()["story"]
    room = (await client.post(f"/v1/stories/{st['id']}/rooms", headers=hb)).json()["room"]
    await client.post(f"/v1/rooms/{room['id']}/photo", json={"client_id": cid(), "prompt": "трамвай"}, headers=hb)
    s = await wait_photo(client, hb, room["id"])
    scene = next(m["image_id"] for m in s["messages"] if m["image_id"])
    assert on_disk(scene) == (True, True)
    assert (await client.delete(f"/v1/rooms/{room['id']}", headers=hb)).status_code == 200
    assert on_disk(scene) == (False, False)
    # a deleted character takes its portrait, unless it is used elsewhere (here: also the profile photo)
    img1 = (await client.post("/v1/images", files={"file": ("a.png", png(), "image/png")}, headers=hb)).json()["id"]
    img2 = (await client.post("/v1/images", files={"file": ("b.png", png((9, 9, 9)), "image/png")}, headers=hb)).json()["id"]
    p1 = (await client.post("/v1/personas", json={**CARD, "avatar_image_id": img1}, headers=hb)).json()["persona"]
    p2 = (await client.post("/v1/personas", json={**CARD, "name": "Вторая", "avatar_image_id": img2}, headers=hb)).json()["persona"]
    await client.patch("/v1/me", json={"avatar_image_id": img2}, headers=hb)
    await client.delete(f"/v1/personas/{p1['id']}", headers=hb)
    await client.delete(f"/v1/personas/{p2['id']}", headers=hb)
    assert on_disk(img1) == (False, False) and on_disk(img2) == (True, True)
    # an unchanged copy without scenes is replaced when the author changed the original — no day slot used
    monkeypatch.setattr(main.settings, "rl_story_copies_per_day", 1)
    pub = (await client.post("/v1/stories", json=STORY, headers=ha)).json()["story"]
    await client.patch(f"/v1/stories/{pub['id']}/visibility", json={"visibility": "public"}, headers=ha)
    await asyncio.sleep(0.005)
    r1 = (await client.post(f"/v1/stories/{pub['id']}/rooms", headers=hb)).json()["room"]
    await client.delete(f"/v1/rooms/{r1['id']}", headers=hb)
    await asyncio.sleep(0.005)
    await client.patch(f"/v1/stories/{pub['id']}/visibility", json={"visibility": "public"}, headers=ha)  # bumps it
    await asyncio.sleep(0.005)
    r = await client.post(f"/v1/stories/{pub['id']}/rooms", headers=hb)
    assert r.status_code == 201, r.text
    copies = [s for s in (await client.get("/v1/stories", headers=hb)).json()["stories"] if not s["is_demo"] and s["id"] != st["id"]]
    assert [c["id"] for c in copies] == [r.json()["room"]["story"]["id"]] != [r1["story"]["id"]]


async def test_voice_rate_limit_is_shown_to_the_admin(client, monkeypatch):
    import httpx
    import app.voice as V
    import app.main as main
    monkeypatch.setattr(main.settings, "llm_backend", "openrouter")
    monkeypatch.setattr(main.settings, "tts_api_key", "sk-or-mock")
    monkeypatch.setattr(V, "_resolved", {"model": "openai/gpt-4o-mini-tts", "voices": None, "at": __import__("time").time()})

    class Busy(httpx.AsyncClient):
        async def post(self, *a, **k):
            return httpx.Response(429, json={"error": {"message": "Rate limit exceeded"}})
    monkeypatch.setattr(V.httpx, "AsyncClient", Busy)
    h, _ = await register(client, "Голос")
    try:
        r = await client.post("/v1/voice/preview", json={"voice": "nova", "text": "Пятая фраза."}, headers=h)
        assert r.status_code == 429
        p = V.last_problem()
        assert "429" in p["text"] and "ok_at" in p
    finally:
        V._last_problem.clear()


async def test_picture_reference_lookups_use_indexes(client):
    import app.main as main
    db = main.state.db
    for table, col in (("messages", "image_id"), ("image_jobs", "image_id"), ("characters", "avatar_image_id"),
                       ("personas", "avatar_image_id"), ("stories", "cover_image_id"), ("users", "avatar_image_id"),
                       ("post_images", "image_id"), ("users", "banner_image_id")):
        plan = " ".join(r[3] for r in db.all(f"EXPLAIN QUERY PLAN SELECT 1 FROM {table} WHERE {col}=? LIMIT 1", ("x",)))
        assert "USING INDEX" in plan or "USING COVERING INDEX" in plan, (table, plan)
