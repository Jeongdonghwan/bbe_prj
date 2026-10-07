"""국세청 사업자등록 상태조회 (공공데이터포털 15081808, 2026-10-07).

    POST https://api.odcloud.kr/api/nts-businessman/v1/status?serviceKey=<키>  {"b_no": ["2208162517"]}

키(.env DATA_GO_KR_KEY, 포털의 '일반 인증키(Decoding)')가 없거나 API 가 응답하지 않으면 None —
가입을 막지 않는다(체크섬은 이미 통과한 번호다). 국세청 장애로 가입이 멈추면 안 되기 때문.
"""
import json
import time
import urllib.parse
import urllib.request

from flask import current_app

URL = "https://api.odcloud.kr/api/nts-businessman/v1/status"
_CACHE = {}   # {b_no: (time, result)} — 같은 번호를 칸 이동·제출로 여러 번 묻는다
TTL = 3600

# b_stt_cd → (상태, 화면 문구, 가입 허용)
STATES = {"01": ("active", "계속사업자", True), "02": ("suspended", "휴업자", True), "03": ("closed", "폐업자", False)}


def status(b_no):
    """{'state': active|suspended|closed|unregistered, 'label': str, 'ok': bool} 또는 None(확인 불가)."""
    key = current_app.config.get("DATA_GO_KR_KEY")
    d = (b_no or "").replace("-", "")
    if not key or len(d) != 10:
        return None
    hit = _CACHE.get(d)
    if hit and time.time() - hit[0] < TTL:
        return hit[1]
    req = urllib.request.Request(f"{URL}?serviceKey={urllib.parse.quote(key, safe='')}",
                                 data=json.dumps({"b_no": [d]}).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            row = (json.load(r).get("data") or [{}])[0]
    except Exception as e:  # 네트워크·키 오류 — 확인 불가로 넘긴다
        current_app.logger.warning("국세청 상태조회 실패 %s: %s", d, e)
        return None
    st = STATES.get(row.get("b_stt_cd") or "")
    res = ({"state": st[0], "label": st[1], "ok": st[2]} if st
           else {"state": "unregistered", "label": "국세청에 등록되지 않은 번호", "ok": False})
    _CACHE[d] = (time.time(), res)
    return res
