"""The single generation worker. Exactly one model call runs at a time for the
whole server; jobs wait in the ``generations`` table (status ``queued``)."""
from __future__ import annotations

import asyncio
import json
import logging

from . import llm
from . import prompt as P
from .common import hub, new_id
from .config import settings
from .db import Database, now_ms
from .rooms import _append, _bump, _notify_room, seats_of

log = logging.getLogger("fonar.worker")


class Worker:
    def __init__(self, db: Database):
        self.db = db
        self._wake = asyncio.Event()
        self._task: asyncio.Task | None = None
        self.busy = False

    def start(self) -> None:
        # jobs that were running when the server stopped are failed, not lost silently
        rows = self.db.all("SELECT id, room_id FROM generations WHERE status='running'")
        for r in rows:
            with self.db.tx():
                self.db.run("UPDATE generations SET status='failed', error=?, finished_at=? WHERE id=?",
                            ("Сервер перезапускался во время генерации. Нажми «Повторить».", now_ms(), r["id"]))
                _bump(self.db, r["room_id"])
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass

    def wake(self) -> None:
        self._wake.set()

    def queue_length(self) -> int:
        return self.db.one("SELECT COUNT(*) n FROM generations WHERE status IN ('queued','running')")["n"]

    # ------------------------------------------------------------------
    def _next_job(self):
        return self.db.one(
            "SELECT * FROM generations WHERE status='queued' ORDER BY (kind='summary'), id LIMIT 1"
        )

    async def _loop(self) -> None:
        while True:
            try:
                job = self._next_job()
                if job is None:
                    self._wake.clear()
                    try:
                        await asyncio.wait_for(self._wake.wait(), timeout=30)
                    except asyncio.TimeoutError:
                        pass
                    continue
                wait_ms = job["not_before_ms"] - now_ms()
                if wait_ms > 0:
                    self._wake.clear()
                    try:
                        await asyncio.wait_for(self._wake.wait(), timeout=wait_ms / 1000)
                    except asyncio.TimeoutError:
                        pass
                    continue
                self.busy = True
                try:
                    if job["kind"] == "summary":
                        await self._run_summary(job)
                    else:
                        await self._run_generation(job)
                finally:
                    self.busy = False
            except asyncio.CancelledError:
                raise
            except Exception:  # never let the worker die
                log.exception("worker loop error")
                await asyncio.sleep(1)

    # ------------------------------------------------------------------
    def _load_prompt_input(self, room, mode: str, exclude_generation: int | None) -> tuple[P.PromptInput, list[P.Card], list[P.Seat]]:
        db = self.db
        story = db.one("SELECT * FROM stories WHERE id=?", (room["story_id"],))
        chars = db.all("SELECT * FROM characters WHERE story_id=? ORDER BY position", (room["story_id"],))

        def to_card(c) -> P.Card:
            return P.Card(id=c["id"], public_id=c["public_id"], role=c["role"], name=c["name"], age=c["age"],
                          appearance=c["appearance"], habits=c["habits"], personality=c["personality"],
                          motivation=c["motivation"], backstory=c["backstory"], speech_style=c["speech_style"],
                          relationships=json.loads(c["relationships"] or "{}"), example_lines=c["example_lines"],
                          version=c["version"])

        npcs = [to_card(c) for c in chars if c["role"] == "npc"]
        heroes = [to_card(c) for c in chars if c["role"] == "hero"]
        seats = []
        for s in seats_of(db, room):
            if s["user"] is None:
                continue
            hero = heroes[s["index"]] if s["index"] < len(heroes) else None
            seats.append(P.Seat(nick=s["user"]["nick"], hero_name=s["hero_name"], hero=hero))
        params = [room["id"], room["summary_upto_seq"]]
        excl = ""
        if exclude_generation is not None:
            excl = " AND (generation_id IS NULL OR generation_id<>?)"
            params.append(exclude_generation)
        rows = db.all(
            f"SELECT * FROM messages WHERE room_id=? AND hidden=0 AND seq>? AND kind<>'system'{excl} ORDER BY seq DESC LIMIT ?",
            (*params, settings.ctx_recent_messages),
        )
        history = [P.HistoryItem(r["seq"], r["kind"], r["speaker_name"] or P.NARRATOR, r["text"]) for r in reversed(rows)]
        fparams = [room["id"]]
        fexcl = ""
        if exclude_generation is not None:
            fexcl = " AND (generation_id IS NULL OR generation_id<>?)"
            fparams.append(exclude_generation)
        facts = [r["text"] for r in reversed(db.all(
            f"SELECT text FROM scene_facts WHERE room_id=? AND hidden=0{fexcl} ORDER BY seq DESC, id DESC LIMIT 6", fparams))]
        inp = P.PromptInput(
            title=story["title"], description=story["description"], world_rules=story["world_rules"],
            location=room["scene_location"], npcs=npcs, seats=seats, summary=room["summary"], history=history,
            facts=facts, mode=mode, num_ctx=settings.llm_num_ctx, num_predict=settings.llm_num_predict,
        )
        return inp, npcs, seats

    async def _run_generation(self, job) -> None:
        db = self.db
        room = db.one("SELECT * FROM rooms WHERE id=?", (job["room_id"],))
        if room is None:
            return
        replaces = job["replaces_generation_id"]
        if job["kind"] == "regenerate":
            last_visible = db.one("SELECT generation_id FROM messages WHERE room_id=? AND hidden=0 ORDER BY seq DESC LIMIT 1",
                                  (room["id"],))
            if not last_visible or last_visible["generation_id"] != replaces:
                self._finish_failed(job, "Последний ответ уже изменился — перегенерация отменена.")
                return
        mode = "continue" if job["kind"] == "continue" else "reply"
        inp, npcs, seats = self._load_prompt_input(room, mode, replaces if job["kind"] == "regenerate" else None)
        built = P.build(inp)
        with db.tx():
            db.run("UPDATE generations SET status='running', started_at=?, model=?, prompt=?, card_versions=? WHERE id=?",
                   (now_ms(), settings.llm_model, built.text, P.card_versions_json(npcs, seats), job["id"]))
            _bump(db, room["id"])
        hub.partial_start(room["id"], job["public_id"])
        _notify_room(room["id"])
        npc_names = [c.name for c in npcs]
        hero_names = [s.hero_name for s in seats]
        recent = [r["text"] for r in db.all(
            "SELECT text FROM messages WHERE room_id=? AND hidden=0 ORDER BY seq DESC LIMIT 30", (room["id"],))]
        if job["kind"] == "regenerate" and replaces:
            recent = [r["text"] for r in db.all(
                "SELECT text FROM messages WHERE room_id=? AND hidden=0 AND (generation_id IS NULL OR generation_id<>?) "
                "ORDER BY seq DESC LIMIT 30", (room["id"], replaces))]
        parsed: list[P.ParsedLine] = []
        result = None
        # one automatic second attempt if the small model only repeated the scene or produced nothing usable
        for attempt in range(2):
            temperature = None if attempt == 0 else min(1.2, settings.llm_temperature + 0.3)
            try:
                result = await llm.chat(built.messages, stop=built.stop, temperature=temperature,
                                        on_delta=lambda piece: self._on_delta(room["id"], piece))
            except llm.LLMError as e:
                hub.partial_clear(room["id"])
                self._finish_failed(job, f"Модель не ответила: {e}")
                return
            except Exception as e:  # pragma: no cover
                hub.partial_clear(room["id"])
                log.exception("generation failed")
                self._finish_failed(job, f"Ошибка генерации: {type(e).__name__}")
                return
            parsed = P.parse_output(result.text, npc_names, hero_names, history=recent)
            if parsed:
                break
            hub.partial_start(room["id"], job["public_id"])
        hub.partial_clear(room["id"])
        if not parsed:
            self._finish_failed(job, "Модель вернула пустой ответ. Попробуй ещё раз.", raw=result.text, result=result)
            return
        if db.one("SELECT 1 FROM rooms WHERE id=?", (room["id"],)) is None:
            return
        name_to_char = {c.name: c.id for c in npcs}
        with db.tx():
            if job["kind"] == "regenerate" and replaces:
                rev = _bump(db, room["id"])
                db.run("UPDATE messages SET hidden=1, rev=? WHERE room_id=? AND generation_id=?", (rev, room["id"], replaces))
                db.run("UPDATE scene_facts SET hidden=1 WHERE room_id=? AND generation_id=?", (room["id"], replaces))
            for p in parsed:
                if p.kind == "narrator":
                    mid = _append(db, room["id"], "narrator", None, None, P.NARRATOR, p.text, generation_id=job["id"])
                else:
                    mid = _append(db, room["id"], "character", None, name_to_char.get(p.name), p.name, p.text,
                                  generation_id=job["id"])
                seq = db.one("SELECT seq FROM messages WHERE id=?", (mid,))["seq"]
                for f in P.extract_facts(p.name, p.text):
                    db.run("INSERT INTO scene_facts(room_id, message_id, generation_id, seq, text) VALUES(?,?,?,?,?)",
                           (room["id"], mid, job["id"], seq, f))
            db.run(
                "UPDATE generations SET status='done', finished_at=?, raw_output=?, prompt_tokens=?, output_tokens=?, "
                "prompt_ms=?, output_ms=?, total_ms=? WHERE id=?",
                (now_ms(), result.text, result.prompt_tokens, result.output_tokens, result.prompt_ms, result.output_ms,
                 result.total_ms, job["id"]),
            )
            _bump(db, room["id"])
            self._maybe_enqueue_summary(room["id"])
        _notify_room(room["id"])

    async def _on_delta(self, room_id: int, piece: str) -> None:
        hub.partial_add(room_id, piece)

    def _finish_failed(self, job, error: str, raw: str | None = None, result: llm.LLMResult | None = None) -> None:
        with self.db.tx():
            self.db.run("UPDATE generations SET status='failed', error=?, raw_output=?, finished_at=?, total_ms=? WHERE id=?",
                        (error[:500], raw, now_ms(), result.total_ms if result else None, job["id"]))
            _bump(self.db, job["room_id"])
        _notify_room(job["room_id"])

    # ------------------------------------------------------------------
    def _summary_range(self, room_id: int):
        room = self.db.one("SELECT * FROM rooms WHERE id=?", (room_id,))
        recent = self.db.all(
            "SELECT seq FROM messages WHERE room_id=? AND hidden=0 AND kind<>'system' ORDER BY seq DESC LIMIT ?",
            (room_id, settings.ctx_recent_messages),
        )
        if len(recent) < settings.ctx_recent_messages:
            return room, []
        boundary = recent[-1]["seq"]  # first message that stays verbatim
        old = self.db.all(
            "SELECT * FROM messages WHERE room_id=? AND hidden=0 AND kind<>'system' AND seq>? AND seq<? ORDER BY seq",
            (room_id, room["summary_upto_seq"], boundary),
        )
        return room, old

    def _maybe_enqueue_summary(self, room_id: int) -> None:
        _, old = self._summary_range(room_id)
        if len(old) >= settings.summary_batch:
            if not self.db.one("SELECT 1 FROM generations WHERE room_id=? AND kind='summary' AND status='queued'", (room_id,)):

                self.db.run(
                    "INSERT INTO generations(public_id, room_id, kind, status, created_at) VALUES(?,?, 'summary', 'queued', ?)",
                    (new_id(), room_id, now_ms()),
                )

    async def _run_summary(self, job) -> None:
        db = self.db
        room, old = self._summary_range(job["room_id"])
        if room is None or not old:
            with db.tx():
                db.run("UPDATE generations SET status='done', finished_at=? WHERE id=?", (now_ms(), job["id"]))
            return
        items = [P.HistoryItem(r["seq"], r["kind"], r["speaker_name"] or P.NARRATOR, r["text"]) for r in old]
        msgs = P.summary_messages(room["summary"], items, settings.summary_max_chars)
        with db.tx():
            db.run("UPDATE generations SET status='running', started_at=?, model=? WHERE id=?",
                   (now_ms(), settings.llm_model, job["id"]))
        error = None
        try:
            res = await llm.chat(msgs, num_predict=min(260, settings.llm_num_predict + 40))
            text = " ".join(res.text.replace("<|im_end|>", "").split())
            if len(text) < 20:
                raise llm.LLMError("слишком короткое резюме")
            summary = text[: settings.summary_max_chars]
        except Exception as e:  # fall back to an extractive summary so the context never overflows
            error = str(e)[:300]
            summary = P.fallback_summary(room["summary"], items, settings.summary_max_chars)
            res = None
        if db.one("SELECT 1 FROM rooms WHERE id=?", (room["id"],)) is None:
            return
        with db.tx():
            db.run("UPDATE rooms SET summary=?, summary_upto_seq=? WHERE id=?", (summary, old[-1]["seq"], room["id"]))
            db.run("UPDATE generations SET status='done', finished_at=?, raw_output=?, error=?, total_ms=? WHERE id=?",
                   (now_ms(), summary, error, res.total_ms if res else None, job["id"]))
