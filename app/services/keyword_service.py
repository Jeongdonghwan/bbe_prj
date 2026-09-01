"""Keyword data: Naver Search Ad API with 24h cache (keyword_cache / related_cache), dummy fallback without keys,
daily quota (keyword_query_log), AI setting-keyword suggestion, store-slot volume refresh."""
import hashlib
import re

from flask import current_app

from ..db import execute, query, query_one
from . import naver_ad

CACHE_HOURS = 24
QUOTA_ANON = 3
QUOTA_USER = 30
RELATED_MAX = 100
REGION_HINT = re.compile(r"(시|구|동|읍|면|군|역|로)$")

SUFFIXES = {"place": ["추천", "잘하는곳", "후기", "가격"], "store": ["추천", "인기", "가성비", "후기"], "coupang": ["추천", "인기", "로켓배송", "후기"]}


def _norm(k):
    return " ".join((k or "").split())[:60]


def _key(k):
    return _norm(k).replace(" ", "").lower()


# ---- dummy (no API key) ------------------------------------------------------
def _dummy(keyword):
    h = int(hashlib.md5(_key(keyword).encode("utf-8")).hexdigest()[:8], 16)
    total = 3_000 + h % 120_000
    pc = int(total * (0.15 + (h % 20) / 100))
    comp = ["낮음", "중간", "높음"][h % 3]
    return {"keyword": _norm(keyword), "pc": pc, "mo": total - pc, "comp": comp}


def _dummy_related(seed, n=40):
    seed = _norm(seed)
    words = seed.split(" ")
    cands = [seed] + [f"{seed} {s}" for s in ["추천", "가격", "후기", "잘하는곳", "예약", "위치", "순위", "비용", "할인", "인기"]]
    if len(words) >= 2:
        cands += [f"{words[-1]} {words[0]}", f"{words[0]}{words[-1]}", f"{words[0]} {words[-1]} 근처"] + [f"{words[0]} {words[-1]}{s}" for s in ["맛집", "전문", "잘하는"]]
    for w in ["근처", "주변", "베스트", "1위", "저렴한", "유명한", "24시", "야간", "주말", "당일"]:
        cands.append(f"{w} {seed}")
    seen, out = set(), []
    for c in cands:
        if _key(c) not in seen:
            seen.add(_key(c)); out.append(_dummy(c))
    return out[:n]


# ---- cache -------------------------------------------------------------------
def _cached_keyword(k):
    return query_one("SELECT * FROM keyword_cache WHERE keyword = %s AND fetched_at >= DATE_SUB(NOW(), INTERVAL %s HOUR)", [_key(k), CACHE_HOURS])


def _store_keyword(row):
    execute("""INSERT INTO keyword_cache (keyword, pc_cnt, mo_cnt, comp, fetched_at) VALUES (%s,%s,%s,%s,NOW())
               ON DUPLICATE KEY UPDATE pc_cnt = VALUES(pc_cnt), mo_cnt = VALUES(mo_cnt), comp = VALUES(comp), fetched_at = NOW()""",
            [_key(row["keyword"]), row["pc"], row["mo"], row["comp"]])


def _cached_related(seed):
    return query("SELECT keyword, pc_cnt AS pc, mo_cnt AS mo FROM related_cache WHERE seed = %s AND fetched_at >= DATE_SUB(NOW(), INTERVAL %s HOUR)",
                 [_key(seed), CACHE_HOURS])


def _store_related(seed, rows):
    execute("DELETE FROM related_cache WHERE seed = %s", [_key(seed)])
    for r in rows:
        execute("INSERT INTO related_cache (seed, keyword, pc_cnt, mo_cnt) VALUES (%s,%s,%s,%s)", [_key(seed), r["keyword"], r["pc"], r["mo"]])


# ---- public lookups -------------------------------------------------------------
def lookup(keywords):
    """Stats for up to 5 keywords. Returns (rows, source) where source in ('api','cache','dummy')."""
    keywords = [_norm(k) for k in keywords if _norm(k)][:5]
    rows, missing = {}, []
    for k in keywords:
        c = _cached_keyword(k)
        if c:
            rows[_key(k)] = {"keyword": k, "pc": c["pc_cnt"], "mo": c["mo_cnt"], "comp": c["comp"]}
        else:
            missing.append(k)
    source = "cache" if rows else None
    if missing:
        if naver_ad.configured():
            try:
                data = naver_ad.keyword_stats(missing)
                by = {_key(d["keyword"]): d for d in data}
                for k in missing:
                    d = by.get(_key(k)) or {"keyword": k, "pc": 0, "mo": 0, "comp": None}
                    d["keyword"] = k; rows[_key(k)] = d; _store_keyword(d)
                source = "api"
            except naver_ad.NaverAdError as e:
                current_app.logger.warning("naver api failed: %s", e)
                for k in missing:
                    rows[_key(k)] = _dummy(k)
                source = "dummy"
        else:
            for k in missing:
                rows[_key(k)] = _dummy(k)
            source = "dummy"
    out = [rows[_key(k)] for k in keywords]
    for r in out:
        r["total"] = r["pc"] + r["mo"]
    return out, source or "dummy"


