"""Stage 2: standalone characters — drafts/publishing, visibility, AI fill, styled AI avatars, demo."""
import pytest

from .conftest import register

pytestmark = pytest.mark.asyncio

CARD = {"name": "Ива", "first_message": "*Ты входишь.* — Привет.", "description": "Хранительница маяка.",
        "backstory": "Выросла у моря.", "personality": "Тихая, упрямая.", "tags": ["#Маяк", "море", "море"],
        "visibility": "public", "status": "published"}


async def test_demo_characters_are_public(client):
    h, _ = await register(client, "Mira")
    ps = (await client.get("/v1/personas", headers=h)).json()["personas"]
    demo = [p for p in ps if p["is_demo"]]
    assert len(demo) == 6
    assert all(p["first_message"] and p["description"] and p["status"] == "published" for p in demo)
    assert all("personality" not in p and "backstory" not in p for p in demo)  # hidden from non-authors


async def test_draft_then_publish_and_visibility(client):
    ha, a = await register(client, "Mira")
    hb, _ = await register(client, "Lev", ip="2.2.2.2")
    # a draft may be incomplete
    r = await client.post("/v1/personas", json={"name": "", "description": "черновик"}, headers=ha)
    assert r.status_code == 201
    draft = r.json()["persona"]
    assert draft["status"] == "draft" and draft["visibility"] == "private"
    # publishing needs a name and the first message
    r = await client.put(f"/v1/personas/{draft['id']}", json={"description": "x", "status": "published"}, headers=ha)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "incomplete"
    r = await client.put(f"/v1/personas/{draft['id']}", json=CARD, headers=ha)
    assert r.status_code == 200
    p = r.json()["persona"]
    assert p["status"] == "published" and p["tags"] == ["маяк", "море"] and p["personality"] == "Тихая, упрямая."
    # another user sees the public card but not the hidden fields, and can not edit or delete it
    r = await client.get(f"/v1/personas/{p['id']}", headers=hb)
    seen = r.json()["persona"]
    assert seen["name"] == "Ива" and seen["author"]["nick"] == "Mira" and "personality" not in seen and seen["mine"] is False
    assert (await client.put(f"/v1/personas/{p['id']}", json=CARD, headers=hb)).status_code == 404
    assert (await client.delete(f"/v1/personas/{p['id']}", headers=hb)).status_code == 404
    names_b = [x["name"] for x in (await client.get("/v1/personas", headers=hb)).json()["personas"]]
    assert "Ива" in names_b
    # private → gone for others
    await client.put(f"/v1/personas/{p['id']}", json={**CARD, "visibility": "private"}, headers=ha)
    assert (await client.get(f"/v1/personas/{p['id']}", headers=hb)).status_code == 404
    assert "Ива" not in [x["name"] for x in (await client.get("/v1/personas", headers=hb)).json()["personas"]]
    # a public draft is not shown either
    await client.put(f"/v1/personas/{p['id']}", json={**CARD, "status": "draft"}, headers=ha)
    assert (await client.get(f"/v1/personas/{p['id']}", headers=hb)).status_code == 404
    # author's lists
    mine = (await client.get("/v1/personas", params={"scope": "mine"}, headers=ha)).json()["personas"]
    drafts = (await client.get("/v1/personas", params={"scope": "drafts"}, headers=ha)).json()["personas"]
    assert len(mine) == 1 and len(drafts) == 1
    assert (await client.delete(f"/v1/personas/{p['id']}", headers=ha)).json()["ok"] is True
    assert (await client.get("/v1/personas", params={"scope": "mine"}, headers=ha)).json()["personas"] == []


async def test_field_limits(client):
    h, _ = await register(client, "Mira")
    r = await client.post("/v1/personas", json={**CARD, "name": "x" * 61}, headers=h)
    assert r.status_code == 400 and "Имя" in r.json()["detail"]["message"]
    r = await client.post("/v1/personas", json={**CARD, "backstory": "x" * 2001}, headers=h)
    assert r.status_code == 400 and "Предыстория" in r.json()["detail"]["message"]
    r = await client.post("/v1/personas", json={**CARD, "description": "x" * 10000, "first_message": "y" * 5000}, headers=h)
    assert r.status_code == 201


async def test_search_by_name_and_tag(client):
    h, _ = await register(client, "Mira")
    await client.post("/v1/personas", json=CARD, headers=h)
    async def names(q):
        return [p["name"] for p in (await client.get("/v1/personas", params={"q": q}, headers=h)).json()["personas"]]
    assert await names("ива") == ["Ива"]
    assert "Капитан Тихон Гроза" in await names("#пираты")
    assert "Ива" in await names("маяк")
    assert await names("нетакого") == []


