"""Rank server (partner API) client.

Best-effort only: every call returns a dict and never raises, so a slow or missing rank
server degrades the campaign wizard to plain manual entry instead of blocking it.
The token lives in .env (RANK_API_TOKEN) and must never reach the browser — the wizard
talks to our own proxy route, not to the rank server.
"""
import json
import urllib.error
import urllib.parse
import urllib.request

from flask import current_app

TIMEOUT = 5


def configured():
    c = current_app.config
    return bool(c.get("RANK_SERVER_URL") and c.get("RANK_API_TOKEN"))


def _get(path, params):
    """GET <RANK_SERVER_URL><path>?<params>. Returns the decoded body or None on any failure."""
    c = current_app.config
    url = c["RANK_SERVER_URL"].rstrip("/") + path + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"X-NSR-Token": c["RANK_API_TOKEN"], "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
        current_app.logger.info("rank_client %s failed: %s", path, e)
        return None


def product_preview(url):
    """Look up a product page: {"ok", "valid", "prodNm", "imageUrl", "mallName", ...}.

    ok=False means we could not ask (no token, timeout, rank server down) — the caller
    should stay silent. valid=False means the rank server read the URL and found no
    product number, which is worth telling the user about.
    """
    if not configured() or not (url or "").strip():
        return {"ok": False}
    body = _get("/partner/product/preview", {"url": url.strip()})
    if not isinstance(body, dict) or not body.get("ok"):
        return {"ok": False}
    return body
