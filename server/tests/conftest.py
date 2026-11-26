import asyncio
import os
import tempfile

import pytest
import pytest_asyncio

os.environ.setdefault("LLM_BACKEND", "fake")
os.environ.setdefault("REPLY_DEBOUNCE_MS", "50")
os.environ.setdefault("DEFAULT_AI_MODE", "local")
os.environ.setdefault("CLOUD_RECENT_MESSAGES", "10")  # keeps summary tests short
os.environ.setdefault("DEMO_CONTENT", "on")  # sample characters and story (production has none)


@pytest_asyncio.fixture
async def client():
    import httpx
    from asgi_lifespan import LifespanManager

    tmp = tempfile.mkdtemp()
    os.environ["DATA_DIR"] = tmp
    from app import config

    config.reload_settings()
    # modules imported "settings" by value — refresh them
    import app.main as main
    import app.rooms as rooms
    import app.stories as stories
    import app.worker as worker
    import app.llm as llm
    import app.images as images
    import app.personas as personas
    import app.admin as admin
    import app.voice as voice
    for m in (main, rooms, stories, worker, llm, images, personas, admin, voice):
        m.settings = config.settings
    from app.ratelimit import limiter

    limiter.reset()
    async with LifespanManager(main.app):
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=30) as c:
            yield c


async def register(client, nick, ip="1.1.1.1"):
    r = await client.post("/v1/register", json={"nick": nick}, headers={"x-forwarded-for": ip})
    assert r.status_code == 201, r.text
    data = r.json()
    return {"Authorization": f"Bearer {data['token']}"}, data


async def wait_generation(client, h, room_id, timeout=10.0, statuses=("done", "failed")):
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while loop.time() < end:
        r = await client.get(f"/v1/rooms/{room_id}/sync", params={"since": 0}, headers=h)
        g = r.json()["generation"]
        if g and g["status"] in statuses:
            # make sure no further job is queued
            if g["status"] in ("done", "failed"):
                return r.json()
        await asyncio.sleep(0.05)
    raise AssertionError("generation did not finish")
