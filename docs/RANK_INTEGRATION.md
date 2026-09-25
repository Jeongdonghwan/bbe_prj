# 순위 서버(rankserver) 연동

bbe_prj ↔ `rank.mbizsquare.com` 파트너 API 연동 문서. 1단계(상품 미리보기)는 구현 완료,
2단계(캠페인 순위 자동 조회)는 아직 **계획만** 있고 코드가 없다.

같은 구조가 트리플업(`C:\bbe_shop_prj`)에서 이미 돌고 있으므로, 2단계는 새로 설계하지 말고
그쪽 구현을 그대로 이식한다.

## 공통

| 항목 | 값 |
| --- | --- |
| 베이스 URL | `.env` 의 `RANK_SERVER_URL` (기본 `https://rank.mbizsquare.com`) |
| 인증 | 요청 헤더 `X-NSR-Token: <RANK_API_TOKEN>` |
| 토큰 출처 | rankserver 의 `/var/www/tripleup/.env` 의 `RANK_API_TOKEN` 과 같은 값 |

토큰은 **절대 브라우저로 나가면 안 된다.** 프런트는 항상 우리 서버의 프록시 라우트를 부르고,
rankserver 호출은 `app/services/rank_client.py` 안에서만 한다. 코드에 하드코딩 금지.

`RANK_SERVER_URL` 이나 `RANK_API_TOKEN` 이 비어 있으면 연동 기능은 전부 조용히 꺼진다
(`rank_client.configured()`). 로컬 개발에서 토큰 없이도 화면이 정상 동작해야 한다.

## 1단계 — 상품 미리보기 (구현 완료, 2026-09-21)

**쇼핑·스토어 채널에만 적용한다** (2026-09-21 JDH). 쿠팡·플레이스는 순위 서버가 읽는
대상이 아니라서 미리보기 카드 자체를 렌더하지 않고, 주소 확인 칩(`.w-urlok`)만 보여준다.

캠페인 등록 1스텝에서 상품 URL을 넣으면 상품명·대표이미지·몰이름을 미리 보여주고,
상품명 칸이 비어 있으면 자동으로 채운다.

```
GET /partner/product/preview?url=<상품URL>     (rankserver)
→ {"ok":true, "valid":true|false, "prodNm":.., "imageUrl":.., "mallName":.., "nvMid":.., "catalogId":.., "note":..}
```

- `valid:false` = URL에서 상품 번호를 못 찾음 → 사용자에게 주소 확인 안내.
  `valid` 판정은 URL 경로에서 상품번호를 뽑은 결과라 **페이지 열람 성공 여부와 무관하다**
- 네이버 클릭 리다이렉트(`search.naver.com/p/crd/rd`)는 rankserver 가 알아서 풀어준다
- `source`: `"page"`(상품 페이지를 직접 읽음) · `"serp"`(일별 수집 캐시에서 찾음) · `null`(둘 다 실패)

### 상품명·이미지가 자주 비는 이유 (2026-09-21 확인)

네이버가 **데이터센터 IP의 상품 페이지 열람을 전면 차단(429)** 한다. rankserver·bbe 서버·외부
미리보기 서비스 모두 차단되고, 스크래퍼 UA 위장도 안 통한다 (네이버는 카카오톡·페이스북봇을
UA가 아니라 화이트리스트한 실제 서버 IP로 검증). 그래서 rankserver 는 페이지 조회가 실패하면
매일 수집하는 SERP(키워드별 300위)에서 nvMid·mall_product_id 로 상품명·몰이름을 찾아 돌려준다.

그 결과 UI가 반드시 감당해야 하는 상태:

- **`source:"serp"` 면 `imageUrl` 은 항상 `null`** (수집 항목에 썸네일이 없다) → 이미지 없이도
  카드가 성립해야 한다. 지금은 기본 아이콘으로 떨어진다
