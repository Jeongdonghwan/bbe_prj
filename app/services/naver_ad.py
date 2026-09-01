"""Naver Search Ad API client (keywordstool / RelKwdStat). Keys from .env; raises NaverAdError when unavailable."""
import base64
import hashlib
import hmac
import json
import time
import urllib.parse
import urllib.request

from flask import current_app

BASE = "https://api.searchad.naver.com"


class NaverAdError(Exception):
    pass


def configured():
    c = current_app.config
    return bool(c.get("NAVER_AD_ACCESS_LICENSE") and c.get("NAVER_AD_SECRET_KEY") and c.get("NAVER_AD_CUSTOMER_ID"))


def _headers(method, uri):
    c = current_app.config
    ts = str(int(time.time() * 1000))
    msg = f"{ts}.{method}.{uri}".encode()
    sig = base64.b64encode(hmac.new(c["NAVER_AD_SECRET_KEY"].encode(), msg, hashlib.sha256).digest()).decode()
    return {"X-Timestamp": ts, "X-API-KEY": c["NAVER_AD_ACCESS_LICENSE"], "X-Customer": str(c["NAVER_AD_CUSTOMER_ID"]),
            "X-Signature": sig, "Content-Type": "application/json; charset=UTF-8"}


def _count(v):
    """API returns ints or strings like '< 10'."""
    if isinstance(v, (int, float)):
        return int(v)
    try:
        return int(str(v).replace("<", "").replace(",", "").strip() or 0)
    except ValueError:
        return 0


def keyword_stats(hint_keywords):
    """hint_keywords: list[str] (max 5). Returns list of dicts {keyword, pc, mo, comp} — includes related keywords."""
    if not configured():
        raise NaverAdError("NAVER_AD_* keys are not configured")
    hints = ",".join(k.replace(" ", "") for k in hint_keywords if k.strip())[:200]
    uri = "/keywordstool"
    q = urllib.parse.urlencode({"hintKeywords": hints, "showDetail": 1})
    req = urllib.request.Request(f"{BASE}{uri}?{q}", headers=_headers("GET", uri), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise NaverAdError(f"HTTP {e.code}: {e.read().decode()[:200]}")
    except urllib.error.URLError as e:
        raise NaverAdError(f"network: {e.reason}")
    out = []
    for k in data.get("keywordList", []):
        out.append({"keyword": k.get("relKeyword", ""), "pc": _count(k.get("monthlyPcQcCnt")), "mo": _count(k.get("monthlyMobileQcCnt")),
                    "comp": k.get("compIdx") or None})
    return out
