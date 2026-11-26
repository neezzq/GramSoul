#!/usr/bin/env python3
"""Serve the web app and the API from one origin, like Caddy does on the VPS.

    cd server && LLM_BACKEND=fake DATA_DIR=/tmp/gs python3 ../tools/web_dev.py 8010
    open http://127.0.0.1:8010/app/
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "server"))

import uvicorn  # noqa: E402
from starlette.applications import Starlette  # noqa: E402
from starlette.responses import RedirectResponse  # noqa: E402
from starlette.routing import Mount, Route  # noqa: E402
from starlette.staticfiles import StaticFiles  # noqa: E402

from app.main import app as api  # noqa: E402

site = os.path.join(HERE, "..", "deploy", "site")
web = Starlette(routes=[
    Route("/app", lambda r: RedirectResponse("/app/")),
    Route("/admin", lambda r: RedirectResponse("/admin/")),
    Mount("/app", StaticFiles(directory=os.path.join(site, "app"), html=True)),
    Mount("/admin", StaticFiles(directory=os.path.join(site, "admin"), html=True)),
    Mount("/v1", app=api),  # the API keeps its /v1 prefix below
])


# the same Content-Security-Policy as deploy/Caddyfile, so violations show up in tests
CSP = ("default-src 'self'; img-src 'self' blob: data:; media-src 'self' blob: data:; style-src 'self'; script-src 'self'; connect-src 'self'; "
       "manifest-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")


async def asgi(scope, receive, send):
    if scope["type"] == "lifespan":
        return await api(scope, receive, send)
    if scope["type"] in ("http", "websocket") and scope["path"].startswith("/v1"):
        return await api(scope, receive, send)

    async def send_with_csp(msg):
        if msg["type"] == "http.response.start" and scope["path"].startswith(("/app", "/admin")):
            msg["headers"] = list(msg.get("headers", [])) + [(b"content-security-policy", CSP.encode()),
                                                              (b"cache-control", b"no-cache")]
        await send(msg)

    return await web(scope, receive, send_with_csp)


if __name__ == "__main__":
    uvicorn.run(asgi, host="127.0.0.1", port=int(sys.argv[1]) if len(sys.argv) > 1 else 8010, log_level="warning")
