# 도메인 연결 — 셀프마이마케팅.kr (2026-09-30)

한글 도메인 **셀프마이마케팅.kr** 의 punycode 는 `xn--hz2ba848cszgbqko5fcyd.kr` 이다.
DNS·nginx·인증서·.env 어디든 이 punycode 를 쓴다 (브라우저 주소창만 한글로 보인다).

```
python -c "print('셀프마이마케팅.kr'.encode('idna').decode())"
```

서버: bbe (211.45.175.195, 카페24). 80·443 만 열려 있고, 80 은 다른 앱(ilioom)이
`default_server` 로 쥐고 있다. 우리 도메인 이름이 정확히 맞는 server 블록을 따로 두면
nginx 가 그쪽을 우선 고르므로 ilioom 은 건드리지 않는다. 앱은 여전히 waitress :8034.

## 1. DNS (등록기관 관리 화면 — 가비아/후이즈/카페24)

| 타입 | 호스트 | 값 | TTL |
|---|---|---|---|
| A | `@` | `211.45.175.195` | 600 |
| A | `www` | `211.45.175.195` | 600 |

확인 (PC 에서):
```
nslookup xn--hz2ba848cszgbqko5fcyd.kr
```
IP 가 211.45.175.195 로 나올 때까지 기다린다 (보통 몇 분, 최대 하루).

## 2. nginx 80 블록 (bbe 서버)

```bash
cd /root/bbe_prj/bbe_prj && git pull
sudo python3 deploy/install_site_nginx.py      # sites-available/mymarketing + sites-enabled 링크, nginx -t
sudo systemctl reload nginx
curl -sI -H 'Host: xn--hz2ba848cszgbqko5fcyd.kr' http://127.0.0.1/ | head -3   # HTTP/1.1 200
```
DNS 가 퍼진 뒤 브라우저에서 `http://셀프마이마케팅.kr` 이 열리면 통과.

## 3. 인증서 (Let's Encrypt)

```bash
sudo apt-get install -y certbot python3-certbot-nginx     # 이미 있으면 그대로
sudo certbot --nginx -d xn--hz2ba848cszgbqko5fcyd.kr -d www.xn--hz2ba848cszgbqko5fcyd.kr \
     --redirect --agree-tos -m jdhwan0227@gmail.com -n
sudo nginx -t && sudo systemctl reload nginx
```
certbot 이 `sites-available/mymarketing` 에 443 블록과 80→443 리다이렉트를 붙인다.
갱신은 certbot 이 심는 타이머가 알아서 한다 (`systemctl list-timers | grep certbot`).
**이 뒤로 `install_site_nginx.py` 는 인증서 설정이 든 파일을 덮어쓰지 않는다** — 80 블록을 고칠 일이
있으면 그 파일을 직접 고친다.

## 4. 앱 .env (인증서 뒤에)

```bash
cd /root/bbe_prj/bbe_prj
grep -q '^PUBLIC_URL=' .env && sed -i 's#^PUBLIC_URL=.*#PUBLIC_URL=https://xn--hz2ba848cszgbqko5fcyd.kr#' .env \
  || echo 'PUBLIC_URL=https://xn--hz2ba848cszgbqko5fcyd.kr' >> .env
bash scripts/deploy.sh
```
`PUBLIC_URL` 이 있으면 앱이 nginx 의 `X-Forwarded-Proto/Host` 를 믿고(ProxyFix), og:image 같은
절대 주소가 https 도메인으로 나가며 세션 쿠키에 `Secure` 가 붙는다.
**그래서 이 값을 넣은 뒤로는 `http://211.45.175.195:8034` 로 로그인이 안 된다** (쿠키가 https 전용).
도메인으로만 쓴다. 로컬 개발은 비워 둔다.

## 5. 확인

```bash
curl -sI https://xn--hz2ba848cszgbqko5fcyd.kr/ | head -3            # HTTP/2 200
curl -sI http://xn--hz2ba848cszgbqko5fcyd.kr/ | head -3             # 301 → https
curl -s -o /dev/null -w '%{http_code}\n' https://xn--hz2ba848cszgbqko5fcyd.kr/api/rank/callback -X POST   # 401 (토큰 없음 — 우리 앱이 받는다는 뜻)
```
마지막 줄이 401 이 아니라 ilioom 의 응답(404/HTML)이면 server_name 매칭이 안 된 것 — `nginx -T | grep -n server_name` 로 확인.

## 6. 순위 콜백을 도메인으로 (권장, 별도 작업)

지금 콜백은 `http://bbe-callback/bbe/rank-callback` + 순위 서버 `/etc/hosts` 우회다
(docs/RANK_INTEGRATION.md). 도메인이 생기면 우회 없이 받을 수 있다 — 우리 server 블록은
`/api/*` 를 가로채는 게 없다.

순위 서버(makwangbatch1, `~/r_prj`)에서:
```bash
sed -i 's#http://bbe-callback/bbe/rank-callback#https://xn--hz2ba848cszgbqko5fcyd.kr/api/rank/callback#' scripts/prod.env
grep NSR_PARTNER_CALLBACK_URL scripts/prod.env
sudo systemctl restart rankserver
```
다음 수집(쇼핑 11시·17시, 플레이스 14시) 뒤 bbe 로그에 `rank callback track=` 이 찍히면
`/etc/hosts` 의 `bbe-callback` 줄과 ilioom 쪽 `location = /bbe/rank-callback` 을 지워도 된다.
확인 전에는 둘 다 두는 게 안전하다.

## 나중에 같이 바꿀 것

- 카카오 로그인 열 때 `KAKAO_REDIRECT_URI=https://xn--hz2ba848cszgbqko5fcyd.kr/auth/kakao/callback`
  (카카오 개발자 콘솔의 Redirect URI 도 punycode 로 등록).
- 영문 도메인을 추가로 잡으면 `deploy/nginx-site.conf` 의 `server_name` 에 덧붙이고
  `certbot --nginx -d … --expand`.
