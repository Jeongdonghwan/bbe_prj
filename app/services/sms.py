"""운영자 문자 알림 — 알리고(Aligo) https://apis.aligo.in/send/ (2026-10-07).

같은 서버(211.45.175.195)에 raws_prj 가 알리고를 `ALIGO_*` 환경변수로 쓰고 있다. 섞이지 않게
이 프로젝트는 **`MM_ALIGO_*` 이름만** 쓰고, os.environ 이 아니라 app.config(Config) 로만 읽는다.
코드도 공유하지 않는다.

    MM_ALIGO_USER_ID / MM_ALIGO_API_KEY  알리고 계정 (이 서비스용)
    MM_ALIGO_SENDER       알리고에 사전등록·승인된 발신번호
    MM_ALIGO_ADMIN_PHONES 받을 운영자 번호, 쉼표로 여러 개
    MM_ALIGO_TEST_MODE    Y 면 실제 발송·과금 없이 응답만 (설정 확인용)

발송 서버 IP 가 그 알리고 계정에 등록돼 있어야 한다(-101). 문자는 부가 기능이라 실패해도
예외를 올리지 않고 로그만 남기며, 요청을 붙잡지 않게 스레드로 보낸다.
"""
import json
import logging
import re
import threading
import urllib.parse
import urllib.request

from flask import current_app

log = logging.getLogger(__name__)
SEND_URL = "https://apis.aligo.in/send/"
HINTS = {-101: "발송 서버 IP 미등록", -102: "아이디/API 키 불일치", -103: "발신번호 미승인",
         -104: "잔여 건수 부족", -111: "수신번호 형식 오류", -201: "내용 오류"}


def _conf():
    c = current_app.config
    return {"user_id": c.get("MM_ALIGO_USER_ID", ""), "key": c.get("MM_ALIGO_API_KEY", ""),
            "sender": re.sub(r"\D", "", c.get("MM_ALIGO_SENDER", "")),
            "admins": [re.sub(r"\D", "", p) for p in (c.get("MM_ALIGO_ADMIN_PHONES", "")).split(",") if p.strip()],
            "test": (c.get("MM_ALIGO_TEST_MODE", "") or "").upper()}


def msg_type(text):
    """알리고는 CP949 90바이트까지 SMS, 넘으면 LMS(제목 필요)."""
    try:
        return "SMS" if len(text.encode("cp949")) <= 90 else "LMS"
    except UnicodeEncodeError:
        return "LMS"


def _send(c, receivers, msg):
    data = {"key": c["key"], "userid": c["user_id"], "sender": c["sender"],
            "receiver": ",".join(receivers), "msg": msg, "msg_type": msg_type(msg)}
    if data["msg_type"] == "LMS":
        data["title"] = msg.splitlines()[0][:40]
    if c["test"] == "Y":
        data["testmode_yn"] = "Y"
    try:
        req = urllib.request.Request(SEND_URL, data=urllib.parse.urlencode(data).encode())
        with urllib.request.urlopen(req, timeout=10) as r:
            out = json.load(r)
        code = int(out.get("result_code", -1))
    except Exception as e:
        log.warning("문자 발송 실패(요청): %s", e)
        return False
    if code > 0:
        log.info("문자 발송 %s건 type=%s msg_id=%s", len(receivers), data["msg_type"], out.get("msg_id"))
        return True
    log.error("문자 발송 거절 code=%s %s %s", code, out.get("message"), HINTS.get(code, ""))
    return False


def notify_admins(msg):
    """운영자 번호 전원에게 문자. 설정이 비어 있으면 조용히 건너뛴다."""
    c = _conf()
    if not (c["user_id"] and c["key"] and c["sender"] and c["admins"]):
        return False
    threading.Thread(target=_send, args=(c, c["admins"], msg), daemon=True).start()
    return True


if __name__ == "__main__":  # python -m app.services.sms — 길이 판정만 확인
    assert msg_type("[마이마케팅] 충전 요청 홍길동 100,000원") == "SMS"
    assert msg_type("가" * 46) == "LMS"
    print("sms ok")
