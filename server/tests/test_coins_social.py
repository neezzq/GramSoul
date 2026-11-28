"""Coins and Elite (payments through the YooKassa stub), the look of a profile, pinned stories, favourites and the
catalog tabs, the feed."""
import os
import time

import httpx
import pytest

from .conftest import register
from .test_api import cid, wait_photo
from .test_admin import png

pytestmark = pytest.mark.asyncio


async def upload(client, h, color=(200, 30, 120)):
    r = await client.post("/v1/images", files={"file": ("a.png", png(color), "image/png")}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def admin_headers(client, monkeypatch):
    import app.main as main
    from app.common import hash_password
    monkeypatch.setattr(main.settings, "admin_password_hash", hash_password("очень-секретно"))
    r = await client.post("/v1/admin/login", json={"password": "очень-секретно"})
    return {"X-Admin-Token": r.json()["token"]}


async def test_coins_pay_for_pictures_and_come_back_when_they_fail(client, monkeypatch):
    import app.main as main
    h, me = await register(client, "Coin")
    assert me["user"]["coins"] == main.settings.coins_start_bonus == 100
    shop = (await client.get("/v1/shop", headers=h)).json()
    assert shop["coins"] == 100 and shop["costs"] == {"scene_image": 10, "avatar": 10} and shop["provider"] == "stub"
    st = (await client.get("/v1/stories", headers=h)).json()["stories"][0]
    room = (await client.post(f"/v1/stories/{st['id']}/rooms", headers=h)).json()["room"]
    # a picture costs 10
    r = await client.post(f"/v1/rooms/{room['id']}/photo", json={"client_id": cid(), "prompt": "маяк"}, headers=h)
    assert r.status_code == 200
    await wait_photo(client, h, room["id"])
    assert (await client.get("/v1/me", headers=h)).json()["user"]["coins"] == 90
    # a failed picture gives the coins back
    import app.llm as llm

    async def broken(*a, **k):
        raise llm.LLMError("модель недоступна")
    monkeypatch.setattr(llm, "generate_image", broken)
    await client.post(f"/v1/rooms/{room['id']}/photo", json={"client_id": cid(), "prompt": "снова"}, headers=h)
    s = await wait_photo(client, h, room["id"])
    assert s["image_job"]["status"] == "failed"
    assert (await client.get("/v1/me", headers=h)).json()["user"]["coins"] == 90
    hist = (await client.get("/v1/me/coins/history", headers=h)).json()["items"]
    assert [i["reason"] for i in hist[:3]] == ["scene_image_refund", "scene_image", "scene_image"]
    assert hist[-1]["reason"] == "start_bonus"
    # not enough coins: refused, nothing is queued
    main.state.db.run("UPDATE users SET coins=5 WHERE public_id=?", (me["user"]["id"],))
    r = await client.post(f"/v1/rooms/{room['id']}/photo", json={"client_id": cid(), "prompt": "ещё"}, headers=h)
    assert r.status_code == 402 and r.json()["detail"]["code"] == "no_coins"
    r = await client.post("/v1/avatars/generate", json={"name": "Ива", "description": "рыжая", "style": "anime"}, headers=h)
    assert r.status_code == 402
    assert (await client.get("/v1/me", headers=h)).json()["user"]["coins"] == 5


async def test_avatar_costs_coins_and_refunds_on_failure(client, monkeypatch):
    h, me = await register(client, "Ava")
    r = await client.post("/v1/avatars/generate", json={"name": "Ива", "description": "рыжая", "style": "anime"}, headers=h)
    assert r.status_code == 200, r.text
    assert (await client.get("/v1/me", headers=h)).json()["user"]["coins"] == 90
    import app.llm as llm

    async def broken(*a, **k):
        raise llm.LLMError("нет связи")
    monkeypatch.setattr(llm, "generate_image", broken)
    r = await client.post("/v1/avatars/generate", json={"name": "Ива", "description": "рыжая", "style": "anime"}, headers=h)
    assert r.status_code == 502
    assert (await client.get("/v1/me", headers=h)).json()["user"]["coins"] == 90


async def test_stub_payments_do_not_credit_unless_test_mode(client, monkeypatch):
    import app.main as main
    h, me = await register(client, "Payer")
    r = await client.post("/v1/payments", json={"product": "coins_300"}, headers=h)
    p = r.json()["payment"]
    assert r.status_code == 201 and p["status"] == "pending" and p["provider"] == "stub" and p["amount_rub"] == 249
    # production stub: no real payment, nothing credited
    r = await client.post(f"/v1/payments/{p['id']}/confirm-test", headers=h)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "payments_disabled"
    assert (await client.get("/v1/me", headers=h)).json()["user"]["coins"] == 100
    # test mode: the stub "pays" once
    monkeypatch.setattr(main.settings, "payments_test_mode", True)
    r = await client.post(f"/v1/payments/{p['id']}/confirm-test", headers=h)
    assert r.json()["payment"]["status"] == "succeeded" and r.json()["shop"]["coins"] == 400
    await client.post(f"/v1/payments/{p['id']}/confirm-test", headers=h)
    assert (await client.get("/v1/me", headers=h)).json()["user"]["coins"] == 400
    # Elite for 30 days with its monthly coins
    e = (await client.post("/v1/payments", json={"product": "elite_month"}, headers=h)).json()["payment"]
    await client.post(f"/v1/payments/{e['id']}/confirm-test", headers=h)
    u = (await client.get("/v1/me", headers=h)).json()["user"]
    assert u["elite"] is True and u["coins"] == 700
    assert 29.9 * 86400_000 < u["elite_until"] - time.time() * 1000 < 30.1 * 86400_000
    # someone else's payment is not reachable
    h2, _ = await register(client, "Other", ip="2.2.2.2")
    assert (await client.get(f"/v1/payments/{p['id']}", headers=h2)).status_code == 404
    assert (await client.post("/v1/payments", json={"product": "free_money"}, headers=h)).status_code == 400


async def test_yookassa_payment_is_credited_only_when_yookassa_confirms(client, monkeypatch):
    import app.coins as coins
    import app.main as main
    monkeypatch.setattr(main.settings, "yookassa_shop_id", "123456")
    monkeypatch.setattr(main.settings, "yookassa_secret_key", "test_secret")
    monkeypatch.setattr(main.settings, "public_url", "https://example.test")
    state = {"status": "pending", "paid": False, "amount": "99.00"}
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append((req.method, req.url.path, req.headers.get("Idempotence-Key")))
        assert req.headers["authorization"].startswith("Basic ")
        if req.method == "POST":
            body = __import__("json").loads(req.content)
            state["meta"] = body["metadata"]
            assert body["confirmation"]["return_url"].startswith("https://example.test/app/#/coins?payment=")
            return httpx.Response(200, json={"id": "yk-1", "status": "pending",
                                              "confirmation": {"confirmation_url": "https://yoomoney.example/pay/yk-1"}})
        return httpx.Response(200, json={"id": "yk-1", "status": state["status"], "paid": state["paid"],
                                          "amount": {"value": state["amount"], "currency": "RUB"}, "metadata": state["meta"]})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(coins.httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    h, me = await register(client, "Yookassa")
    p = (await client.post("/v1/payments", json={"product": "coins_100"}, headers=h)).json()["payment"]
    assert p["provider"] == "yookassa" and p["confirmation_url"] == "https://yoomoney.example/pay/yk-1"
    assert seen[0][2] == p["id"]  # idempotence key: one payment even if the request is repeated
    # a forged "succeeded" notification: YooKassa itself still says pending → nothing
    await client.post("/v1/payments/yookassa/webhook", json={"event": "payment.succeeded", "object": {"id": "yk-1", "status": "succeeded"}})
    assert (await client.get("/v1/me", headers=h)).json()["user"]["coins"] == 100
    # the wrong amount → nothing
    state.update(status="succeeded", paid=True, amount="1.00")
    await client.post("/v1/payments/yookassa/webhook", json={"object": {"id": "yk-1"}})
    assert (await client.get("/v1/me", headers=h)).json()["user"]["coins"] == 100
    # paid: credited once, also when the notification comes again
    state["amount"] = "99.00"
    for _ in range(2):
        await client.post("/v1/payments/yookassa/webhook", json={"object": {"id": "yk-1"}})
    assert (await client.get("/v1/me", headers=h)).json()["user"]["coins"] == 200
    assert (await client.get(f"/v1/payments/{p['id']}", headers=h)).json()["payment"]["status"] == "succeeded"
    # the test button does nothing for a real provider
    monkeypatch.setattr(main.settings, "payments_test_mode", True)
    assert (await client.post(f"/v1/payments/{p['id']}/confirm-test", headers=h)).status_code == 403


async def test_elite_looks_banner_and_frames(client, monkeypatch):
    import app.main as main
    ah = await admin_headers(client, monkeypatch)
    h, me = await register(client, "Star")
    hb, b = await register(client, "Fan", ip="2.2.2.2")
    cat = (await client.get("/v1/looks", headers=h)).json()
    assert {s["id"] for s in cat["nick_styles"]} >= {"aurora", "gold"} and any(f["elite"] for f in cat["frames"])
    # without Elite: a simple frame yes, a glowing nick / an Elite frame / a banner no
    assert (await client.patch("/v1/me/looks", json={"frame": "rose"}, headers=h)).json()["user"]["frame"] == "rose"
    for body in ({"nick_style": "aurora"}, {"frame": "neon"}, {"banner_image_id": await upload(client, h)}):
        r = await client.patch("/v1/me/looks", json=body, headers=h)
        assert r.status_code == 403 and r.json()["detail"]["code"] == "elite_required"
    assert (await client.patch("/v1/me/looks", json={"frame": "nonsense"}, headers=h)).status_code == 400
    # the admin gives Elite
    r = await client.post(f"/v1/admin/users/{me['user']['id']}/grant", json={"elite_days": 30, "coins": 50}, headers=ah)
    assert r.status_code == 200 and r.json()["coins"] == 150
    banner = await upload(client, h, (10, 120, 200))
    u = (await client.patch("/v1/me/looks", json={"nick_style": "aurora", "frame": "neon", "banner_image_id": banner}, headers=h)).json()["user"]
    assert u["elite"] and u["nick_style"] == "aurora" and u["frame"] == "neon" and u["banner_image_id"] == banner
    # others see it on the profile, in search and on the banner endpoint
    prof = (await client.get(f"/v1/users/{me['user']['id']}", headers=hb)).json()
    assert prof["user"]["nick_style"] == "aurora" and prof["user"]["frame"] == "neon" and prof["user"]["elite"]
    assert (await client.get(f"/v1/users/{me['user']['id']}/banner", headers=hb)).status_code == 200
    found = (await client.get("/v1/users/search", params={"q": "sta"}, headers=hb)).json()["users"]
    assert found[0]["user"]["nick_style"] == "aurora"
    # a new banner replaces the old one (its picture is removed)
    banner2 = await upload(client, h, (90, 90, 9))
    await client.patch("/v1/me/looks", json={"banner_image_id": banner2}, headers=h)
    assert main.state.db.one("SELECT 1 FROM images WHERE id=?", (banner,)) is None
    # Elite ends: the Elite look disappears for everyone but the choice is kept for later
    main.state.db.run("UPDATE users SET elite_until=1 WHERE public_id=?", (me["user"]["id"],))
    prof = (await client.get(f"/v1/users/{me['user']['id']}", headers=hb)).json()["user"]
    assert not prof["elite"] and prof["nick_style"] == "" and prof["frame"] == "" and prof["banner_image_id"] is None
    assert (await client.get(f"/v1/users/{me['user']['id']}/banner", headers=hb)).status_code == 404
    mine = (await client.get("/v1/me", headers=h)).json()["user"]
    assert mine["looks_choice"] == {"nick_style": "aurora", "frame": "neon", "banner_image_id": banner2}
    users = (await client.get("/v1/admin/users", headers=ah)).json()["users"]
    assert next(x for x in users if x["nick"] == "Star")["coins"] == 150


async def test_pinned_public_stories_on_a_profile(client):
    from .test_stories_voice import STORY
    h, me = await register(client, "Pinner")
    hb, b = await register(client, "Guest", ip="2.2.2.2")
    s1 = (await client.post("/v1/stories", json={**STORY, "title": "Первая"}, headers=h)).json()["story"]
    s2 = (await client.post("/v1/stories", json={**STORY, "title": "Вторая"}, headers=h)).json()["story"]
    r = await client.put("/v1/me/pins", json={"story_ids": [s1["id"]]}, headers=h)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "not_public"
    for s in (s1, s2):
        await client.patch(f"/v1/stories/{s['id']}/visibility", json={"visibility": "public"}, headers=h)
    r = await client.put("/v1/me/pins", json={"story_ids": [s2["id"], s1["id"]]}, headers=h)
    assert [x["title"] for x in r.json()["pinned_stories"]] == ["Вторая", "Первая"]
    # someone else's story can not be pinned; at most three
    other = (await client.post("/v1/stories", json=STORY, headers=hb)).json()["story"]
    assert (await client.put("/v1/me/pins", json={"story_ids": [other["id"]]}, headers=h)).status_code == 404
    assert (await client.put("/v1/me/pins", json={"story_ids": ["a", "b", "c", "d"]}, headers=h)).status_code == 400
    prof = (await client.get(f"/v1/users/{me['user']['id']}", headers=hb)).json()
    assert [x["title"] for x in prof["pinned_stories"]] == ["Вторая", "Первая"] and prof["pinned_stories"][0]["mine"] is False
    # a story made private again leaves the profile
    await client.patch(f"/v1/stories/{s2['id']}/visibility", json={"visibility": "private"}, headers=h)
    prof = (await client.get(f"/v1/users/{me['user']['id']}", headers=hb)).json()
    assert [x["title"] for x in prof["pinned_stories"]] == ["Первая"]


async def test_catalog_tabs_and_favourites(client):
    from .test_personas import CARD
    h, me = await register(client, "Author")
    hb, b = await register(client, "Reader", ip="2.2.2.2")
    p = (await client.post("/v1/personas", json={**CARD, "name": "Нова", "visibility": "public", "status": "published"},
                           headers=h)).json()["persona"]
    new = (await client.get("/v1/personas", params={"scope": "new"}, headers=hb)).json()["personas"]
    assert new[0]["id"] == p["id"] and new[0]["author"]["nick"] == "Author" and new[0]["favorite"] is False
    # favourites
    r = await client.put(f"/v1/personas/{p['id']}/favorite", headers=hb)
    assert r.json()["persona"]["favorite"] is True and r.json()["persona"]["favorites"] == 1
    fav = (await client.get("/v1/personas", params={"scope": "favorites"}, headers=hb)).json()["personas"]
    assert [x["id"] for x in fav] == [p["id"]]
    # «Для вас»: the most played and liked first
    await client.post(f"/v1/personas/{p['id']}/chats", headers=hb)
    foryou = (await client.get("/v1/personas", params={"scope": "foryou"}, headers=hb)).json()["personas"]
    assert foryou[0]["id"] == p["id"] and foryou[0]["chats_count"] == 1
    await client.delete(f"/v1/personas/{p['id']}/favorite", headers=hb)
    assert (await client.get("/v1/personas", params={"scope": "favorites"}, headers=hb)).json()["personas"] == []
    # a private character can not be favourited by others
    priv = (await client.post("/v1/personas", json={**CARD, "name": "Тайна", "visibility": "private", "status": "draft"}, headers=h)).json()["persona"]
    assert (await client.put(f"/v1/personas/{priv['id']}/favorite", headers=hb)).status_code == 404


async def test_feed_posts_likes_comments_follows(client, monkeypatch):
    import app.main as main
    ha, a = await register(client, "Writer")
    hb, b = await register(client, "Reader", ip="2.2.2.2")
    hc, c = await register(client, "Third", ip="3.3.3.3")
    img = await upload(client, ha)
    assert (await client.post("/v1/posts", json={"text": "  "}, headers=ha)).status_code == 400
    r = await client.post("/v1/posts", json={"text": "Новая история про маяк #маяк #Ночь", "image_ids": [img]}, headers=ha)
    post = r.json()["post"]
    assert r.status_code == 201 and post["images"] == [img] and post["tags"] == ["маяк", "ночь"] and post["mine"]
    # someone else's picture can not go into a post
    assert (await client.post("/v1/posts", json={"text": "x", "image_ids": [await upload(client, hb)]}, headers=ha)).status_code == 400
    # everyone sees it and its picture
    feed = (await client.get("/v1/posts", headers=hb)).json()
    assert feed["posts"][0]["id"] == post["id"] and feed["posts"][0]["author"]["nick"] == "Writer"
    assert (await client.get(f"/v1/posts/{post['id']}/images/{img}", headers=hb)).status_code == 200
    assert (await client.get(f"/v1/posts/{post['id']}/images/someone-else", headers=hb)).status_code == 404
    assert [p["id"] for p in (await client.get("/v1/posts", params={"tag": "маяк"}, headers=hb)).json()["posts"]] == [post["id"]]
    # following
    assert (await client.get("/v1/posts", params={"tab": "following"}, headers=hb)).json()["posts"] == []
    r = await client.put(f"/v1/users/{a['user']['id']}/follow", headers=hb)
    assert r.json()["followers"] == 1 and r.json()["is_following"]
    assert len((await client.get("/v1/posts", params={"tab": "following"}, headers=hb)).json()["posts"]) == 1
    assert (await client.put(f"/v1/users/{b['user']['id']}/follow", headers=hb)).status_code == 400
    # likes
    r = await client.put(f"/v1/posts/{post['id']}/like", headers=hb)
    await client.put(f"/v1/posts/{post['id']}/like", headers=hb)
    assert r.json()["post"]["likes"] == 1 and r.json()["post"]["liked"]
    assert (await client.delete(f"/v1/posts/{post['id']}/like", headers=hb)).json()["post"]["likes"] == 0
    # comments: the commenter or the post's author may delete a comment, nobody else
    cm = (await client.post(f"/v1/posts/{post['id']}/comments", json={"text": "Красиво!"}, headers=hb)).json()["comment"]
    assert cm["author"]["nick"] == "Reader" and cm["can_delete"]
    lst = (await client.get(f"/v1/posts/{post['id']}/comments", headers=hc)).json()
    assert lst["post"]["comments"] == 1 and lst["comments"][0]["can_delete"] is False
    assert (await client.delete(f"/v1/comments/{cm['id']}", headers=hc)).status_code == 403
    assert (await client.delete(f"/v1/comments/{cm['id']}", headers=ha)).status_code == 200
    # the profile counts posts and followers
    prof = (await client.get(f"/v1/users/{a['user']['id']}", headers=hb)).json()
    assert prof["posts"] == 1 and prof["followers"] == 1 and prof["is_following"]
    # only the author deletes a post; its pictures go with it
    assert (await client.delete(f"/v1/posts/{post['id']}", headers=hb)).status_code == 403
    assert (await client.delete(f"/v1/posts/{post['id']}", headers=ha)).status_code == 200
    assert main.state.db.one("SELECT 1 FROM images WHERE id=?", (img,)) is None
    # pages of 20
    monkeypatch.setattr(main.settings, "rl_posts_per_hour", 100)
    for i in range(23):
        await client.post("/v1/posts", json={"text": f"пост {i}"}, headers=hc)
    page1 = (await client.get("/v1/posts", headers=hb)).json()
    page2 = (await client.get("/v1/posts", params={"before": page1["next"]}, headers=hb)).json()
    assert len(page1["posts"]) == 20 and len(page2["posts"]) == 3 and page2["next"] is None
    # the admin removes any post
    ah = await admin_headers(client, monkeypatch)
    lst = (await client.get("/v1/admin/posts", headers=ah)).json()["posts"]
    assert (await client.delete(f"/v1/admin/posts/{lst[0]['id']}", headers=ah)).status_code == 200
    assert len((await client.get("/v1/posts", params={"tab": "user", "user_id": c["user"]["id"]}, headers=hb)).json()["posts"]) == 20


async def test_players_from_before_coins_get_the_welcome_bonus_once():
    import tempfile
    from app.coins import start_bonus_for_existing
    from app.db import Database
    db = Database(os.path.join(tempfile.mkdtemp(), "t.sqlite3"))
    db.run("INSERT INTO users(public_id, nick, nick_key, created_at) VALUES('u1','Old','old',1)")
    assert start_bonus_for_existing(db) == 1 and start_bonus_for_existing(db) == 0
    assert db.one("SELECT coins FROM users WHERE public_id='u1'")["coins"] == 100
