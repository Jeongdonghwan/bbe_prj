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

- `valid:false` = rankserver 가 URL을 읽었지만 상품 번호를 못 찾음 → 사용자에게 주소 확인 안내
- 네이버 클릭 리다이렉트(`search.naver.com/p/crd/rd`)는 rankserver 가 알아서 풀어준다

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
- 화면 문구("상품 URL을 넣으면 자동으로 채워집니다")는 `preview_on` 기준이라 토큰이 없어도
  노출되고, 실제 호출은 `preview_live`(= `WZ.preview`)가 참일 때만 일어난다

## 2단계 — 캠페인 순위 자동 조회 (계획, 미구현)

### 스키마 (선행 작업)

```sql
ALTER TABLE campaigns
  ADD track_id     VARCHAR(64) NULL,        -- rankserver 슬롯 id
  ADD track_status VARCHAR(20) NULL;        -- pending | collected | ...
CREATE INDEX idx_campaigns_track ON campaigns (track_id);
```

`scripts/migrate.py` 에 idempotent 블록으로 추가한다 (`deploy.sh` 가 자동 실행).

### 슬롯 등록

캠페인이 결제완료/승인으로 넘어가는 시점에 등록한다. 상태 전이는 반드시
`campaign_service.transition()` 을 거치므로, 훅을 거기에 건다 (알림 훅과 같은 자리).

```
POST /partner/slots  {keyword, url}
→ {trackId, status, rank, prodNm}
```

- `status == "collected"` 면 오늘 이미 수집된 키워드·상품이라는 뜻 → 응답의 `rank` 를
  그 자리에서 일별 순위로 기록
- 실패해도 캠페인 생성·승인은 성공해야 한다 (순위는 부가 기능)

### 콜백 수신

```
POST /api/rank/callback   {trackId, date, rank, prodNm}
```

- `X-NSR-Token` 검증 후 `track_id` 가 일치하는 **진행 중인 캠페인 전부**에 일별 순위 기록
- rankserver 의 `NSR_PARTNER_CALLBACK_URL` 에 bbe_prj 주소를 콤마로 추가하면 된다
  (다중 콜백 이미 지원 — 트리플업과 동시 수신 가능)
- 로그인 없이 들어오는 엔드포인트이므로 토큰 검증 실패는 401, 본문은 신뢰하지 말 것

### 중단·종료

같은 `track_id` 를 쓰는 **다른 진행 캠페인이 없을 때만** 슬롯을 지운다.

```
DELETE /partner/slots/<trackId>
```

키워드·URL이 같은 캠페인 두 건이 동시에 돌 수 있으므로, 하나가 끝났다고 바로 지우면
남은 캠페인의 순위가 끊긴다.

### 폴백

순위 화면 진입 시 오늘 순위가 없으면 보정한다. 5분 스로틀(같은 캠페인 재조회 방지).

```
GET /partner/slots/<trackId>/ranks
```

### 이식 대상 (트리플업 `C:\bbe_shop_prj`)

| 파일 | 내용 |
| --- | --- |
| `app/services/rank_client.py` | 슬롯 등록·삭제·순위 조회 |
| `app/blueprints/rank_api.py` | 콜백 수신 엔드포인트 |
| `app/services/campaign_service.py` | `_spawn_track()` / `_untrack_if_unused()` |

bbe_prj 로 옮길 때 지킬 것: SQL은 `app/models/` 안에서만, 상태 전이는
`campaign_service.transition()` 만, 쓰기 작업 로그는 기존 규칙대로.

## 확인 필요

- 2단계 착수 시점 — 현재는 1단계만 합의됨
- rankserver 배포 후 실제 미리보기 응답으로 1단계 검증 필요
  (지금까지는 스텁 서버와 `{"ok":false}` 폴백 경로로만 확인)
- `.env` 의 `RANK_API_TOKEN` 실제 값 입력 (서버·로컬 각각)
