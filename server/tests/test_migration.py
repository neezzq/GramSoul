"""The one-time rebuild of `rooms` (story_id becomes nullable) must keep every row and every link."""
import importlib.util
import os
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _old_db_module(tmp):
    """db.py as released before personal chats (rooms.story_id NOT NULL), kept as a fixture."""
    path = os.path.join(ROOT, "tests", "fixtures", "db_v1.py")
    spec = importlib.util.spec_from_file_location("db_v1", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_rooms_rebuild_keeps_data_and_foreign_keys():
    tmp = tempfile.mkdtemp()
    dbfile = os.path.join(tmp, "x.sqlite3")
    old = _old_db_module(tmp).Database(dbfile)
    c = old.conn
    c.execute("INSERT INTO users(id, public_id, nick, nick_key, created_at) VALUES(1,'u1','Mira','mira',1),(2,'u2','Lev','lev',1)")
    c.execute("INSERT INTO stories(id, public_id, owner_id, title, created_at, updated_at) VALUES(1,'s1',1,'T',1,1)")
    c.execute("INSERT INTO characters(id, public_id, story_id, position, role, name, updated_at) VALUES(1,'c1',1,0,'npc','Ива',1)")
    c.execute("INSERT INTO rooms(id, public_id, story_id, owner_id, guest_id, rev, meta_rev, next_seq, scene_location, summary, "
              "ai_mode, created_at, updated_at) VALUES(1,'r1',1,1,2,7,3,4,'маяк','сводка','cloud',5,6)")
    c.execute("INSERT INTO generations(id, public_id, room_id, kind, status, created_at) VALUES(1,'g1',1,'reply','done',1)")
    c.execute("INSERT INTO messages(id, public_id, room_id, seq, rev, kind, user_id, character_id, speaker_name, text, generation_id, "
              "created_at) VALUES(1,'m1',1,1,1,'player',1,NULL,'Ян','привет',NULL,1),(2,'m2',1,2,2,'character',NULL,1,'Ива','*кивает*',1,1)")
    c.execute("INSERT INTO scene_facts(room_id, message_id, generation_id, seq, text) VALUES(1,2,1,2,'Ива — кивает')")
    c.execute("INSERT INTO room_invites(public_id, room_id, from_user, to_user, status, created_at, updated_at) VALUES('i1',1,1,2,'accepted',1,1)")
    c.execute("INSERT INTO image_jobs(public_id, room_id, requested_by, status, created_at) VALUES('j1',1,1,'done',1)")
    old.close()

    from app.db import Database
    db = Database(dbfile)
    info = {r[1]: r for r in db.conn.execute("PRAGMA table_info(rooms)")}
    assert info["story_id"][3] == 0 and {"kind", "title", "setting", "ai_mode"} <= set(info)
    r = db.one("SELECT * FROM rooms WHERE id=1")
    assert (r["public_id"], r["story_id"], r["guest_id"], r["rev"], r["meta_rev"], r["next_seq"], r["scene_location"],
            r["summary"], r["ai_mode"], r["kind"]) == ("r1", 1, 2, 7, 3, 4, "маяк", "сводка", "cloud", "story")
    for t, n in (("messages", 2), ("generations", 1), ("scene_facts", 1), ("room_invites", 1), ("image_jobs", 1)):
        assert db.one(f"SELECT COUNT(*) n FROM {t}")["n"] == n, t
    assert db.one("PRAGMA foreign_keys")[0] == 1
    assert db.conn.execute("PRAGMA foreign_key_check").fetchall() == []
    # a story-less room is now allowed, and cascades still work through the new table
    db.run("INSERT INTO rooms(public_id, kind, owner_id, title, created_at, updated_at) VALUES('r2','chat',1,'Ива',1,1)")
    db.run("DELETE FROM rooms WHERE id=1")
    for t in ("messages", "generations", "scene_facts", "room_invites", "image_jobs"):
        assert db.one(f"SELECT COUNT(*) n FROM {t}")["n"] == 0, t
    db.close()
    # opening again does not rebuild again
    from app.db import _rebuild_rooms_if_needed
    db = Database(dbfile)
    assert _rebuild_rooms_if_needed(db.conn) is False
    db.close()
