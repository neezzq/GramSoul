"""SQLite storage.

All database access happens on the asyncio event-loop thread and never spans an
``await``, so every write transaction is atomic and requests are applied in a
single, well-defined server order (this is what gives chat messages their
``seq``)."""
from __future__ import annotations

import os
import sqlite3
import time
from typing import Any, Iterable

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS meta(
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY,
  public_id TEXT NOT NULL UNIQUE,
  nick TEXT NOT NULL,
  nick_key TEXT NOT NULL UNIQUE,
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions(
  token_hash TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at INTEGER NOT NULL,
  last_seen_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS friend_requests(
  id INTEGER PRIMARY KEY,
  public_id TEXT NOT NULL UNIQUE,
  from_user INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  to_user INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  status TEXT NOT NULL CHECK(status IN ('pending','accepted','declined')),
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  UNIQUE(from_user, to_user)
);

CREATE TABLE IF NOT EXISTS images(
  id TEXT PRIMARY KEY,
  owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  mime TEXT NOT NULL,
  size INTEGER NOT NULL,
  width INTEGER NOT NULL,
  height INTEGER NOT NULL,
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS stories(
  id INTEGER PRIMARY KEY,
  public_id TEXT NOT NULL UNIQUE,
  owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  intro TEXT NOT NULL DEFAULT '',
  world_rules TEXT NOT NULL DEFAULT '',
  start_scene TEXT NOT NULL DEFAULT '',
  cover_image_id TEXT REFERENCES images(id) ON DELETE SET NULL,
  is_demo INTEGER NOT NULL DEFAULT 0,
  version INTEGER NOT NULL DEFAULT 1,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS characters(
  id INTEGER PRIMARY KEY,
  public_id TEXT NOT NULL UNIQUE,
  story_id INTEGER NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
  position INTEGER NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('npc','hero')),
  name TEXT NOT NULL,
  avatar_image_id TEXT REFERENCES images(id) ON DELETE SET NULL,
  age TEXT NOT NULL DEFAULT '',
  appearance TEXT NOT NULL DEFAULT '',
  habits TEXT NOT NULL DEFAULT '',
  personality TEXT NOT NULL DEFAULT '',
  motivation TEXT NOT NULL DEFAULT '',
  backstory TEXT NOT NULL DEFAULT '',
  speech_style TEXT NOT NULL DEFAULT '',
  relationships TEXT NOT NULL DEFAULT '{}',
  example_lines TEXT NOT NULL DEFAULT '',
  version INTEGER NOT NULL DEFAULT 1,
  updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS start_messages(
  id INTEGER PRIMARY KEY,
  story_id INTEGER NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
  position INTEGER NOT NULL,
  speaker_kind TEXT NOT NULL CHECK(speaker_kind IN ('narrator','character')),
  character_id INTEGER REFERENCES characters(id) ON DELETE CASCADE,
  text TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rooms(
  id INTEGER PRIMARY KEY,
  public_id TEXT NOT NULL UNIQUE,
  kind TEXT NOT NULL DEFAULT 'story' CHECK(kind IN ('story','chat','group')),
  story_id INTEGER REFERENCES stories(id) ON DELETE CASCADE,
  owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  guest_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
  title TEXT NOT NULL DEFAULT '',
  setting TEXT NOT NULL DEFAULT '',
  rev INTEGER NOT NULL DEFAULT 0,
  meta_rev INTEGER NOT NULL DEFAULT 0,
  next_seq INTEGER NOT NULL DEFAULT 1,
  scene_location TEXT NOT NULL DEFAULT '',
  summary TEXT NOT NULL DEFAULT '',
  summary_upto_seq INTEGER NOT NULL DEFAULT 0,
  ai_mode TEXT NOT NULL DEFAULT 'local',
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS room_invites(
  id INTEGER PRIMARY KEY,
  public_id TEXT NOT NULL UNIQUE,
  room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
  from_user INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  to_user INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  status TEXT NOT NULL CHECK(status IN ('pending','accepted','declined','cancelled')),
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  UNIQUE(room_id, to_user)
);

CREATE TABLE IF NOT EXISTS generations(
  id INTEGER PRIMARY KEY,
  public_id TEXT NOT NULL UNIQUE,
  room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
  kind TEXT NOT NULL CHECK(kind IN ('reply','continue','regenerate','summary')),
  status TEXT NOT NULL CHECK(status IN ('queued','running','done','failed','cancelled')),
  requested_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
  client_id TEXT,
  replaces_generation_id INTEGER REFERENCES generations(id) ON DELETE SET NULL,
  not_before_ms INTEGER NOT NULL DEFAULT 0,
  error TEXT,
  model TEXT,
  prompt TEXT,
  card_versions TEXT,
  raw_output TEXT,
  prompt_tokens INTEGER,
  output_tokens INTEGER,
  prompt_ms INTEGER,
  output_ms INTEGER,
  total_ms INTEGER,
  created_at INTEGER NOT NULL,
  started_at INTEGER,
  finished_at INTEGER,
  UNIQUE(room_id, requested_by, client_id)
);
CREATE INDEX IF NOT EXISTS generations_queue ON generations(status, id);

CREATE TABLE IF NOT EXISTS messages(
  id INTEGER PRIMARY KEY,
  public_id TEXT NOT NULL UNIQUE,
  room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
  seq INTEGER NOT NULL,
  rev INTEGER NOT NULL,
  kind TEXT NOT NULL CHECK(kind IN ('player','character','narrator','system')),
  user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
  character_id INTEGER REFERENCES characters(id) ON DELETE SET NULL,
  speaker_name TEXT NOT NULL DEFAULT '',
  text TEXT NOT NULL,
  client_id TEXT,
  generation_id INTEGER REFERENCES generations(id) ON DELETE SET NULL,
  hidden INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL,
  UNIQUE(room_id, seq),
  UNIQUE(room_id, user_id, client_id)
);
CREATE INDEX IF NOT EXISTS messages_rev ON messages(room_id, rev);

CREATE TABLE IF NOT EXISTS scene_facts(
  id INTEGER PRIMARY KEY,
  room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
  message_id INTEGER REFERENCES messages(id) ON DELETE CASCADE,
  generation_id INTEGER REFERENCES generations(id) ON DELETE CASCADE,
  seq INTEGER NOT NULL,
  text TEXT NOT NULL,
  hidden INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS scene_facts_room ON scene_facts(room_id, hidden, seq);

CREATE TABLE IF NOT EXISTS image_jobs(
  id INTEGER PRIMARY KEY,
  public_id TEXT NOT NULL UNIQUE,
  room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
  requested_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
  client_id TEXT,
  user_prompt TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL CHECK(status IN ('queued','running','done','failed')),
  error TEXT,
  model TEXT,
  prompt TEXT,
  image_id TEXT REFERENCES images(id) ON DELETE SET NULL,
  created_at INTEGER NOT NULL,
  finished_at INTEGER,
  UNIQUE(room_id, requested_by, client_id)
);
CREATE INDEX IF NOT EXISTS image_jobs_queue ON image_jobs(status, id);
CREATE TABLE IF NOT EXISTS transfer_codes(
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  code_hash TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,
  used_at INTEGER,
  attempts INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS transfer_codes_user ON transfer_codes(user_id);
CREATE TABLE IF NOT EXISTS personas(
  id INTEGER PRIMARY KEY,
  public_id TEXT NOT NULL UNIQUE,
  author_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL DEFAULT '',
  avatar_image_id TEXT REFERENCES images(id) ON DELETE SET NULL,
  first_message TEXT NOT NULL DEFAULT '',
  description TEXT NOT NULL DEFAULT '',
  backstory TEXT NOT NULL DEFAULT '',
  personality TEXT NOT NULL DEFAULT '',
  tags TEXT NOT NULL DEFAULT '[]',
  visibility TEXT NOT NULL DEFAULT 'private' CHECK(visibility IN ('public','private')),
  status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','published')),
  is_demo INTEGER NOT NULL DEFAULT 0,
  version INTEGER NOT NULL DEFAULT 1,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS personas_author ON personas(author_id);
CREATE TABLE IF NOT EXISTS room_personas(
  room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
  persona_id INTEGER NOT NULL REFERENCES personas(id) ON DELETE CASCADE,
  position INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY(room_id, persona_id)
);
CREATE INDEX IF NOT EXISTS room_personas_persona ON room_personas(persona_id);
CREATE TABLE IF NOT EXISTS usage_events(
  id INTEGER PRIMARY KEY,
  user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
  kind TEXT NOT NULL,           -- text | avatar | photo
  model TEXT,
  prompt_tokens INTEGER NOT NULL DEFAULT 0,
  completion_tokens INTEGER NOT NULL DEFAULT 0,
  cost REAL NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS usage_user ON usage_events(user_id, kind);
CREATE TABLE IF NOT EXISTS admin_sessions(
  token_hash TEXT PRIMARY KEY,
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL
);
"""

# columns added after the first release (ALTER TABLE keeps existing data)
MIGRATIONS = [
    ("rooms", "ai_mode", "ALTER TABLE rooms ADD COLUMN ai_mode TEXT NOT NULL DEFAULT 'local'"),
    ("messages", "image_id", "ALTER TABLE messages ADD COLUMN image_id TEXT"),
    ("generations", "provider", "ALTER TABLE generations ADD COLUMN provider TEXT"),
    ("users", "avatar_image_id", "ALTER TABLE users ADD COLUMN avatar_image_id TEXT REFERENCES images(id) ON DELETE SET NULL"),
    ("users", "about", "ALTER TABLE users ADD COLUMN about TEXT NOT NULL DEFAULT ''"),
    ("messages", "persona_id", "ALTER TABLE messages ADD COLUMN persona_id INTEGER REFERENCES personas(id) ON DELETE SET NULL"),
    ("messages", "edited_at", "ALTER TABLE messages ADD COLUMN edited_at INTEGER"),
    ("users", "password_hash", "ALTER TABLE users ADD COLUMN password_hash TEXT"),
    # what an image is for: '' (avatars, covers, AI pictures) or 'chat' (a player's own photo, kept 7 days)
    ("images", "purpose", "ALTER TABLE images ADD COLUMN purpose TEXT NOT NULL DEFAULT ''"),
    ("images", "expires_at", "ALTER TABLE images ADD COLUMN expires_at INTEGER"),
]


def _rooms_table_sql(name: str) -> str:
    start = SCHEMA.index("CREATE TABLE IF NOT EXISTS rooms(")
    end = SCHEMA.index(");", start) + 2
    return SCHEMA[start:end].replace("CREATE TABLE IF NOT EXISTS rooms(", f"CREATE TABLE {name}(")


def _rebuild_rooms_if_needed(conn: sqlite3.Connection) -> bool:
    """Rooms of the first releases had story_id NOT NULL; personal chats have no story.
    SQLite can not drop NOT NULL, so the table is rebuilt once (the documented 12-step way):
    foreign keys OFF (otherwise DROP TABLE would cascade-delete every message), copy, swap."""
    info = conn.execute("PRAGMA table_info(rooms)").fetchall()
    if not info or not any(r[1] == "story_id" and r[3] == 1 for r in info):
        return False
    conn.execute("PRAGMA foreign_keys=OFF")
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(_rooms_table_sql("rooms_v2"))
            old_cols = [r[1] for r in info]
            new_cols = [r[1] for r in conn.execute("PRAGMA table_info(rooms_v2)").fetchall()]
            common = ",".join(c for c in old_cols if c in new_cols)
            conn.execute(f"INSERT INTO rooms_v2({common}) SELECT {common} FROM rooms")
            conn.execute("DROP TABLE rooms")
            conn.execute("ALTER TABLE rooms_v2 RENAME TO rooms")
            if conn.execute("PRAGMA foreign_key_check").fetchall():
                raise RuntimeError("foreign key check failed after rebuilding rooms")
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.execute("PRAGMA foreign_keys=ON")
    return True


def now_ms() -> int:
    return int(time.time() * 1000)


class Database:
    def __init__(self, path: str):
        self.path = path
        if path != ":memory:":
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.conn = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA busy_timeout=5000")
        _rebuild_rooms_if_needed(self.conn)
        self.conn.executescript(SCHEMA)
        for table, column, sql in MIGRATIONS:
            cols = {r[1] for r in self.conn.execute(f"PRAGMA table_info({table})").fetchall()}
            if column not in cols:
                self.conn.execute(sql)

    # -- helpers -------------------------------------------------------
    def one(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
        return self.conn.execute(sql, tuple(params)).fetchone()

    def all(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        return self.conn.execute(sql, tuple(params)).fetchall()

    def run(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        return self.conn.execute(sql, tuple(params))

    def tx(self) -> "_Tx":
        return _Tx(self.conn)

    def close(self) -> None:
        self.conn.close()


class _Tx:
    """``with db.tx():`` — BEGIN IMMEDIATE … COMMIT/ROLLBACK."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def __enter__(self):
        self.conn.execute("BEGIN IMMEDIATE")
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.conn.execute("COMMIT")
        else:
            self.conn.execute("ROLLBACK")
        return False
