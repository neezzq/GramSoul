"""Writes the OpenAPI description of the GramSoul API (for API security tools such as the 42Crunch audit).

The running server does not publish it (openapi_url=None), so it is built from the code here. Authentication in
the app is a dependency that reads the headers itself, which FastAPI cannot see; this script adds it to the
description: player endpoints need "Authorization: Bearer <session token>", admin endpoints "X-Admin-Token".

    python3 tools/export_openapi.py openapi.json [server-url]      (from any directory)
"""
import json
import os
import sys
import tempfile

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp())
os.environ.setdefault("LLM_BACKEND", "fake")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "server"))

from fastapi.routing import APIRoute  # noqa: E402

from app.main import app, current_admin, current_user  # noqa: E402


def _needs(dep, fn) -> bool:
    return any(d.call is fn or _needs(d, fn) for d in dep.dependencies)


def build(server: str) -> dict:
    spec = app.openapi()
    spec["servers"] = [{"url": server}]
    spec.setdefault("components", {})["securitySchemes"] = {
        "player": {"type": "http", "scheme": "bearer", "description": "Session token from /v1/register or /v1/login"},
        "admin": {"type": "apiKey", "in": "header", "name": "X-Admin-Token", "description": "From /v1/admin/login"},
    }
    for route in app.routes:
        if not isinstance(route, APIRoute) or route.path not in spec["paths"]:
            continue
        scheme = "admin" if _needs(route.dependant, current_admin) else "player" if _needs(route.dependant, current_user) else None
        for method in route.methods:
            op = spec["paths"][route.path].get(method.lower())
            if op is not None:
                op["security"] = [{scheme: []}] if scheme else []
    return spec


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "openapi.json"
    spec = build(sys.argv[2] if len(sys.argv) > 2 else "https://banerka.ru")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False, indent=1)
    ops = [op for p in spec["paths"].values() for op in p.values()]
    open_ops = sum(1 for op in ops if op.get("security") == [])
    print(f"{out}: OpenAPI {spec['openapi']}, {len(ops)} operations, {len(ops) - open_ops} need sign-in, {open_ops} open")
