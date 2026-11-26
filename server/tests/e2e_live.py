#!/usr/bin/env python3
"""End-to-end check against a running backend with a real model.

    python3 server/tests/e2e_live.py https://example.sslip.io

Simulates two independent players (+ a third, unrelated account) with nothing
but nicknames: registration, duplicate nick, search, friend request, invite,
shared scene, live AI reaction seen identically by both, a character edit that
must appear in the next model request, regeneration, catch-up after a
"disconnect" and access checks for the third account. Prints timings."""
from __future__ import annotations

import io
import json
import random
import string
import sys
import time
import uuid

import httpx

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
GEN_TIMEOUT = float(sys.argv[2]) if len(sys.argv) > 2 else 600.0
results: list[tuple[str, bool, str]] = []
timings: list[dict] = []


def check(name: str, ok: bool, info: str = "") -> None:
    results.append((name, ok, info))
    print(("OK   " if ok else "FAIL ") + name + (f" — {info}" if info else ""), flush=True)


def cid() -> str:
    return uuid.uuid4().hex


def rnd(n=5) -> str:
    return "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(n))


c = httpx.Client(base_url=BASE, timeout=60)


PASSWORD = "e2e-" + rnd(8)


def reg(nick):
    r = c.post("/v1/register", json={"nick": nick, "password": PASSWORD})
    assert r.status_code == 201, r.text
    d = r.json()
    return {"Authorization": "Bearer " + d["token"]}, d


def wait_gen(h, room, since_rev=0, timeout=GEN_TIMEOUT):
    t0 = time.time()
    seen_running = None
    while time.time() - t0 < timeout:
        s = c.get(f"/v1/rooms/{room}/sync", params={"since": 0}, headers=h).json()
        g = s["generation"]
        if g and g["status"] == "running" and seen_running is None:
            seen_running = time.time() - t0
        if g and g["status"] in ("done", "failed"):
            return s, time.time() - t0, seen_running
        time.sleep(1.0)
    raise TimeoutError("generation timeout")


def ensure_done(h, room, s, dt):
    """Like a player pressing «Повторить генерацию» if the small model produced nothing usable."""
    for _ in range(2):
        if s["generation"]["status"] == "done":
            break
        print(f"      (generation failed: {s['generation'].get('error')}; pressing retry)")
        c.post(f"/v1/rooms/{room}/retry", json={"client_id": cid()}, headers=h)
        time.sleep(1)
        s, dt2, _ = wait_gen(h, room)
        dt += dt2
    return s, dt