- **신규 상품은 SERP에도 없어 `source:null` + `prodNm` 없음이 흔하다** → 이때 "상품을
  확인했습니다"라고 하면 안 된다. `주소는 확인했습니다. 상품명은 직접 입력해주세요` 로 안내하고
  사용자가 직접 입력하게 둔다 (2단계 순위 연동을 붙이면 등록 후 자동 보정 예정)

구현 위치:

| 파일 | 역할 |
| --- | --- |
| `app/services/rank_client.py` | rankserver HTTP 호출. 타임아웃 5초, 어떤 실패도 예외 없이 `{"ok": false}` |
| `app/blueprints/campaign.py` `api_product_preview()` | 프록시 라우트 `GET /api/product/preview?url=` (로그인 필수), `product_api` 블루프린트 |
| `app/static/js/wizard.js` `lookup()` / `showLookup()` | 입력 후 600ms 디바운스 + blur 시 호출, URL별 1회 캐시 |
| `app/templates/campaign/new.html` `#preview` | 썸네일(`#pvImg`) · 상태줄(`#pvOk`) · 경고(`#pvWarn`). 스토어에서만 렌더 |
| `app/blueprints/campaign.py` `new()` | `preview_on`(문구·카드 노출) / `preview_live`(실제 호출 = 위 + 토큰 설정됨) |

동작 규칙 — **미리보기는 best-effort라 등록 흐름을 절대 막지 않는다.**

- `ok:false`(토큰 없음·타임아웃·서버 다운)이면 아무 말도 하지 않고 수동 입력 그대로 진행
- `valid:false` 면 빨간 안내만 띄우고, 다음 단계 이동은 막지 않는다 (URL 형식 검증은
  기존 `constants.URL_PATTERNS` 가 서버에서 따로 한다)
- 사용자가 이미 상품명을 입력했으면 절대 덮어쓰지 않는다
- `prodNm` 이 없으면 상품을 확인했다고 말하지 않는다 (위 "자주 비는 이유" 참고)
- 화면 문구("상품 URL을 넣으면 자동으로 채워집니다")는 `preview_on` 기준이라 토큰이 없어도
  노출되고, 실제 호출은 `preview_live`(= `WZ.preview`)가 참일 때만 일어난다

## 2단계 — 캠페인 순위 자동 조회 (구현 완료, 2026-09-24)

**쇼핑·스토어 채널만.** 파트너 API 는 `slotType=ST002`(쇼핑) 고정이라 플레이스·쿠팡은 대상이 아니다.

### 스키마

`campaigns.track_id INT NULL` + `campaigns.track_status VARCHAR(20) NULL` + `idx_campaigns_track`
(migrate 가 자동 반영). 순위 자체는 기존 `campaign_daily(date, rank, done_qty)` 에 그대로 쌓는다 —
어드민 수동 입력과 같은 자리라 화면을 새로 만들 필요가 없다.

### 슬롯 등록

`campaign_service.transition()` 이 `approved` / `running` 으로 갈 때 `spawn_track()` 을 부른다.

```
POST /partner/slots   {"keyword": ..., "url": ...}
→ {"ok", "trackId", "status", "rank", "prodNm", "date"}
```

- `status` 는 **`"collected"` 또는 `"queued"` 둘뿐**이다 (`pending` 같은 값은 오지 않는다).
- `collected` 면 `rank` 가 그 자리에 들어 있어 바로 기록한다. `rank: null` 은 300위 밖.
- 실패해도 상태 전이는 그대로 진행한다. 누락분은 `scripts/cron.py hourly` 가 줍는다.
- 이미 `track_id` 가 있으면 다시 부르지 않는다. 서버 쪽은 get-or-create 라 같은 키워드·URL 이면
  같은 `trackId` 를 돌려준다.

### 콜백 수신

```
POST /api/rank/callback      (app/blueprints/rank_api.py)
헤더 X-NSR-Token: <RANK_API_TOKEN 과 같은 값>
본문 {"trackId": int, "keyword": str, "date": "YYYY-MM-DD", "rank": int|null, "prodNm": str|null}
```

