"""Target URL validation per channel: whitelist + PC place URL -> mobile conversion."""
import re
from urllib.parse import urlparse

from ..constants import URL_WHITELIST


class URLError(Exception):
    pass


def _host_ok(host, channel):
    host = host.lower()
    return any(host == d or host.endswith("." + d) for d in URL_WHITELIST[channel])


def normalize(url, channel):
    url = (url or "").strip()
    if not url:
        raise URLError("링크를 입력해주세요.")
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    p = urlparse(url)
    if not p.netloc or not _host_ok(p.netloc, channel):
        allowed = ", ".join(URL_WHITELIST[channel][:3])
        raise URLError(f"허용되지 않는 링크입니다. ({allowed} 주소만 가능)")
    if channel == "place":
        return to_mobile_place(url, p)
    return url


def to_mobile_place(url, p=None):
    """place.naver.com/<type>/<id>... or map.naver.com/p/entry/place/<id> -> https://m.place.naver.com/<type>/<id>"""
    p = p or urlparse(url)
    host = p.netloc.lower()
    if host in ("place.naver.com", "pcmap.place.naver.com"):
        m = re.match(r"^/([a-z]+)/(\d+)", p.path)
        if m:
            return f"https://m.place.naver.com/{m.group(1)}/{m.group(2)}/home"
    if host == "map.naver.com":
        m = re.search(r"/place/(\d+)", p.path)
        if m:
            return f"https://m.place.naver.com/place/{m.group(1)}/home"
        raise URLError("지도 링크에서 업체 ID를 찾을 수 없습니다. 플레이스 페이지의 모바일 주소를 입력해주세요.")
    return url
