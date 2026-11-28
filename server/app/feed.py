"""The feed («Публикации»): posts with text and up to four pictures, likes, comments, following authors.

Posts are public to every signed-in player; only the author (or the admin) deletes them."""
from __future__ import annotations

import re

from pydantic import BaseModel, Field

from .common import ApiError, User, hub, new_id
from .db import Database, now_ms
from .looks import author_of

MAX_IMAGES = 4
PAGE = 20
_TAG = re.compile(r"#([\wА-Яа-яЁё]{2,30})")


class PostIn(BaseModel):
    text: str = Field(default="", max_length=2000)
    image_ids: list[str] = Field(default_factory=list, max_length=MAX_IMAGES)


class CommentIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


def _post_row(db: Database, pid: str):
    p = db.one("SELECT * FROM posts WHERE public_id=?", (pid,))
    if not p:
        raise ApiError(404, "not_found", "Публикация не найдена.")
    return p


def post_dict(db: Database, p, viewer: User, cache: dict | None = None) -> dict:
    cache = {} if cache is None else cache
    imgs = [r["image_id"] for r in db.all("SELECT image_id FROM post_images WHERE post_id=? ORDER BY position", (p["id"],))]
    likes = db.one("SELECT COUNT(*) n FROM post_likes WHERE post_id=?", (p["id"],))["n"]
    liked = db.one("SELECT 1 FROM post_likes WHERE post_id=? AND user_id=?", (p["id"], viewer.id)) is not None
    comments = db.one("SELECT COUNT(*) n FROM post_comments WHERE post_id=?", (p["id"],))["n"]
    following = p["author_id"] != viewer.id and db.one(
        "SELECT 1 FROM follows WHERE follower_id=? AND followee_id=?", (viewer.id, p["author_id"])) is not None
    return {"id": p["public_id"], "author": author_of(db, p["author_id"], cache), "text": p["text"], "images": imgs,
            "tags": sorted({t.lower() for t in _TAG.findall(p["text"])}), "likes": likes, "liked": liked,
            "comments": comments, "mine": p["author_id"] == viewer.id, "following": following, "created_at": p["created_at"]}


def list_posts(db: Database, viewer: User, tab: str = "all", before: str | None = None, user_pid: str | None = None,
               tag: str | None = None) -> dict:
    """tab: all (everyone, newest first), following (authors the player follows), user (one author)."""
    where, params = [], []
    if before:
        b = db.one("SELECT id FROM posts WHERE public_id=?", (before,))
        if b:
            where.append("p.id<?")
            params.append(b["id"])
    if tab == "following":
        where.append("p.author_id IN (SELECT followee_id FROM follows WHERE follower_id=?)")
        params.append(viewer.id)
    elif tab == "user":
        u = db.one("SELECT id FROM users WHERE public_id=?", (user_pid or "",))
        if not u:
            raise ApiError(404, "not_found", "Игрок не найден.")
        where.append("p.author_id=?")
        params.append(u["id"])
    if tag:
        where.append("lower(p.text) LIKE ?")
        params.append("%#" + tag.lower().lstrip("#")[:30].replace("%", "").replace("_", "") + "%")
    sql = "SELECT p.* FROM posts p" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY p.id DESC LIMIT ?"
    rows = db.all(sql, (*params, PAGE + 1))
    cache: dict = {}
    out = [post_dict(db, r, viewer, cache) for r in rows[:PAGE]]
    return {"posts": out, "next": out[-1]["id"] if len(rows) > PAGE else None}


def create_post(db: Database, user: User, body: PostIn) -> dict:
    text = body.text.strip()
    ids = list(dict.fromkeys(i for i in body.image_ids if i))
    if not text and not ids:
        raise ApiError(400, "empty", "Напиши что-нибудь или добавь картинку.")
    for iid in ids:
        img = db.one("SELECT owner_id FROM images WHERE id=?", (iid,))
        if not img or img["owner_id"] != user.id:
            raise ApiError(400, "bad_image", "Картинка не найдена. Загрузи её ещё раз.")
    with db.tx():
        pid = new_id()
        post_id = db.run("INSERT INTO posts(public_id, author_id, text, created_at) VALUES(?,?,?,?)",
                         (pid, user.id, text, now_ms())).lastrowid
        for pos, iid in enumerate(ids):
            db.run("INSERT INTO post_images(post_id, image_id, position) VALUES(?,?,?)", (post_id, iid, pos))
    hub.notify("feed")
    return post_dict(db, db.one("SELECT * FROM posts WHERE id=?", (post_id,)), user)


def delete_post(db: Database, post_row) -> None:
    from .images import delete_image_files, drop_unreferenced
    imgs = [r["image_id"] for r in db.all("SELECT image_id FROM post_images WHERE post_id=?", (post_row["id"],))]
    with db.tx():
        db.run("DELETE FROM posts WHERE id=?", (post_row["id"],))
        gone = drop_unreferenced(db, imgs)
    delete_image_files(gone)