- 토큰은 `hmac.compare_digest` 로 검증. 틀리면 401, 본문은 신뢰하지 않는다.
- **같은 `(trackId, date)` 가 여러 번 온다** — 하루 두 번(11시·17시) 수집 + 재시도(0/5/20/60초, 최대 4회).
  `upsert` 로만 쓰므로 몇 번 와도 하루 한 행이다.
- **모르는 `trackId` 는 200 + `matched:0`** 으로 넘긴다. 순위 서버가 여러 파트너 사이트에 같은
  payload 를 뿌리므로 남의 슬롯이 오는 게 정상이다. 여기서 4xx 를 내면 상대가 재시도를 반복한다.
- 캠페인 구동 기간 밖의 날짜는 기록하지 않는다 (슬롯이 캠페인보다 오래 산다).

순위 서버 쪽 `.env` 의 `NSR_PARTNER_CALLBACK_URL` 에 우리 주소를 **콤마로 덧붙여야** 한다
(트리플업 주소를 지우지 말 것): `http://<트리플업>:8034/api/rank/callback,http://211.45.175.195:8034/api/rank/callback`

### 기록 구간 — 시작일 전 순위도 남긴다

추적은 등록 즉시 시작하므로 **시작일 전에 들어온 순위도 기록한다.** 그게 유입 전 기준값이고,
일찍 추적을 거는 이유 자체다. 판정은 `campaign_service.in_rank_window()` 한 곳:

| | 경계 |
| --- | --- |
| 이른 쪽 | 캠페인 **등록일**(`created_at`), 시작일이 더 이르면 시작일 |
| 늦은 쪽 | **종료일**(`end_date`) |

등록 전 날짜를 버리는 이유는 파트너 슬롯이 캠페인보다 오래 살고 `track_id` 를 다른 건과
공유하기 때문이다 — 그 구간은 남의 기간이다. 구동 전 `campaign_daily` 행은 `done_qty = 0`
(작업한 건 없다). `rank_start` 는 "처음 쓴 값"이 아니라 `campaign_model.first_rank()` 로 가장
이른 날짜를 다시 읽고, `rank_now` 는 가장 최근 날짜일 때만 갱신한다 — 순위가 뒤섞여 도착해도
기준값과 현재값이 뒤집히지 않게.

### 폴백

- 순위 화면 진입 시 오늘 순위가 없으면 `GET /partner/slots/<trackId>/ranks` 로 보정
  (`campaign_service.backfill_ranks`, 캠페인당 5분 스로틀). 검수 중인 건도 대상이다.
- `scripts/cron.py hourly` 가 ① 슬롯 없는 캠페인 등록 ② 오늘 순위 빈 캠페인 보정을 돌린다.
  둘 다 `review`(검수) 상태를 포함한다 — 추적이 그때부터 돌기 때문이다.

### 중단·삭제 — 기본으로 하지 않는다

순위 서버의 파트너 슬롯은 **`partner:bbe` 공용 계정 하나**를 쓴다. 트리플업이 같은 키워드·URL 을
이미 등록했으면 우리 POST 는 그쪽 `trackId` 를 돌려받고, 우리가 DELETE 하면 **그쪽 추적까지 끊긴다.**
그래서 `untrack_if_unused()` 는 우리 쪽 진행 캠페인 수를 세는 것에 더해 `RANK_UNTRACK_ON_STOP`
(기본 `0`)이 켜져 있을 때만 실제로 지운다. 켜기 전에 순위 서버 운영자와 합의할 것.
슬롯은 자동 만료가 없고 파트너 슬롯은 수량 쿼터도 안 먹으므로, 안 지우고 두어도 비용은 없다.

### 토큰

`.env` 의 `RANK_API_TOKEN` = 순위 서버 `.env` 의 **`NSR_PARTNER_TOKEN`** 과 같은 값.
(`NSR_API_TOKEN` 은 작업 PC 에이전트용 다른 비밀값이니 혼동하지 말 것.) 인바운드 인증과 콜백
검증에 같은 값을 쓴다.

### 구현 위치