def main():
    print(f"Backend: {BASE}")
    h = c.get("/v1/health").json()
    check("health", h.get("ok") is True, json.dumps(h, ensure_ascii=False))
    if h.get("local_ai"):
        check("model loaded in Ollama", h.get("model_ready") is True, h.get("model", ""))
    else:
        check("cloud AI configured", h.get("cloud") is True, h.get("cloud_model", ""))

    suffix = rnd(4)
    nick_a, nick_b, nick_c = f"Mira_{suffix}", f"Лев_{suffix}", f"eve_{suffix}"
    ha, a = reg(nick_a)
    hb, b = reg(nick_b)
    hc, cc = reg(nick_c)
    check("two independent registrations by nick + password", bool(a["token"] and b["token"]) and a["token"] != b["token"])
    r = c.post("/v1/register", json={"nick": nick_a.upper()})
    check("taken nick (other case) is refused and gives no token", r.status_code == 409 and "token" not in r.text,
          r.json()["detail"]["message"])
    r = c.post("/v1/login", json={"nick": nick_a})
    check("no login by nick alone", r.status_code in (400, 404, 405, 422) and "token" not in r.text, str(r.status_code))
    r = c.post("/v1/login", json={"nick": nick_a, "password": PASSWORD + "x"})
    check("wrong password is refused", r.status_code == 400 and "token" not in r.text)
    r = c.post("/v1/login", json={"nick": nick_a.lower(), "password": PASSWORD})
    check("login with nick + password", r.status_code == 201 and r.json()["user"]["id"] == a["user"]["id"])

    r = c.get("/v1/users/search", params={"nick": nick_b.lower()}, headers=ha)
    check("find friend by full nick", r.status_code == 200 and r.json()["user"]["nick"] == nick_b)
    r = c.get("/v1/users/search", params={"nick": nick_b[:-1]}, headers=ha)
    check("partial nick does not find anyone", r.status_code == 404)
    r1 = c.post("/v1/friends/requests", json={"nick": nick_b}, headers=ha).json()
    r2 = c.post("/v1/friends/requests", json={"nick": nick_b}, headers=ha).json()
    check("repeat request is not duplicated", r1["request"]["id"] == r2["request"]["id"], r1["request"]["status"])
    inc = c.get("/v1/friends", headers=hb).json()["incoming"]
    check("friend sees incoming request", len(inc) == 1 and inc[0]["user"]["nick"] == nick_a)
    acc = c.post(f"/v1/friends/requests/{inc[0]['id']}/accept", headers=hb).json()
    check("request accepted", acc["request"]["status"] == "accepted")
    out = c.get("/v1/friends", headers=ha).json()
    check("sender sees friend", [f["nick"] for f in out["friends"]] == [nick_b])

    demo = next(s for s in c.get("/v1/stories", headers=ha).json()["stories"] if s["is_demo"])
    room = c.post(f"/v1/stories/{demo['id']}/rooms", headers=ha).json()["room"]
    rid = room["id"]
    inv = c.post(f"/v1/rooms/{rid}/invite", json={"user_id": b["user"]["id"]}, headers=ha).json()["invite"]
    invites = c.get("/v1/invites", headers=hb).json()["invites"]
    check("friend sees the game invite", any(i["id"] == inv["id"] for i in invites))
    c.post(f"/v1/invites/{inv['id']}/accept", headers=hb)
    detail = c.get(f"/v1/rooms/{rid}", headers=hb).json()["room"]
    check("two seats taken", detail["seats"][1]["user"]["nick"] == nick_b, f"{detail['seats'][0]['hero_name']} / {detail['seats'][1]['hero_name']}")

    rev0 = c.get(f"/v1/rooms/{rid}/sync", params={"since": 0}, headers=hb).json()["rev"]
    text = "*сажусь рядом с Ивой и беру её за руку* Ты чего притихла?"
    t0 = time.time()
    c.post(f"/v1/rooms/{rid}/messages", json={"client_id": cid(), "text": text}, headers=ha)
    s, dt, _ = wait_gen(ha, rid)
    s, dt = ensure_done(ha, rid, s, dt)
    g = s["generation"]
    check("live model reaction", g["status"] == "done", g.get("error") or "")
    timings.append({"step": "first reaction", "seconds": round(dt, 1), **(g.get("stats") or {})})
    sa = c.get(f"/v1/rooms/{rid}/sync", params={"since": rev0}, headers=ha).json()["messages"]
    sb = c.get(f"/v1/rooms/{rid}/sync", params={"since": rev0}, headers=hb).json()["messages"]
    check("both players got the same reaction", [(m["id"], m["text"]) for m in sa] == [(m["id"], m["text"]) for m in sb],
          f"{len(sa)} messages")
    for m in sa:
        print(f"      [{m['kind']}] {m['speaker_name']}: {m['text']}")

    # edit Iva's personality mid-scene, then the next request must contain it
    story = detail["story"]
    iva = next(ch for ch in story["characters"] if ch["name"] == "Ива")
    marker = f"Обожает петь морские песни {rnd(3)}"
    r = c.patch(f"/v1/stories/{story['id']}/characters/{iva['id']}", json={"personality": marker}, headers=ha)
    check("owner edits character mid-scene", r.status_code == 200, f"version {r.json()['character']['version']}")
    rb = c.patch(f"/v1/stories/{story['id']}/characters/{iva['id']}", json={"personality": "hack"}, headers=hb)
    check("guest cannot edit owner's card", rb.status_code == 404)
    c.post(f"/v1/rooms/{rid}/messages", json={"client_id": cid(), "text": "*щёлкаю зажигалкой* Ива, спой что-нибудь?"},
           headers=hb)
    s, dt, _ = wait_gen(hb, rid)
    s, dt = ensure_done(hb, rid, s, dt)
    lp = c.get(f"/v1/rooms/{rid}/last-prompt", headers=ha).json()
    check("next model request contains the saved edit", marker in lp["prompt"],
          f"card v{lp['card_versions'].get(iva['id'])}")
    timings.append({"step": "second reaction", "seconds": round(dt, 1), **(s["generation"].get("stats") or {})})

    # regenerate
    before = [m for m in c.get(f"/v1/rooms/{rid}/sync", params={"since": 0}, headers=ha).json()["messages"]
              if m["generation_id"] and not m["hidden"]]
    if not before:
        check("regenerate (needs a previous AI reaction)", False, "no AI reaction to regenerate")
        return finish()
    old_gen = before[-1]["generation_id"]
    rr = c.post(f"/v1/rooms/{rid}/regenerate", json={"client_id": cid()}, headers=ha)
    check("regenerate accepted", rr.status_code == 200, rr.text[:100])
    time.sleep(1)
    s, dt, _ = wait_gen(ha, rid)
    timings.append({"step": "regenerate", "seconds": round(dt, 1), **(s["generation"].get("stats") or {})})
    va = [m["id"] for m in c.get(f"/v1/rooms/{rid}/sync", params={"since": 0}, headers=ha).json()["messages"] if not m["hidden"]]
    allb = c.get(f"/v1/rooms/{rid}/sync", params={"since": 0}, headers=hb).json()["messages"]
    vb = [m["id"] for m in allb if not m["hidden"]]
    old_hidden = all(m["hidden"] for m in allb if m["generation_id"] == old_gen)
    check("regenerated reaction replaced the old one for both", va == vb and old_hidden and s["generation"]["status"] == "done")

    # disconnect / catch-up: B stops syncing, A plays, B resumes from its cursor
    cursor = c.get(f"/v1/rooms/{rid}/sync", params={"since": 0}, headers=hb).json()["rev"]
    c.post(f"/v1/rooms/{rid}/messages", json={"client_id": cid(), "text": "*поднимаю фонарь повыше* Идём к линзе."}, headers=ha)
    s, dt, _ = wait_gen(ha, rid)
    ensure_done(ha, rid, s, dt)
    missed = c.get(f"/v1/rooms/{rid}/sync", params={"since": cursor}, headers=hb).json()["messages"]
    check("after reconnect the friend receives missed messages", any("поднимаю фонарь" in m["text"] for m in missed)
          and any(m["generation_id"] for m in missed), f"{len(missed)} missed")

    # idempotency
    same = cid()
    m1 = c.post(f"/v1/rooms/{rid}/messages", json={"client_id": same, "text": "повтор"}, headers=hb).json()
    m2 = c.post(f"/v1/rooms/{rid}/messages", json={"client_id": same, "text": "повтор"}, headers=hb).json()
    check("retrying a send does not duplicate", m1["message"]["id"] == m2["message"]["id"])
    wait_gen(hb, rid)

    # third account
    statuses = [
        c.get(f"/v1/rooms/{rid}", headers=hc).status_code,
        c.get(f"/v1/rooms/{rid}/sync", params={"since": 0}, headers=hc).status_code,
        c.post(f"/v1/rooms/{rid}/messages", json={"client_id": cid(), "text": "x"}, headers=hc).status_code,
        c.post(f"/v1/rooms/{rid}/regenerate", json={"client_id": cid()}, headers=hc).status_code,
        c.get(f"/v1/rooms/{rid}/last-prompt", headers=hc).status_code,
        c.get(f"/v1/stories/{story['id']}", headers=hc).status_code,
    ]
    # an avatar of the room's story
    from_img = None
    try:
        from PIL import Image  # optional
        buf = io.BytesIO()
        Image.new("RGB", (32, 32), (90, 60, 200)).save(buf, "PNG")
        up = c.post("/v1/images", files={"file": ("a.png", buf.getvalue(), "image/png")}, headers=ha).json()
        from_img = up["id"]
        c.patch(f"/v1/stories/{story['id']}/characters/{iva['id']}", json={"avatar_image_id": from_img}, headers=ha)
        statuses.append(c.get(f"/v1/rooms/{rid}/images/{from_img}", headers=hc).status_code)
        statuses.append(c.get(f"/v1/images/{from_img}", headers=hc).status_code)
        check("friend can load the room's image", c.get(f"/v1/rooms/{rid}/images/{from_img}", headers=hb).status_code == 200)
    except ImportError:
        pass
    check("third account is denied everywhere (incl. images)", all(s == 404 for s in statuses), str(statuses))

    return finish()


def finish():
    print("\nTimings:")
    for t in timings:
        tok_s = (t.get("output_tokens") or 0) / max(1, (t.get("output_ms") or 1)) * 1000
        print(f"  {t['step']}: {t['seconds']} s total, prompt {t.get('prompt_tokens')} tok in {t.get('prompt_ms')} ms, "
              f"output {t.get('output_tokens')} tok in {t.get('output_ms')} ms ({tok_s:.1f} tok/s)")
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
