"""Rank server (partner API) client — rank.mbizsquare.com /partner/*.

Best-effort only: every call returns a dict and never raises, so a slow or missing rank
server degrades to manual entry instead of blocking the app. The token lives in .env
(RANK_API_TOKEN = 순위 서버의 NSR_PARTNER_TOKEN) and must never reach the browser.

주의 — 파트너 슬롯은 순위 서버에서 `partner:bbe` 라는 **공용 계정 하나**를 쓴다.
트리플업(bbe_shop)이 같은 키워드·URL 을 이미 등록해 뒀으면 우리 등록은 그쪽 trackId 를
그대로 돌려받고(get-or-create), 우리가 DELETE 하면 그쪽 추적까지 끊긴다. 그래서 삭제는
기본으로 하지 않는다 (RANK_UNTRACK_ON_STOP, 기본 off).
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


def _call(method, path, params=None, body=None):
    """<RANK_SERVER_URL><path> 호출. 실패하면 None (예외를 밖으로 내보내지 않는다)."""
    c = current_app.config
    url = c["RANK_SERVER_URL"].rstrip("/") + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    headers = {"X-NSR-Token": c["RANK_API_TOKEN"], "Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:                                    # 400/401 은 본문에 한국어 사유가 들어 있다
            return json.loads(e.read().decode("utf-8"))
        except Exception:
            current_app.logger.info("rank_client %s %s HTTP %s", method, path, e.code)
            return None
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
        current_app.logger.info("rank_client %s %s failed: %s", method, path, e)
        return None


def product_preview(url):
    """상품 미리보기: {"ok", "valid", "source", "prodNm", "imageUrl", "mallName", "nvMid", ...}.

    ok=False 는 물어보지 못했다는 뜻(토큰 없음·타임아웃·서버 다운) — 조용히 넘어간다.
    valid=False 는 주소를 읽었는데 상품 번호가 없다는 뜻이라 사용자에게 알린다.
    """
    if not configured() or not (url or "").strip():
        return {"ok": False}
    body = _call("GET", "/partner/product/preview", params={"url": url.strip()})
    if not isinstance(body, dict) or not body.get("ok"):
        return {"ok": False}
    return body


def register_slot(keyword, url):
    """추적 등록(get-or-create): {"ok", "trackId", "status", "rank", "prodNm", "date"}.

    status 는 "collected"(오늘 수집 완료) 또는 "queued" 둘뿐이다. collected 면 rank 가
    바로 들어 있어 그 자리에서 기록할 수 있다. rank=None 은 300위 밖이거나 아직 미수집.
    """
    keyword = " ".join((keyword or "").split())[:100]
    url = (url or "").strip()
    if not configured() or not keyword or not url:
        return {"ok": False}
    body = _call("POST", "/partner/slots", body={"keyword": keyword, "url": url})
    if not isinstance(body, dict) or not body.get("ok") or not body.get("trackId"):
        if isinstance(body, dict) and body.get("message"):
            current_app.logger.info("rank_client register_slot rejected: %s", body["message"])
        return {"ok": False, "message": (body or {}).get("message")}
    return body


def slot_ranks(track_id):
    """{"ok", "trackId", "prodNm", "ranks": [{"date", "rank"}, ...]} — 최신 100일, 최신순."""
    if not configured() or not track_id:
        return {"ok": False, "ranks": []}
    body = _call("GET", f"/partner/slots/{int(track_id)}/ranks")
    if not isinstance(body, dict) or not body.get("ok"):
        return {"ok": False, "ranks": []}
    body.setdefault("ranks", [])
    return body


def untrack(track_id):
    """추적 중단. 공용 계정이라 다른 파트너 사이트의 추적도 함께 끊긴다 — 호출 전에 확인할 것."""
    if not configured() or not track_id:
        return {"ok": False}
    return _call("DELETE", f"/partner/slots/{int(track_id)}") or {"ok": False}
