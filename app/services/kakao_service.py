"""Kakao OAuth helpers (urllib only, no extra dependency)."""
import json
import urllib.parse
import urllib.request

AUTH_URL = "https://kauth.kakao.com/oauth/authorize"
TOKEN_URL = "https://kauth.kakao.com/oauth/token"
ME_URL = "https://kapi.kakao.com/v2/user/me"


class KakaoError(Exception):
    pass


def authorize_url(rest_key, redirect_uri, state):
    q = urllib.parse.urlencode({
        "client_id": rest_key, "redirect_uri": redirect_uri, "response_type": "code", "state": state,
    })
    return f"{AUTH_URL}?{q}"


def _post(url, data, headers=None):
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, headers=headers or {}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise KakaoError(f"{url} -> {e.code} {e.read().decode()[:200]}")
    except urllib.error.URLError as e:
        raise KakaoError(f"{url} -> {e.reason}")


def exchange_code(rest_key, redirect_uri, code):
    data = {"grant_type": "authorization_code", "client_id": rest_key, "redirect_uri": redirect_uri, "code": code}
    tok = _post(TOKEN_URL, data, {"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"})
    if "access_token" not in tok:
        raise KakaoError(f"token error: {tok}")
    return tok["access_token"]


def fetch_me(access_token):
    """Returns (kakao_id:str, nickname:str|None)."""
    me = _post(ME_URL, {}, {"Authorization": f"Bearer {access_token}",
                            "Content-Type": "application/x-www-form-urlencoded;charset=utf-8"})
    if "id" not in me:
        raise KakaoError(f"me error: {me}")
    nick = (me.get("kakao_account", {}).get("profile") or {}).get("nickname") or me.get("properties", {}).get("nickname")
    return str(me["id"]), nick