def related(seed):
    """Up to 100 related keywords for one seed, sorted by total desc. Returns (rows, source)."""
    seed = _norm(seed)
    cached = _cached_related(seed)
    if cached:
        rows, source = [dict(r) for r in cached], "cache"
    elif naver_ad.configured():
        try:
            data = naver_ad.keyword_stats([seed])
            rows = [d for d in data if _key(d["keyword"]) != _key(seed)]
            source = "api"
        except naver_ad.NaverAdError as e:
            current_app.logger.warning("naver api failed: %s", e)
            rows, source = _dummy_related(seed), "dummy"
    else:
        rows, source = _dummy_related(seed), "dummy"
    for r in rows:
        r["total"] = r["pc"] + r["mo"]
    rows.sort(key=lambda r: -r["total"])
    rows = rows[:RELATED_MAX]
    if source == "api":
        _store_related(seed, rows)
    return rows, source


def search_volume(keyword):
    """(pc, mo) monthly volume for store slots. Uses lookup() (cache/API/dummy)."""
    rows, _ = lookup([keyword])
    return rows[0]["pc"], rows[0]["mo"]


def refresh_all_slots():
    """Nightly batch hook (P5): re-fetch every store slot's volume and recommended qty."""
    from ..constants import reco_qty
    from ..models import store_slot as slot_model
    n = 0
    for s in slot_model.list_all():
        pc, mo = search_volume(s["keyword"])
        slot_model.update_volume(s["id"], pc, mo, reco_qty(pc + mo))
        n += 1
    return n


# ---- AI setting keywords ------------------------------------------------------------
def _rule_based(main_keyword, channel="place", limit=5):
    kw = _norm(main_keyword)
    if not kw:
        return []
    words = kw.split(" ")
    out = [kw]
    suffixes = SUFFIXES.get(channel, SUFFIXES["coupang"])
    if len(words) >= 2:
        region, rest = words[0], " ".join(words[1:])
        out += [f"{region} {rest}{suffixes[0]}" if channel == "place" else f"{kw} {suffixes[0]}", f"{rest} {region}", f"{region} {rest} {suffixes[2]}", f"{region}{rest}"]
    for s in suffixes:
        cand = f"{kw} {s}"
        if cand not in out:
            out.append(cand)
    seen, res = set(), []
    for k in out:
        if k not in seen:
            seen.add(k); res.append(k)
    return res[:limit]


def suggest_setting_keywords(main_keyword, channel="place", limit=5):
    """Top related keywords from the API (region-containing first); rule-based fallback when no API / failure."""
    kw = _norm(main_keyword)
    if not kw:
        return []
    if not naver_ad.configured():
        return _rule_based(kw, channel, limit)
    try:
        rows, source = related(kw)
    except Exception:  # never break the create form
        return _rule_based(kw, channel, limit)
    if source == "dummy" or not rows:
        return _rule_based(kw, channel, limit)
    region = kw.split(" ")[0] if len(kw.split(" ")) >= 2 else None
    def score(r):
        has_region = bool(region and region in r["keyword"].replace(" ", ""))
        return (0 if has_region else 1, -r["total"])
    picked = [kw] + [r["keyword"] for r in sorted(rows, key=score) if _key(r["keyword"]) != _key(kw)]
    return picked[:limit]


# ---- quota -------------------------------------------------------------------
def quota(user, ip):
    """Flat per-user daily limit; keyword tools require login (2026-09-01 JDH)."""
    if not user:
        return {"limit": QUOTA_USER, "used": 0, "remaining": 0, "unlimited": False}
    used = query_one("SELECT COUNT(*) AS n FROM keyword_query_log WHERE user_id = %s AND created_at >= CURDATE()", [user["id"]])["n"]
    return {"limit": QUOTA_USER, "used": used, "remaining": max(0, QUOTA_USER - used), "unlimited": False}


def log_query(user, ip, tool, q):
    execute("INSERT INTO keyword_query_log (user_id, ip, tool, query) VALUES (%s,%s,%s,%s)", [user["id"] if user else None, ip or "-", tool, q[:300]])