| 파일 | 역할 |
| --- | --- |
| `app/services/rank_client.py` | `product_preview` / `register_slot` / `slot_ranks` / `untrack` |
| `app/services/campaign_service.py` | `spawn_track` · `untrack_if_unused` · `apply_rank` · `backfill_ranks` |
| `app/blueprints/rank_api.py` | `POST /api/rank/callback` |
| `app/models/campaign.py` | `by_track` · `count_active_by_track` · `daily_rank` · `untracked_running` · `tracked_without_today_rank` |
| `scripts/cron.py` | `sync_ranks` (매시) |

## 설정 순서 (실제 값)

토큰은 **순위 서버가 정하고 우리가 받아 적는 값**이다. 우리가 새로 만드는 게 아니다.
값은 순위 서버 쪽 `rankingbatch_prj/scripts/prod.env`(배포 후에는 순위 서버의 `.env`)의
**`NSR_PARTNER_TOKEN`** 에 있다. 그 파일이 언제나 정답이다.

토큰 값은 이 문서에 적지 않는다 — 이 저장소는 GitHub 에 올라간다. `.env` 에만 넣는다.

### 1) 우리 서버 `.env` — 받는 쪽

```bash
cd /root/bbe_prj/bbe_prj
vi .env
```

```ini
RANK_SERVER_URL=https://rank.mbizsquare.com
RANK_API_TOKEN=<순위 서버의 NSR_PARTNER_TOKEN 과 같은 값>
RANK_UNTRACK_ON_STOP=0
```

- `RANK_SERVER_URL` 은 끝에 `/` 를 붙이지 않는다. 경로(`/partner/...`)는 코드가 붙인다.
- 둘 중 하나라도 비어 있으면 **연동 전체가 조용히 꺼진다**(수동 순위 입력으로 동작).
- 저장 후 앱 재시작: `systemctl restart bbe` (또는 `bash scripts/deploy.sh`).

확인:

```bash
cd /root/bbe_prj/bbe_prj && ./venv/bin/python -c "
from app import create_app
from app.services import rank_client
app = create_app()
with app.app_context():
    print('설정됨:', rank_client.configured())
    print(rank_client.product_preview('https://smartstore.naver.com/main/products/1234567890'))"
```

`설정됨: True` 가 나오고 미리보기 응답에 `ok: True` 가 오면 우리 → 순위 서버 방향은 끝.
`ok: False` 만 오면 토큰이 틀렸거나 방화벽에 막힌 것이다.

### 2) 순위 서버 `.env` — 보내는 쪽 (콜백)

순위 수집이 끝났을 때 순위 서버가 우리를 호출해 줘야 자동 기록이 된다.
`NSR_PARTNER_CALLBACK_URL` 은 **콤마로 여러 개**를 넣을 수 있으니, 트리플업 주소가
이미 있으면 지우지 말고 뒤에 덧붙인다.

```ini
NSR_PARTNER_CALLBACK_URL=<기존 주소가 있으면 그대로>,http://211.45.175.195:8034/api/rank/callback
# NSR_PARTNER_TOKEN 은 이미 들어 있는 값을 그대로 쓴다 — 우리 RANK_API_TOKEN 과 같아야 한다.
```

토큰은 양쪽이 **같은 값**이어야 한다. 우리 콜백은 `X-NSR-Token` 이 다르면 401 로 거절한다.
순위 서버를 재시작한 뒤, 우리 쪽에서 들어오는지 본다:

```bash
tail -f /root/bbe_prj/bbe_prj/app.log | grep -i rank
```

콜백이 아직 안 열렸어도 순위는 들어온다 — 매시 크론 `sync_ranks` 와 화면 진입 폴백이
순위 서버에서 직접 긁어오기 때문이다. 다만 하루 안에 반영되는 시점이 늦어진다.

## 확인 필요

- 순위 서버 `.env` 의 `NSR_PARTNER_CALLBACK_URL` 에 우리 주소 추가 (현재 비어 있어 콜백이 꺼져 있음)
- `RANK_UNTRACK_ON_STOP` 을 켤지 — 공용 슬롯 삭제 영향 확인 후 결정
