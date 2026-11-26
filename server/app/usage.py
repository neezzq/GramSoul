"""Token / cost accounting per user for the admin page (text replies, avatars, scene photos)."""
from __future__ import annotations

from .db import Database, now_ms


def record(db: Database, user_id: int | None, kind: str, model: str | None, result) -> None:
    """kind: text | avatar | photo | voice (prompt_tokens = characters). result: llm.LLMResult or llm.ImageResult (anything with the token fields)."""
    if result is None:
        return
    pt = getattr(result, "prompt_tokens", None) or 0
    ct = getattr(result, "output_tokens", None) or 0
    cost = getattr(result, "cost", None) or 0.0
    if not (pt or ct or cost):
        return
    db.run("INSERT INTO usage_events(user_id, kind, model, prompt_tokens, completion_tokens, cost, created_at) "
           "VALUES(?,?,?,?,?,?,?)", (user_id, kind, model, int(pt), int(ct), float(cost), now_ms()))