async def test_avatar_from_other_user_rejected_and_avatar_visible(client):
    import io
    from PIL import Image
    ha, _ = await register(client, "Mira")
    hb, _ = await register(client, "Lev", ip="2.2.2.2")
    buf = io.BytesIO()
    Image.new("RGB", (100, 150), (9, 9, 9)).save(buf, "PNG")
    img_b = (await client.post("/v1/images", files={"file": ("b.png", buf.getvalue(), "image/png")}, headers=hb)).json()["id"]
    r = await client.post("/v1/personas", json={**CARD, "avatar_image_id": img_b}, headers=ha)
    assert r.status_code == 404
    gen = (await client.post("/v1/avatars/generate", json={"name": "Ива", "description": "серебряные волосы, зелёный плащ",
                                                           "style": "manhwa"}, headers=ha)).json()
    assert gen["style"] == "manhwa" and abs(gen["width"] / gen["height"] - 2 / 3) < 0.02  # cropped to 2:3
    p = (await client.post("/v1/personas", json={**CARD, "avatar_image_id": gen["image_id"]}, headers=ha)).json()["persona"]
    r = await client.get(f"/v1/personas/{p['id']}/avatar", headers=hb)
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    await client.put(f"/v1/personas/{p['id']}", json={**CARD, "avatar_image_id": gen["image_id"], "visibility": "private"}, headers=ha)
    assert (await client.get(f"/v1/personas/{p['id']}/avatar", headers=hb)).status_code == 404


async def test_avatar_styles_validation_refusal_and_limits(client):
    from app import config
    h, _ = await register(client, "Mira")
    styles = (await client.get("/v1/avatar-styles", headers=h)).json()["styles"]
    assert [s["id"] for s in styles] == ["aesthetic", "anime", "realism", "painted", "manhwa", "sketch"]
    assert styles[0]["label"] == "Эстетика"
    assert "prompt" not in styles[0] and "scene" not in styles[0]  # style prompts never leave the server
    r = await client.post("/v1/avatars/generate", json={"description": "рыжая девушка", "style": "pixel"}, headers=h)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "bad_style"
    r = await client.post("/v1/avatars/generate", json={"description": " ", "name": "", "style": "anime"}, headers=h)
    assert r.status_code == 400 and "Лелуш" in r.json()["detail"]["message"]
    r = await client.post("/v1/avatars/generate", json={"description": "кто-то #refuse", "style": "anime"}, headers=h)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "avatar_refused"
    # 3 per minute per user (the three attempts above count too)
    r = await client.post("/v1/avatars/generate", json={"description": "рыжая девушка в плаще", "style": "anime"}, headers=h)
    assert r.status_code == 429
    assert config.settings.rl_avatars_per_day == 20


async def test_fill_from_idea(client):
    h, _ = await register(client, "Mira")
    r = await client.post("/v1/personas/fill", json={"idea": "хозяйка маяка с секретом"}, headers=h)
    assert r.status_code == 200, r.text
    p = r.json()["persona"]
    assert p["name"] == "Ветта" and p["first_message"].startswith("*") and p["tags"] == ["маяк", "мистика", "море"]
    r = await client.post("/v1/personas/fill", json={"idea": "#badjson"}, headers=h)
    assert r.status_code == 502 and r.json()["detail"]["code"] == "ai_bad_output"
    # nothing was saved — fill only suggests
    assert (await client.get("/v1/personas", params={"scope": "mine"}, headers=h)).json()["personas"] == []


async def test_avatar_from_a_known_character_name_and_usage_is_counted(client):
    h, me = await register(client, "Mira")
    # no appearance at all — the name of a known character is enough
    r = await client.post("/v1/avatars/generate", json={"name": "Лелуш", "description": "Лелуш Ви Британия из аниме Код Гиасс",
                                                         "style": "anime"}, headers=h)
    assert r.status_code == 200, r.text
    r = await client.post("/v1/avatars/generate", json={"name": "Лелуш Ви Британия", "description": "", "style": "painted"}, headers=h)
    assert r.status_code == 200, r.text
    import app.main as main
    rows = main.state.db.all("SELECT kind, SUM(prompt_tokens+completion_tokens) t, COUNT(*) n FROM usage_events "
                             "WHERE user_id=(SELECT id FROM users WHERE nick='Mira') GROUP BY kind")
    by = {r["kind"]: (r["t"], r["n"]) for r in rows}
    assert by["avatar"][1] == 4 and by["avatar"][0] > 0  # subject text + image, twice
