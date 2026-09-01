"""Anonymous nickname rules (spec 2-8). pick() is the only way to obtain a nick for a post/comment.

- New post: nick is pre-drawn into the session (preview) so the write box can show it, then fixed on save.
- Comment: same (post_id, user_id) -> same nick (post_nicks). Post author reuses the post nick.
- Never reused across posts; a nick is unique inside one post (re-draw on collision).
"""
import random

from flask import session

from ..db import execute, query, query_one

SESSION_KEY = "nick_preview"


class NickError(Exception):
    pass


def _words(kind):
    return [r["word"] for r in query("SELECT word FROM nick_words WHERE kind = %s", [kind])]


def draw():
    adjs, nouns = _words("adj"), _words("noun")
    if not adjs or not nouns:
        raise NickError("nick_words is empty — run scripts/seed.py")
    return f"{random.choice(adjs)} {random.choice(nouns)}"


def _taken_in_post(post_id):
    names = {r["nick"] for r in query("SELECT nick FROM post_nicks WHERE post_id = %s", [post_id])}
    p = query_one("SELECT anon_nick FROM posts WHERE id = %s", [post_id])
    if p:
        names.add(p["anon_nick"])
    return names


def pick(post_id, user_id):
    """Return the nick for user_id inside post_id, creating it if needed."""
    row = query_one("SELECT nick FROM post_nicks WHERE post_id = %s AND user_id = %s", [post_id, user_id])
    if row:
        return row["nick"]
    post = query_one("SELECT user_id, anon_nick FROM posts WHERE id = %s", [post_id])
    if post and post["user_id"] == user_id:
        nick = post["anon_nick"]
    else:
        taken = _taken_in_post(post_id)
        nick = draw()
        for _ in range(30):
            if nick not in taken:
                break
            nick = draw()
    execute("INSERT IGNORE INTO post_nicks (post_id, user_id, nick) VALUES (%s,%s,%s)", [post_id, user_id, nick])
    return nick


def _taken_in_media(media_id):
    return {r["nick"] for r in query("SELECT nick FROM media_nicks WHERE media_id = %s", [media_id])}


def pick_media(media_id, user_id):
    """Same rules as pick(), scoped to one media discussion thread (인기 트래픽)."""
    row = query_one("SELECT nick FROM media_nicks WHERE media_id = %s AND user_id = %s", [media_id, user_id])
    if row:
        return row["nick"]
    taken = _taken_in_media(media_id)
    nick = draw()
    for _ in range(30):
        if nick not in taken:
            break
        nick = draw()
    execute("INSERT IGNORE INTO media_nicks (media_id, user_id, nick) VALUES (%s,%s,%s)", [media_id, user_id, nick])
    return nick


def preview(board):
    """Nick shown in the write box; kept in session per board until the post is saved."""
    store = session.get(SESSION_KEY) or {}
    if board not in store:
        store[board] = draw()
        session[SESSION_KEY] = store
    return store[board]


def consume(board):
    store = session.get(SESSION_KEY) or {}
    nick = store.pop(board, None) or draw()
    session[SESSION_KEY] = store
    return nick


def register_post(post_id, user_id, nick):
    """After a post insert: fix the author's nick for that post."""
    execute("INSERT IGNORE INTO post_nicks (post_id, user_id, nick) VALUES (%s,%s,%s)", [post_id, user_id, nick])
