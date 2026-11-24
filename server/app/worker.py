"""The single generation worker. Exactly one model call runs at a time for the
whole server; jobs wait in the ``generations`` table (status ``queued``)."""
from __future__ import annotations

import asyncio
import json
import logging
import time

from . import llm
from . import prompt as P
from .common import hub, new_id
from .config import settings
from .db import Database, now_ms
from .images import process_image, save_image
from .rooms import _append, _bump, _notify_room, room_personas, seats_of

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
        for r in self.db.all("SELECT id, room_id FROM image_jobs WHERE status='running'"):
            with self.db.tx():
                self.db.run("UPDATE image_jobs SET status='failed', error=?, finished_at=? WHERE id=?",
                            ("Сервер перезапускался — попробуй ещё раз.", now_ms(), r["id"]))
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
        return (self.db.one("SELECT COUNT(*) n FROM generations WHERE status IN ('queued','running')")["n"]
                + self.db.one("SELECT COUNT(*) n FROM image_jobs WHERE status IN ('queued','running')")["n"])

    # ------------------------------------------------------------------
    def _next_job(self):
        gen = self.db.one(
            "SELECT * FROM generations WHERE status='queued' ORDER BY (kind='summary'), id LIMIT 1"
        )
        img = self.db.one("SELECT * FROM image_jobs WHERE status='queued' ORDER BY id LIMIT 1")
        if img is not None and (gen is None or gen["kind"] == "summary" or img["created_at"] <= gen["created_at"]):
            return ("image", img)
        return ("gen", gen) if gen is not None else None

    async def _loop(self) -> None:
        while True:
            try:
                picked = self._next_job()
                if picked is None:
                    self._wake.clear()
                    try:
                        await asyncio.wait_for(self._wake.wait(), timeout=30)
                    except asyncio.TimeoutError:
                        pass
                    continue
                what, job = picked
                if what == "image":
                    self.busy = True
                    try:
                        await self._run_image(job)
                    finally:
                        self.busy = False
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
    @staticmethod
    def _limits(room) -> dict:
        if room["ai_mode"] == "cloud":
            return {"provider": "cloud", "model": settings.cloud_text_model, "num_ctx": settings.cloud_ctx_tokens,
                    "num_predict": settings.cloud_max_tokens, "recent": settings.cloud_recent_messages, "rich": True}
        return {"provider": "local", "model": settings.llm_model, "num_ctx": settings.llm_num_ctx,
                "num_predict": settings.llm_num_predict, "recent": settings.ctx_recent_messages, "rich": False}

    def _load_prompt_input(self, room, mode: str, exclude_generation: int | None) -> tuple[P.PromptInput, list[P.Card], list[P.Seat]]:
        db = self.db
        lim = self._limits(room)
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
            f"SELECT * FROM messages WHERE room_id=? AND hidden=0 AND seq>? AND kind<>'system' AND image_id IS NULL{excl} "
            "ORDER BY seq DESC LIMIT ?",
            (*params, lim["recent"]),
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
            facts=facts, mode=mode, num_ctx=lim["num_ctx"], num_predict=lim["num_predict"], rich=lim["rich"],
        )
        return inp, npcs, seats

    def _history(self, room, limit: int, exclude_generation: int | None) -> list[P.HistoryItem]:
        params = [room["id"], room["summary_upto_seq"]]
        excl = ""
        if exclude_generation is not None:
            excl = " AND (generation_id IS NULL OR generation_id<>?)"
            params.append(exclude_generation)
        rows = self.db.all(
            f"SELECT * FROM messages WHERE room_id=? AND hidden=0 AND seq>? AND kind<>'system' AND image_id IS NULL{excl} "
            "ORDER BY seq DESC LIMIT ?", (*params, limit))
        return [P.HistoryItem(r["seq"], r["kind"], r["speaker_name"] or P.NARRATOR, r["text"]) for r in reversed(rows)]

    def _load_chat_input(self, room, mode: str, exclude_generation: int | None):
        lim = self._limits(room)
        ps = room_personas(self.db, room)
        if not ps:
            return None, None
        p = ps[0]
        owner = self.db.one("SELECT nick FROM users WHERE id=?", (room["owner_id"],))
        inp = P.ChatPromptInput(
            name=p["name"] or "Персонаж", description=p["description"], personality=p["personality"],
            backstory=p["backstory"], user_name=owner["nick"] if owner else "Игрок", setting=room["setting"],
            summary=room["summary"], history=self._history(room, lim["recent"], exclude_generation), mode=mode,
            num_ctx=lim["num_ctx"], num_predict=lim["num_predict"], rich=lim["rich"],
        )
        return inp, p

    async def _run_generation(self, job) -> None:
        db = self.db
        room = db.one("SELECT * FROM rooms WHERE id=?", (job["room_id"],))
        if room is None:
            return
        replaces = job["replaces_generation_id"]
        if job["kind"] == "regenerate":
            last_visible = db.one("SELECT generation_id FROM messages WHERE room_id=? AND hidden=0 AND image_id IS NULL "
                                  "AND kind<>'system' ORDER BY seq DESC LIMIT 1", (room["id"],))
            if not last_visible or last_visible["generation_id"] != replaces:
                self._finish_failed(job, "Последний ответ уже изменился — перегенерация отменена.")
                return
        mode = "continue" if job["kind"] == "continue" else "reply"
        exclude = replaces if job["kind"] == "regenerate" else None
        chat = room["kind"] == "chat"
        persona = None
        if chat:
            inp, persona = self._load_chat_input(room, mode, exclude)
            if inp is None:
                self._finish_failed(job, "Персонаж этого чата удалён автором.")
                return
            built = P.build_chat(inp)
            npcs, seats = [], []
            versions = json.dumps({persona["public_id"]: persona["version"]})
        else:
            inp, npcs, seats = self._load_prompt_input(room, mode, exclude)
            built = P.build(inp)
            versions = P.card_versions_json(npcs, seats)
        lim = self._limits(room)
        provider = lim["provider"]
        with db.tx():
            db.run("UPDATE generations SET status='running', started_at=?, model=?, provider=?, prompt=?, card_versions=? WHERE id=?",
                   (now_ms(), lim["model"], provider, built.text, versions, job["id"]))
            _bump(db, room["id"])
        hub.partial_start(room["id"], job["public_id"])
        _notify_room(room["id"])
        npc_names = [c.name for c in npcs]
        hero_names = [inp.user_name] if chat else [s.hero_name for s in seats]
        recent = [r["text"] for r in db.all(
            "SELECT text FROM messages WHERE room_id=? AND hidden=0 ORDER BY seq DESC LIMIT 30", (room["id"],))]
        if job["kind"] == "regenerate" and replaces:
            recent = [r["text"] for r in db.all(
                "SELECT text FROM messages WHERE room_id=? AND hidden=0 AND (generation_id IS NULL OR generation_id<>?) "
                "ORDER BY seq DESC LIMIT 30", (room["id"], replaces))]
        # the scene-state/instruction turn is also "already said": an echo of it is not a reaction
        if not chat:
            recent = recent + [l for l in built.messages[-1]["content"].splitlines() if l.strip()]
        parsed: list[P.ParsedLine] = []
        result = None
        # one automatic second attempt if the small model only repeated the scene or produced nothing usable
        # Small models sometimes answer for a player's hero or copy an earlier line. Such output is
        # dropped by the parser; then we try again: narrator prefill, a "do not repeat" nudge and a
        # repeat penalty over the whole context. At most 3 attempts and ~2 minutes in total.
        t_start = time.monotonic()
        for attempt in range(3):
            if attempt and time.monotonic() - t_start > 120:
                break
            base_t = settings.cloud_temperature if provider == "cloud" else settings.llm_temperature
            temperature = None if attempt == 0 else min(1.2, base_t + 0.2 * attempt)
            messages = [dict(m) for m in built.messages]
            extra = None
            prefill = ""
            if attempt:
                messages[-1]["content"] += "\nНе повторяй уже сказанное — придумай новую реакцию, новые детали и действия."
                if provider == "local" and not chat:  # assistant prefill is reliable only with the local model
                    prefill = P.NARRATOR + ":"
                    messages.append({"role": "assistant", "content": prefill})
                    extra = {"repeat_last_n": -1, "repeat_penalty": max(settings.llm_repeat_penalty, 1.2)}
                hub.partial_start(room["id"], job["public_id"])
                hub.partial_add(room["id"], prefill + " ")
            try:
                result = await llm.chat(messages, stop=built.stop, temperature=temperature, extra_options=extra,
                                        num_predict=lim["num_predict"], provider=provider,
                                        on_delta=lambda piece: self._on_delta(room["id"], piece))
                if prefill:
                    result.text = prefill + " " + result.text.lstrip()
            except llm.LLMError as e:
                hub.partial_clear(room["id"])
                self._finish_failed(job, f"Модель не ответила: {e}")
                return
            except Exception as e:  # pragma: no cover
                hub.partial_clear(room["id"])
                log.exception("generation failed")
                self._finish_failed(job, f"Ошибка генерации: {type(e).__name__}")
                return
            if chat:
                parsed = P.parse_chat_output(result.text, inp.name, hero_names, history=recent)
            else:
                parsed = P.parse_output(result.text, npc_names, hero_names, history=recent, facts=inp.facts)
            if parsed:
                break
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
                if chat:
                    _append(db, room["id"], "character", None, None, p.name, p.text, generation_id=job["id"],
                            persona_id=persona["id"])
                    continue
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

    # ------------------------------------------------------------------
    async def _run_image(self, job) -> None:
        db = self.db
        room = db.one("SELECT * FROM rooms WHERE id=?", (job["room_id"],))
        if room is None:
            return
        if room["story_id"] is None:
            cinp, persona = self._load_chat_input(room, "reply", None)
            in_frame = [P.Card(id=persona["id"], public_id=persona["public_id"], role="npc", name=persona["name"],
                               appearance=persona["description"])] if persona else []
            prompt = P.image_prompt(room["title"], room["setting"], room["scene_location"], in_frame,
                                    cinp.history if cinp else [], job["user_prompt"])
        else:
            story = db.one("SELECT * FROM stories WHERE id=?", (room["story_id"],))
            inp, npcs, seats = self._load_prompt_input(room, "reply", None)
            present = set(P.present_names(inp))
            in_frame = [c for c in npcs if c.name in present] + [s.hero for s in seats if s.hero]
            prompt = P.image_prompt(story["title"], story["world_rules"], room["scene_location"], in_frame,
                                    inp.history, job["user_prompt"])
        with db.tx():
            db.run("UPDATE image_jobs SET status='running', model=?, prompt=? WHERE id=?",
                   (settings.cloud_image_model, prompt, job["id"]))
            _bump(db, room["id"])
        _notify_room(room["id"])
        try:
            raw = await llm.generate_image(prompt)
            data, w, h = await asyncio.to_thread(process_image, raw, 1280)
        except llm.LLMError as e:
            self._finish_image_failed(job, str(e))
            return
        except Exception as e:
            log.exception("image generation failed")
            self._finish_image_failed(job, f"Не удалось получить картинку: {type(e).__name__}")
            return
        if db.one("SELECT 1 FROM rooms WHERE id=?", (room["id"],)) is None:
            return
        with db.tx():
            iid = save_image(db, job["requested_by"], data, w, h)
            caption = job["user_prompt"].strip() or "Фото сцены"
            _append(db, room["id"], "narrator", None, None, "Фото", caption, image_id=iid)
            db.run("UPDATE image_jobs SET status='done', image_id=?, finished_at=? WHERE id=?", (iid, now_ms(), job["id"]))
            _bump(db, room["id"])
        _notify_room(room["id"])

    def _finish_image_failed(self, job, error: str) -> None:
        with self.db.tx():
            self.db.run("UPDATE image_jobs SET status='failed', error=?, finished_at=? WHERE id=?",
                        (error[:300], now_ms(), job["id"]))
            _bump(self.db, job["room_id"])
        _notify_room(job["room_id"])

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
        if room is None:
            return None, []
        keep = self._limits(room)["recent"]
        recent = self.db.all(
            "SELECT seq FROM messages WHERE room_id=? AND hidden=0 AND kind<>'system' AND image_id IS NULL "
            "ORDER BY seq DESC LIMIT ?",
            (room_id, keep),
        )
        if len(recent) < keep:
            return room, []
        boundary = recent[-1]["seq"]  # first message that stays verbatim
        old = self.db.all(
            "SELECT * FROM messages WHERE room_id=? AND hidden=0 AND kind<>'system' AND image_id IS NULL AND seq>? AND seq<? "
            "ORDER BY seq",
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
            lim = self._limits(room)
            res = await llm.chat(msgs, num_predict=min(400, lim["num_predict"] + 40), provider=lim["provider"])
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