def delete_own_post(db: Database, user: User, pid: str) -> None:
    p = _post_row(db, pid)
    if p["author_id"] != user.id:
        raise ApiError(403, "not_yours", "Удалить можно только свою публикацию.")
    delete_post(db, p)


def set_like(db: Database, user: User, pid: str, on: bool) -> dict:
    p = _post_row(db, pid)
    if on:
        db.run("INSERT OR IGNORE INTO post_likes(post_id, user_id, created_at) VALUES(?,?,?)", (p["id"], user.id, now_ms()))
    else:
        db.run("DELETE FROM post_likes WHERE post_id=? AND user_id=?", (p["id"], user.id))
    return post_dict(db, p, user)


def comment_dict(db: Database, c, viewer: User, post_author: int, cache: dict) -> dict:
    return {"id": c["public_id"], "author": author_of(db, c["author_id"], cache), "text": c["text"],
            "created_at": c["created_at"], "can_delete": c["author_id"] == viewer.id or post_author == viewer.id}


def list_comments(db: Database, user: User, pid: str) -> dict:
    p = _post_row(db, pid)
    cache: dict = {}
    rows = db.all("SELECT * FROM post_comments WHERE post_id=? ORDER BY id LIMIT 500", (p["id"],))
    return {"post": post_dict(db, p, user, cache), "comments": [comment_dict(db, c, user, p["author_id"], cache) for c in rows]}


def add_comment(db: Database, user: User, pid: str, body: CommentIn) -> dict:
    p = _post_row(db, pid)
    text = body.text.strip()
    if not text:
        raise ApiError(400, "empty", "Комментарий пустой.")
    cid = new_id()
    db.run("INSERT INTO post_comments(public_id, post_id, author_id, text, created_at) VALUES(?,?,?,?,?)",
           (cid, p["id"], user.id, text, now_ms()))
    return comment_dict(db, db.one("SELECT * FROM post_comments WHERE public_id=?", (cid,)), user, p["author_id"], {})


def delete_comment(db: Database, user: User, cid: str) -> None:
    c = db.one("SELECT c.*, p.author_id post_author FROM post_comments c JOIN posts p ON p.id=c.post_id WHERE c.public_id=?", (cid,))
    if not c:
        raise ApiError(404, "not_found", "Комментарий не найден.")
    if user.id not in (c["author_id"], c["post_author"]):
        raise ApiError(403, "not_yours", "Удалить можно свой комментарий или комментарий к своей публикации.")
    db.run("DELETE FROM post_comments WHERE id=?", (c["id"],))


def post_image_allowed(db: Database, pid: str, iid: str) -> bool:
    return db.one("SELECT 1 FROM post_images i JOIN posts p ON p.id=i.post_id WHERE p.public_id=? AND i.image_id=?",
                  (pid, iid)) is not None


def set_follow(db: Database, user: User, target_pid: str, on: bool) -> dict:
    t = db.one("SELECT id FROM users WHERE public_id=?", (target_pid,))
    if not t:
        raise ApiError(404, "not_found", "Игрок не найден.")
    if t["id"] == user.id:
        raise ApiError(400, "self_follow", "Нельзя подписаться на себя.")
    if on:
        db.run("INSERT OR IGNORE INTO follows(follower_id, followee_id, created_at) VALUES(?,?,?)", (user.id, t["id"], now_ms()))
    else:
        db.run("DELETE FROM follows WHERE follower_id=? AND followee_id=?", (user.id, t["id"]))
    return follow_counts(db, user, t["id"])


def follow_counts(db: Database, viewer: User, uid: int) -> dict:
    return {"followers": db.one("SELECT COUNT(*) n FROM follows WHERE followee_id=?", (uid,))["n"],
            "following_count": db.one("SELECT COUNT(*) n FROM follows WHERE follower_id=?", (uid,))["n"],
            "is_following": db.one("SELECT 1 FROM follows WHERE follower_id=? AND followee_id=?", (viewer.id, uid)) is not None,
            "posts": db.one("SELECT COUNT(*) n FROM posts WHERE author_id=?", (uid,))["n"]}


def admin_posts(db: Database) -> dict:
    rows = db.all("SELECT p.*, u.nick FROM posts p JOIN users u ON u.id=p.author_id ORDER BY p.id DESC LIMIT 300")
    return {"posts": [{"id": r["public_id"], "nick": r["nick"], "text": r["text"][:300], "created_at": r["created_at"],
                       "images": [x["image_id"] for x in db.all("SELECT image_id FROM post_images WHERE post_id=? ORDER BY position", (r["id"],))]}
                      for r in rows]}
