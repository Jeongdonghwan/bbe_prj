# 리워드 트래픽 플랫폼 — PROJECT_SPEC v3

> 벤치마크: AURA biz. 구조(좌측 메뉴 + 캠페인 생성/관리 흐름)는 차용하되 디자인은 완전히 다르게 간다.
> 스택: Flask + Jinja2 SSR + MariaDB (Cafe24 가상서버). Claude Code는 Phase 단위로 하나씩 진행한다.
> **디자인 원본: `prototype_v3.html`** — 16개 화면(대시보드 / 캠페인 생성 / 쇼핑 허브 / 캠페인 관리 / 인기 트래픽 / 익명 / 질문답변 / 마케팅 정보 / 대행의뢰 / 마이페이지 / 어드민 6종)의 CSS·마크업·인터랙션을 그대로 옮긴다. 이 문서는 프로토타입에 없는 규칙·데이터·라우트를 정의한다.
> v3 변경: 쇼핑 추적 슬롯·추천 수량, 채널별 인기 트래픽(어드민 순위 설정), 대행의뢰 게시판, 실시간 카운트 제거.

> **v3.1 변경 (2026-08-30, JDH 결정): 포인트·선충전 개념 전부 폐기.** PG 심사상 선불충전이 불리하므로 캠페인 주문 시 카드·계좌이체 **건별 결제**로 간다. 아래 본문의 포인트 관련 항목은 다음과 같이 읽는다.
> - 2-3 포인트 충전 `/point`, 사이드바 "포인트 충전", 헤더 포인트, 2-11 `/admin/charges` → **삭제**. 어드민은 `/admin/payments`(결제 내역·취소)로 대체.
> - 가입 1만P·충전 보너스·환급 11%·답변 채택 100P·현상금(`posts.bounty`) → **없음**. 등급은 누적 결제액 기준.
> - 4장 `point_tx`·`charge_request`·`users.point` 없음. `campaigns.paid_point` → `paid_amount`(원) + `pay_method`·`pay_tid`·`paid_at`·`refund_amount`.
> - 규칙 "포인트 증감은 point_service.apply()" → "결제·취소는 services/payment_service 외 경로 금지". 반려=전액 취소, 진행 중 중단=잔여일 비례 부분취소(PG 부분취소 API).
> - 2-4 ④ 결제 단계: 보유 포인트 대신 PG 결제창. 금액 표기 `12,000원`.

> **결제 모델 (v3.2, 2026-08-30):** 캠페인 생성 화면에서 바로 결제. `payments(campaign_id, method card|bank, amount, status pending|paid|partial_refund|refunded|cancelled|expired, pg_provider, pg_tid, depositor, name_mismatch, bank_due_at, paid_at, refund_amount)`.
> - 금액 = 단가×일 수량×일수 → 30만원↑ 5% 할인 → 공급가 → VAT 10% → 결제 금액(`campaigns.paid_amount`, `vat`, `discount`).
> - 카드: 생성 → payments pending → PG 승인(`payment_service.confirm_card`, 실 PG 전까지 DEBUG 모의 승인) → 캠페인 `review`.
> - 무통장: 생성 → 캠페인 `pay_wait` + 입금 계좌·입금자명·기한(영업일 3일) 안내 → 운영팀 입금 확인(`confirm_bank`) → `review`. 기한 경과 `expire_unpaid` → `cancelled`.
> - 상태 전이: `pay_wait → review → approved → running → done` / `review → rejected(전액 환불)` / `running → stopped(잔여일 비례 부분 환불)` / `pay_wait → cancelled(사용자 취소·기한 만료)`. 기존 `wait` 상태는 없음.
> - PG는 `services/pg/` 어댑터 인터페이스(request/confirm/cancel)만 두고 실제 연동은 P5. 결제·환불 이력은 status_log에도 기록해 드로어 타임라인에 표시.

---

## 0. 프로젝트 한 줄 정의

소상공인·마케터가 **플레이스 / 쇼핑·스토어 / 쿠팡** 유입 캠페인을 포인트로 주문하고, 키워드 도구와 익명 커뮤니티를 함께 쓰는 셀프서브 광고 플랫폼.

- 임시 서비스명: `TRAFFIC HUB` (추후 변경, 코드에서는 `APP_NAME` 상수 1곳에서 관리)
- 사용자 유형: 일반회원(광고주), 관리자
- 결제: 포인트 선충전 → 캠페인 주문 시 차감 (외부 PG 연동은 Phase 5 이후)

---

## 1. 정보 구조 (IA)

### 1-1. 좌측 사이드바 (고정, 240px)

```
[로고]
[카카오 3초 회원가입]  ← 노란 CTA 버튼 (로그인 시 "내 포인트 12,000P" 카드로 교체)

기본
  📢 공지사항
  💬 카카오 바로상담   ↗ (외부링크)
  💳 포인트 충전

유입관리
  🛍 쇼핑·스토어  ▾
      └ 캠페인 생성   (쇼핑 허브: 공지·추적 슬롯 → 생성 폼)
      └ 캠페인 관리
      └ 인기 트래픽
  📦 쿠팡  ▾
      └ 캠페인 생성 / 캠페인 관리 / 인기 트래픽
  📍 플레이스  ▾
      └ 캠페인 생성 / 캠페인 관리 / 인기 트래픽

마케팅도구
  🔍 키워드 조회
  🔗 연관키워드 조회

커뮤니티
  🗣 익명 게시판
  ❓ 질문답변
  📈 마케팅 정보
  🤝 대행의뢰

하단
  이용가이드 / 설정 / 로그아웃
```

- 아코디언 규칙: 채널(쇼핑/쿠팡/플레이스)은 하나만 펼침. 현재 URL에 해당하는 항목은 자동 펼침 + 활성 표시.
- `active` 판정은 `request.path.startswith(prefix)` 로 Jinja 매크로에서 처리.

### 1-2. 익명 커뮤니티 위치 결정 → **좌측 사이드바 '커뮤니티' 섹션**

이유:
1. 좌측 = 기능 내비게이션, 상단 = 유틸리티(알림·포인트·프로필)라는 패턴이 이미 잡혀 있음. 상단에 메뉴를 섞으면 두 곳을 봐야 함.
2. 커뮤니티는 게시판 3개 이상으로 커질 여지가 있어 아코디언이 필요 → 사이드바가 맞음.
3. 대신 **대시보드 가운데에 "익명 게시판 최신글" 위젯**을 넣어 노출은 상단급으로 확보.

상단 헤더에는 넣지 않되, 헤더 우측에 🔔 알림 배지에 "내 글에 댓글" 이벤트를 포함시켜 재방문 유도.

### 1-3. 상단 헤더 (56px)

`[브레드크럼]  ............  [🔔 알림] [12,000 P] [프로필 ▾ / 로그인]`

배너 슬라이더(AURA의 4칸 배너)는 헤더가 아니라 **대시보드 본문 최상단**에만 둔다. 다른 페이지에서는 제거해 화면을 넓게 씀.

---

## 2. 화면 정의

### 2-1. 대시보드 `/`  (가운데 = 안내·공지·게시판)

로그인 여부와 무관하게 보이는 랜딩 겸 홈. 임시 콘텐츠는 아래 그대로 채움.

```
┌ 배너 슬라이더 (3장, 자동 5초) ────────────────────────────────┐
│ ① 신규가입 1만P 쿠폰  ② 플레이스 신규 매체 출시  ③ 광고비 환급 신청 │
└──────────────────────────────────────────────────────────┘

┌ 공지사항 (최근 5) ───────┐ ┌ 이용 안내 ───────────────────┐
│ [필독] 주말 접수 안내     │ │ 1. 포인트 충전               │
│ [업데이트] 쿠팡 매체 추가 │ │ 2. 채널 선택 → 캠페인 생성    │
│ [점검] 9/2 새벽 서버점검  │ │ 3. 매체사·기간·수량 설정      │
│ ...                     │ │ 4. 결제 → 검수 → 진행 → 완료   │
└─────────────────────────┘ └─────────────────────────────┘

┌ 채널 바로가기 (3 카드) ─────────────────────────────────────┐
│ [플레이스 캠페인 만들기] [쇼핑·스토어 캠페인 만들기] [쿠팡 …]  │
└──────────────────────────────────────────────────────────┘

┌ 익명 게시판 최신글 (8) ───┐ ┌ 자주 묻는 질문 ───────────────┐
│ 플레이스 순위 3일째 안 오르는데… (12) │ Q. 구동 시작일은 언제? … │
│ 쿠팡 리워드 효율 어떠세요? (5)        │ Q. 환불 규정은?         │
└─────────────────────────┘ └─────────────────────────────┘

┌ (로그인 시) 내 진행중 캠페인 요약 ──────────────────────────┐
│ 대기 2 · 진행 3 · 완료 11    [캠페인 관리 →]                 │
└──────────────────────────────────────────────────────────┘
```

### 2-2. 공지사항 `/notice`, `/notice/<id>`
- 목록: 카테고리 뱃지(필독/업데이트/점검/이벤트), 제목, 날짜, 조회수. 고정글 상단 핀.
- 상세: 본문(HTML 허용, 관리자만 작성), 이전/다음글.

### 2-3. 포인트 충전 `/point`
- 상단: 보유 포인트 큰 숫자, 이번 달 사용액.
- 금액 선택 버튼 (5만/10만/30만/50만/직접입력) + 보너스 표시(10만 이상 +3%, 30만 이상 +5%).
- 결제수단: 무통장입금(Phase 1) / 카드(PG, 추후).
- 하단 탭: 충전내역 / 사용내역 (테이블, 페이지네이션).

### 2-4. 캠페인 생성 `/campaign/<channel>/new`  (channel ∈ place, store, coupang)

프로토타입 `#p-new` 그대로. 구조:

- 페이지 헤더 우측 **채널 탭**(플레이스/쇼핑·스토어/쿠팡) — 탭 전환은 URL 이동. 매체사 목록·③폼 필드가 채널별로 바뀜.
- **4단계 진행 표시줄**: ① 매체사 선택 → ② 구동 정보 확인 → ③ 캠페인 설정 → ④ 결제. 상태(미완/현재/완료)는 JS가 갱신. ④ 서브텍스트는 보유 포인트 또는 "○○P 부족".
- **3열**: ① 매체사 카드 그리드(필터 칩: 전체/추천/세일/효율순/단가 낮은순) · ② 선택 매체 상세(단가·최소일·수량 범위·효율 바·최근 7일 접수 스파크·접수 규칙) · ③ 설정 폼(기간·수량 / 업체 정보 / 키워드 / 결제 요약 4섹션). 매체 미선택 시 ②③ 흐림 처리.
- **매체사 카드**: 로고 슬롯(40px, `media.logo_url` 있으면 이미지, 없거나 로드 실패 시 이니셜 + `media.color` 배경으로 폴백) · 이름 · 뱃지(추천/SALE/NEW) · 한 줄 설명 · 효율 미니바 · 단가(세일이면 정가 취소선).
- **기간**: date range + 프리셋(3/5/7/10/14일). 주말 시작 선택 시 경고 문구, 최소일 미만 경고. 힌트에 "N일 · ○요일 시작".
- **일 작업량**: stepper(매체 min~max, step 10) + "이 업종 평균 N건" 힌트(같은 카테고리 완료 캠페인 평균, 없으면 숨김).
- **키워드**: 희망 키워드 1개 + 세팅 키워드(AI 자동 ↔ 직접 입력 토글). AI 자동은 희망 키워드 기반 5개 칩 미리보기(P4 전까지는 규칙 기반: 지역어 조합).
- **하단 고정 결제바**(매체 선택 후 표시): 매체 · 기간 · 일 수량 · 세팅 키워드 요약 + 결제 포인트 + [캠페인 등록]. 포인트 부족 시 버튼 텍스트 "○○P 충전하고 등록" → 충전 화면으로 이동(현재 폼은 세션 보존).
- 금액 = 단가 × 일 수량 × 일수, 30만P 이상 5% 할인(상수 `DISCOUNT_RULES`), 변경 즉시 재계산(`/api/campaign/quote`는 서버 검증용, 표시는 클라이언트).

| 필드 | 플레이스 | 쇼핑·스토어 | 쿠팡 |
|---|---|---|---|
| 업체/상품명 | 플레이스명 | 스토어명 + 상품명 | 상품명 |
| 링크 | m.place.naver.com (PC 주소 자동 변환) | smartstore.naver.com 상품 URL | coupang.com 상품 URL |
| 키워드 | 희망 키워드 1개 | 메인 1개 + 서브 최대 3개 | 메인 1개 |
| 추가 옵션 | 매장 카테고리 | 옵션 선택 여부 | 로켓배송 여부 |

### 2-4-1. 쇼핑·스토어 채널 허브 `/campaign/store/new` 상단  (프로토타입 `#p-store`)

쇼핑·스토어의 캠페인 생성 페이지는 3열 폼 **위에** 아래 블록이 먼저 온다(플레이스·쿠팡에는 없음).

- **쇼핑 공지 띠**: `contents(board='notice', channel='store')` 최신 1건 + "쇼핑 공지 N건" 링크. (contents에 `channel` 컬럼 추가: NULL=전체, store/place/coupang)
- **쇼핑 추적 슬롯** (무료, 회원당 10개, `store_slots`): 상품 키워드(+선택 URL) 등록 → 네이버 검색광고 API로 월 검색량(PC/모바일) 조회 후 저장, 매일 새벽 갱신. 테이블: 키워드·월 검색량(PC/모바일)·일 검색량·**추천 일 수량**·7일 순위 추이 미니바·현재 순위·[이 수량으로 캠페인](생성 폼에 키워드·URL·일 수량 프리필)·삭제.
- **추천 일 수량** = `round(월 검색량 / 30 / 1000 × 1.5)` — 일 검색량 1,000회당 1.5건, 최소 1. 상수 `RECO_PER_1000=1.5`. 화면 하단에 수식 문구 노출. 매체 최소 수량(50)과 무관하게 계산값 그대로 표시하고, 캠페인 프리필 시에는 매체 min_daily 이상으로 올림.
- 우측: 슬롯 선택 → 순위 추이 라인차트(통합검색/가격비교 탭, `slot_daily`), 캠페인 진행 기간 표시 · 쇼핑 진행 캠페인 목록 · [새 쇼핑 캠페인 만들기].
- 순위 수집: `slot_daily(slot_id, date, rank_total, rank_price)` — P5 배치 전까지는 관리자 입력/CSV.

### 2-4-2. 인기 트래픽 모아보기 `/campaign/<channel>/popular`  (프로토타입 `#p-popular`)

- 채널 탭 + **카테고리 칩**(채널별로 관리자가 정의: 플레이스 = 병원·의원 / 맛집·카페 / 학원·교육 / 미용·뷰티 / 운동 / 숙박 / 일반 키워드 등, 스토어·쿠팡은 상품군).
- 카테고리 선택 시 **1·2·3위 포디움 카드**(메달 뱃지, 로고, 단가, 관리자 추천 문구, 효율, 이번 주 접수 수) + 4위 이하 "그 외 매체" 2열 목록(효율순 자동, 관리자 제외 가능).
- 카드 클릭 → 캠페인 생성(매체 프리셀렉트). 하단에 "운영팀이 주간 데이터 보고 직접 정함 · 마지막 갱신일".
- 순위·문구는 전부 `popular_sets`에서 읽음. 자동 계산 없음.

### 2-5. 캠페인 관리 `/campaign/<channel>`

프로토타입 `#p-manage` + `#drawer` 그대로.

- 상단 요약 4칸: 진행 중(오늘 소진 예정 P) · 검수+승인 대기 · 이번 달 사용 P(전월 대비 %) · 평균 순위 변동(완료 기준).
- 상태 탭(개수 뱃지) + 기간/매체 필터 + 검색(주문번호·업체명·키워드).
- 테이블 컬럼: 주문번호(mono) · 상태 · 업체+키워드(매체 로고 슬롯 30px 포함) · 매체 · 진행(진행률 바 "5 / 10일 · 종료일", 대기는 "시작일 · N일", 반려는 사유 요약) · 순위(시작 → 현재 ▲▼) · 일 수량 · 결제 P · 등록일 · 행 hover 액션.
- 행 hover 액션(상태별): 대기 → 수정/취소 · 검수 → 복사 · 진행 → 복사/중단 · 반려 → 수정 후 재접수 · 완료 → 복사/리포트.
- **행 클릭 → 우측 드로어(440px)**: 헤더(로고·업체명·주문번호·매체) · 상태+N일차+[중단 요청] · 4칸(희망 키워드/일 작업량/결제 P/누적 작업) · 순위 변동 막대(일자별, 낮을수록 높게) · 세팅 키워드 칩 · 진행 이력 타임라인(status_log) · 운영팀 메모(admin_memo, 있을 때만) · [같은 설정으로 복사] [리포트 PDF(P5)].
- 모바일(<768): 테이블 → 카드, 드로어 → 전체 화면.

### 2-6. 키워드 조회 `/tools/keyword`
- 입력: 키워드 최대 5개 (쉼표 구분).
- 결과 테이블: 키워드 · PC 검색량 · 모바일 검색량 · 합계 · 경쟁도 · 플레이스 등록 업체수(가능하면).
- 데이터 소스: 네이버 검색광고 API (`RelKwdStat`). 키는 `.env`. 결과는 24시간 캐시 테이블 저장.
- 비로그인: 하루 3회 / 로그인: 30회 / 진행중 캠페인 보유: 무제한. (`keyword_query_log`로 카운트)

### 2-7. 연관키워드 조회 `/tools/related`
- 입력: 씨앗 키워드 1개.
- 결과: 연관 키워드 최대 100개, 검색량 내림차순, 체크박스 선택 → "캠페인 생성에 담기" 버튼(세션에 담아 생성 화면 키워드 필드에 프리필).
- 같은 API 사용, 동일 캐시·쿼터 정책.

### 2-8. 커뮤니티 `/community/<board>`  (board ∈ anon, qna, info)

공통: **목록에 본문 미리보기 없음** — 제목 + 메타만. 조회는 공개, 작성·댓글·추천은 로그인 필수. 레이아웃은 본문(1fr) + 우측 사이드(300px).

**익명 닉네임 규칙** (anon, qna 공통)
- 글 작성 시 `수식어 풀(60) × 동물 풀(60)`에서 랜덤 조합 → `posts.anon_nick` 저장 (예: 꿈꾸는 다람쥐, 말없는 고래).
- 같은 글의 댓글: 작성자마다 새 닉네임을 뽑아 `comments.anon_nick`에 저장, 그 글 안에서는 동일 user → 동일 닉네임 유지(`(post_id, user_id) → nick` 매핑 테이블 `post_nicks`). 글쓴이가 댓글 달면 글의 닉네임 그대로 + "글쓴이" 뱃지.
- 같은 글 안에서 닉네임 중복 시 재추첨. 다른 글과는 절대 연결 안 됨. 관리자 화면에서도 user_id는 신고 3회 누적 글에서만 노출.
- 글쓰기 박스에 "이 글에서 당신은 **○○ ○○**"로 미리 표시(작성 전 세션에 미리 뽑아둠).

**익명 게시판 `/community/anon`**
- 정렬: 최신 / 인기(24시간 추천 10↑) / 답변 많은. 채널 태그 필터(플레이스/스토어/쿠팡/도구).
- 행: 추천수(좌측, 인기글은 빨강) · 닉네임 · 시간 · 태그 · 제목 · 댓글수 · 조회. 이미지 첨부 시 우측 썸네일 72px.
- 우측: 24시간 인기글 5 · "익명이 지켜지는 방식" 안내 · 자주 쓰는 태그. 접속자 수 같은 실시간 카운트는 표시하지 않음.
- 신고 3회 → 자동 블라인드(`is_blind`), 관리자 해제. 업체명·전화번호 패턴 자동 마스킹.

**질문답변 `/community/qna`**
- 필터: 전체 / 미해결 / 해결됨 / 현상금. 질문에 상태 뱃지(미해결=노랑, 해결됨=초록) + 채널 태그 + 현상금 뱃지(검정).
- 우측 답변 박스: 답변 수(0이면 점선 박스), 채택된 질문은 체크 박스 추가.
- **현상금**: 질문자가 0~5,000P를 걸 수 있음(`posts.bounty`, 작성 시 차감). 채택 시 답변자에게 100P + 현상금 지급, 채택 없이 30일 경과 시 질문자 환불. 채택은 질문자만, 1회.
- 우측: 내 답변 활동(채택 수 · 답변 수 · 채택률 · 받은 P · 뱃지 진행바) · 현상금 큰 질문 · 공지에 이미 있는 질문 링크.

**마케팅 정보 `/community/info`**
- **관리자 전용 작성.** 분류 3종: 가이드 / 데이터 / 업데이트. 고정글 상단 핀.
- 목록: 태그 · 일자 · 제목만. 이미지·커버 없음. 우측 사이드는 **"처음 시작하는 분께" 시리즈 1개만**(관리자가 순서 지정, 읽은 편은 초록 체크 + "읽음", 미읽음은 예상 읽기 시간).
- 인기글·많이 읽은 글 없음.

**대행의뢰 `/community/agency`** (프로토타입 `#p-agency`)
- 상단 의뢰 폼: 채널 / 업종 / 월 예산(구간 select) / 지역 / 요청 내용. 업체명·연락처 비필수. 목록에는 익명 닉네임(같은 nick_service).
- 목록: 예산 박스 · 상태(모집 중/매칭 완료/마감) · 채널 태그 · 업종·지역 · 시간 · 제목 · 닉네임 · 조회 · 제안 수.
- **제안**(`agency_proposals`): 운영팀(admin) 또는 **인증 대행사**(`users.is_agency`, 완료 캠페인 30건 + 사업자 인증, 관리자 승인)만 작성. 제안 = 예산안 · 계획 · 예상 기간. 의뢰자만 제안 열람.
- 의뢰자가 제안 **수락** → 상태 매칭 완료, 수락한 대행사에게만 연락처 공개(`agency_requests.contact`), 이후 카카오로 진행. 30일 무응답 시 자동 마감.
- 우측: 진행 절차 4단계 · 내 의뢰 · 대행사 참여 안내([인증 신청] → admin 승인 큐).
- 어드민 `/admin/agency`: 의뢰 목록·제안 목록·대행사 인증 승인 (목록 패턴).

### 2-9. 인증
- 카카오 로그인만 (`/auth/kakao`, `/auth/kakao/callback`). 이메일 가입 없음.
- 최초 로그인 시 닉네임·연락처 입력 모달 → 1만P 지급.
- 관리자: `users.role = 'admin'`, 별도 `/admin` 진입.

### 2-10. 마이페이지 `/my`

프로토타입 `#p-my`. 좌(300px): 프로필(닉네임·마스킹 전화·카카오 연결·가입월) + 완료 캠페인/누적 사용/등급 3칸 · 보유 포인트 큰 숫자 + 이번 달 사용·환급 예정 + [충전][환급 신청] · 사업자 정보(상호·사업자번호·세금계산서 자동발행 여부, 수정 모달).
우: 채널별 내 캠페인 요약 3칸 → [전체 관리] · 포인트 내역 테이블(탭: 전체/충전/사용/환불/환급, 변동은 +초록/−검정, 잔액 컬럼) · 알림 설정 토글 3개(캠페인 상태 알림톡 / 내 글 댓글 / 이벤트) · 내가 쓴 글 · 회원 탈퇴(진행 중 캠페인 있으면 불가).
등급: 누적 사용 P 기준 브론즈(0) / 실버(100만) / 골드(500만) — 상수 `GRADE_RULES`, P5 전까지 표시만.

### 2-11. 관리자 `/admin/*`  (role=admin, 별도 사이드바)

프로토타입 어드민 5화면 + 목록형 3화면. 어드민 모드에서 사이드바 배경 `#0B1220`, 헤더에 "관리자 모드" 뱃지, 사이드바 하단 "사용자 화면" 링크로 복귀.

| 경로 | 내용 |
|---|---|
| `/admin` 운영 현황 | 처리 큐 5칸(검수 대기·가장 오래된 건 경과시간 / 충전 대기·합계 / 오늘 순위 미입력·진행 중 수 / 신고 누적 / 오늘 접수·매출P), 헤더에 13:30 카운트다운. 검수 큐 테이블에서 바로 승인/반려. 매체사별 오늘 접수. 최근 처리 로그(admin_log). |
| `/admin/orders` 주문 관리 | 상태 탭(개수) + 채널/매체/기간 필터 + 검색. 표 안에서 상태 select·순위 input·저장. 체크박스 일괄 승인/반려. **금지 문구 감지**(`forbidden_words` 테이블: 최저가, 1위, 의료법 용어 등) 시 행 배경 빨강 + 경고 라인. 반려는 사유 입력 모달 필수 → 자동 전액 환불. 진행 중 행은 "오늘 순위 저장"(campaign_daily upsert) + 중단. 엑셀 내보내기, 순위 일괄 업로드(CSV: order_no,date,rank,done_qty). |
| `/admin/charges` 충전 승인 | 탭 대기/완료/취소. 입금자명 ≠ 회원명이면 "이름 다름" 뱃지, 24시간 경과 빨강. [입금 확인·승인] → point_tx(charge)+bonus 한 트랜잭션 + 알림톡. 하단 수동 지급·차감(회원 검색·포인트·사유 필수 → point_tx type=admin). |
| `/admin/media` 매체사 관리 | 채널 탭(개수) + 그룹별 목록(로고·이름·뱃지·설명·단가(정가 취소선)·효율·최소일/범위·이번 달 접수·노출 토글·[수정]). 우측 수정 패널: 로고 업로드(정사각 PNG/SVG, `/static/uploads/media/`, 없으면 이니셜) · 이름 · 그룹 · 설명 · 단가 · 정가 · 최소일 · 수량 범위 · 접수 마감 · 효율 수동값(비우면 자동) · 뱃지(추천/SALE/NEW/없음) · 상세 안내 · 노출 · 당일 구동 체크. 효율 자동 계산 = 최근 30일 완료 중 순위 상승 비율, 새벽 배치. |
| `/admin/content` 공지·정보글 | 탭 전체/공지/마케팅 정보/입문 시리즈/임시저장. 표: 게시판·분류·제목(고정 태그)·상태(발행/예약 일시/임시저장)·조회·일자·수정/고정/순서. 에디터: 제목 + 본문(간단 툴바: B/I/H2/목록/표/링크/이미지/구분선, HTML 저장). 우측 발행 설정: 게시판 select(선택에 따라 분류 select 변경: 공지=필독·업데이트·점검·이벤트 / 정보=가이드·데이터·업데이트 / 시리즈=편 번호) · 발행 지금/예약 · 상단 고정 · 대시보드 노출 · 발행 시 회원 알림(공지만) · 목록 미리보기 · [발행][임시저장]. |
| `/admin/popular` 인기 트래픽 설정 | 채널 탭 + 카테고리 목록(1·2·3위 요약·갱신일·노출 토글·[수정]) + [+카테고리]. 우측 수정 패널: 카테고리명 · 순위 3행(매체 select + 추천 문구 + 순서 이동) · 4위 이하 제외 체크 · 이번 주 접수 수 표시 토글 · 노출. 저장 → admin_log. |
| `/admin/agency` 대행의뢰 | 의뢰 목록(상태 변경·마감) · 제안 목록 · 대행사 인증 신청 승인/반려. (목록 패턴) |
| `/admin/banners` 배너 관리 | 목록 + 이미지/링크/기간/순서/노출 토글. 대시보드 3칸에 노출 중인 것만. (프로토타입 없음, 매체사 관리 목록 패턴) |
| `/admin/users` 회원 목록 | 검색 · 닉네임/전화/가입일/보유P/누적 사용/캠페인 수/등급/상태(정상·정지) · 상세 드로어(포인트 내역·캠페인·글). (목록 패턴) |
| `/admin/reports` 신고·블라인드 | 신고 누적 글/댓글 목록(누적 수·사유·게시판) · 블라인드/해제 · 3회 이상 글만 user_id 노출. (목록 패턴) |

---

## 3. 디자인 방향

AURA는 흰 바탕 + 컬러풀 아이콘 + 핑크·퍼플 그라데이션 배너 = "이벤트 많은 광고 플랫폼" 느낌. 여기서 정반대로 간다.

**컨셉: "관제실(Control Room)" — 어두운 사이드바 + 밝은 작업 영역, 단일 액센트 컬러, 데이터 중심.**

### 3-1. 토큰 (`static/css/tokens.css`)

```css
:root {
  --sidebar-bg: #111827;      /* 짙은 네이비-블랙 */
  --sidebar-text: #9CA3AF;
  --sidebar-active: #FFFFFF;
  --sidebar-active-bg: rgba(255,255,255,.08);

  --bg: #F5F6F8;              /* 작업 영역 */
  --surface: #FFFFFF;
  --border: #E5E7EB;
  --text: #111827;
  --text-2: #6B7280;

  --accent: #2563EB;          /* 유일한 액센트 */
  --accent-hover: #1D4ED8;
  --kakao: #FEE500;           /* 카카오 CTA 전용 */
  --success: #16A34A; --warn: #D97706; --danger: #DC2626;

  --radius: 10px;
  --shadow: 0 1px 2px rgba(0,0,0,.04), 0 4px 12px rgba(0,0,0,.04);
  --font: 'Pretendard Variable', Pretendard, -apple-system, sans-serif;
}
```

### 3-2. 규칙
- 아이콘: 컬러 일러스트 금지. **Lucide** 단색 선 아이콘, 20px, 사이드바에서는 `--sidebar-text`, 활성 시 흰색.
- 매체사 로고: `.logo-slot`(둥근 사각 40px) 안에 `<img src=logo_url>` — 없거나 로드 실패 시 이니셜 + `media.color` 배경으로 폴백(프로토타입 JS 방식). 뱃지는 텍스트 뱃지(추천/SALE/NEW)만.
- 커뮤니티 목록은 제목만. 본문 미리보기·썸네일 커버·"많이 읽은 글" 없음(익명 게시판 이미지 첨부 썸네일은 예외).
- 상태 뱃지 색: 대기 회색 / 검수 파랑 / 승인 청록 / 진행 초록 / 반려 빨강 / 완료 짙은회색 / 중단 주황.
- 숫자는 `font-variant-numeric: tabular-nums`. 금액은 `12,000 P` 형식, 원화는 충전 화면에서만.
- 그라데이션은 배너 3장에만 허용. 나머지 UI는 플랫.
- 버튼: primary(액센트 채움) / secondary(테두리) / kakao(노랑). 이 3종만.
- 페이지 상단: `<h1>`(20px, 700) + 우측 액션 버튼 1개. 브레드크럼은 헤더에.

### 3-3. 반응형
- ≥1280: 사이드바 고정 240 + 본문.
- 768~1279: 사이드바 72px 아이콘만, hover 시 확장.
- <768: 사이드바 숨김, 하단 탭바 5개(홈/캠페인/충전/커뮤니티/메뉴).

---

## 4. 데이터 모델 (MariaDB, utf8mb4)

```sql
users            (id, kakao_id, nickname, phone, role ENUM('user','admin'), point INT, grade ENUM('bronze','silver','gold'), biz_name NULL, biz_no NULL, tax_invoice BOOL, notify_campaign BOOL, notify_comment BOOL, notify_event BOOL, status ENUM('active','suspended'), created_at)
point_tx         (id, user_id, type ENUM('charge','use','refund','bonus','admin'), amount INT, balance_after INT, ref_type, ref_id, memo, created_at)
charge_request   (id, req_no CHAR(11), user_id, amount INT, bonus INT, method ENUM('bank','card'), depositor, name_mismatch BOOL, status ENUM('pending','done','cancel'), created_at, done_at, done_by NULL)

media            (id, channel ENUM('place','store','coupang'), group_name, name, tagline, logo_url NULL, color CHAR(7), unit_price INT, list_price INT NULL, min_days INT, min_daily INT, max_daily INT, efficiency_auto TINYINT, efficiency_manual TINYINT NULL, cutoff_time TIME, same_day BOOL, description TEXT, badge ENUM('rec','sale','new') NULL, sort, is_active)
campaigns        (id, order_no CHAR(10) UNIQUE, user_id, channel, media_id, status ENUM('wait','review','approved','running','rejected','done','stopped'),
                  biz_name, product_name, target_url, main_keyword, sub_keywords JSON, setting_keywords JSON, keyword_mode ENUM('ai','manual'),
                  extra JSON, start_date, end_date, daily_qty INT, total_qty INT, unit_price INT, discount INT, paid_point INT,
                  rank_start INT, rank_now INT, reject_reason, admin_memo, created_at, updated_at)
campaign_daily   (id, campaign_id, date, done_qty INT, rank INT, UNIQUE(campaign_id,date))   -- 관리자 입력/CSV/배치
status_log       (id, campaign_id, from_status, to_status, actor_id NULL, memo, created_at)   -- 드로어 타임라인
forbidden_words  (id, word, channel NULL, severity ENUM('warn','block'))
admin_log        (id, admin_id, action, target_type, target_id, summary, created_at)

contents         (id, board ENUM('notice','info','series'), channel ENUM('store','place','coupang') NULL, category, series_no NULL, title, body MEDIUMTEXT, status ENUM('draft','scheduled','published'), publish_at, is_pinned, show_dashboard, notify BOOL, views, author_id, created_at, updated_at)
series_reads     (user_id, content_id, PK)
-- notices 테이블은 contents(board='notice')로 대체
notifications    (id, user_id, type, title, link, is_read, created_at)

store_slots      (id, user_id, keyword, product_url NULL, store_name NULL, pc_cnt INT, mo_cnt INT, reco_qty INT, fetched_at, created_at)
slot_daily       (slot_id, date, rank_total INT NULL, rank_price INT NULL, PK(slot_id,date))
keyword_cache    (keyword PK, pc_cnt, mo_cnt, comp, fetched_at)
related_cache    (seed, keyword, pc_cnt, mo_cnt, fetched_at, INDEX(seed))
keyword_query_log(id, user_id NULL, ip, tool, query, created_at)

boards           (id, slug UNIQUE, name, is_anon BOOL, write_role)
posts            (id, board_id, user_id, anon_nick VARCHAR(20), channel_tag NULL, title, body TEXT, image_url NULL, bounty INT DEFAULT 0, is_solved BOOL, accepted_comment_id NULL, views, likes, report_cnt, is_blind, created_at, updated_at)
post_nicks       (post_id, user_id, nick VARCHAR(20), PK(post_id,user_id))   -- 글 안 닉네임 고정
nick_words       (id, kind ENUM('adj','noun'), word)   -- 수식어 60 · 동물 60
comments         (id, post_id, user_id, parent_id NULL, anon_nick VARCHAR(20), body TEXT, likes, is_accepted BOOL, is_blind, created_at)
post_likes       (post_id, user_id, PK(post_id,user_id))
reports          (id, target_type, target_id, user_id, reason, created_at)
banners          (id, image_url, link, title, sort, is_active, start_at, end_at)

popular_categories(id, channel, name, sort, is_active)
popular_sets     (id, category_id, rank TINYINT, media_id, note VARCHAR(80), UNIQUE(category_id,rank))   -- rank 1~3
popular_excludes (category_id, media_id, PK)   -- 4위 이하에서 제외
popular_meta     (category_id PK, show_weekly_cnt BOOL, updated_at, updated_by)

agency_requests  (id, user_id, anon_nick, channel ENUM('place','store','coupang','multi'), industry, budget ENUM('u30','30_100','100_300','o300','tbd'), region, body TEXT, contact VARCHAR(40) NULL, status ENUM('open','matched','closed'), accepted_proposal_id NULL, views, created_at, closed_at)
agency_proposals (id, request_id, proposer_id, budget_plan TEXT, plan TEXT, duration, status ENUM('sent','accepted','rejected'), created_at)
agency_applies   (id, user_id, biz_no, biz_cert_url, status ENUM('pending','approved','rejected'), created_at, reviewed_by)
-- users에 is_agency BOOL 추가
```

- `order_no`: `N` + 9자리 랜덤 숫자, 생성 시 중복 검사. `req_no`: `C` + YYMMDD + `-` + 3자리 일련.
- 포인트 지급 규칙(상수): 가입 10,000 / 충전 보너스 10만↑ 3%, 30만↑ 5% / 답변 채택 100 + 현상금 / 광고비 환급 전월 사용액 11%(매월 5일 배치, P5) / 인증회원 글 5,000은 폐기(마케팅 정보는 관리자 전용).
- 닉네임 생성: `nick_service.pick(post_id, user_id)` — post_nicks에 있으면 반환, 없으면 adj×noun 랜덤, 같은 post 내 중복이면 재추첨 후 저장.
- 포인트 변동은 반드시 `point_tx` 삽입과 `users.point` 갱신을 한 트랜잭션으로 (서비스 레이어 `point_service.apply()` 단일 진입점).
- 캠페인 상태 전이표:
  `wait → review → approved → running → done` / `review → rejected(포인트 자동 환불)` / `running → stopped(잔여일 비례 환불)` / `wait → (사용자 취소, 전액 환불)`.

---

## 5. 프로젝트 구조

```
app/
  __init__.py          create_app, 블루프린트 등록, 컨텍스트 프로세서(사이드바 메뉴·포인트)
  config.py            .env 로드
  db.py                pymysql 커넥션 풀 + get_db()
  models/              순수 SQL 함수 모듈 (ORM 없음)
  services/            point_service, campaign_service, keyword_service(네이버 API+캐시), notify_service, nick_service, forbidden_service
  blueprints/
    main.py            /  대시보드
    auth.py            /auth/kakao
    notice.py          /notice
    point.py           /point
    campaign.py        /campaign/<channel>[/new]
    tools.py           /tools/keyword, /tools/related
    community.py       /community/<board>
    my.py              /my
    admin.py           /admin/*  (orders, charges, media, content, banners, users, reports)
  templates/
    layout/base.html, sidebar.html(사용자/관리자 nav 분기), header.html, bottom_tab.html
    macros/            status_badge, pagination, form_field, media_card
    (blueprint별 폴더)
  static/css/tokens.css, base.css, components.css
  static/js/campaign_new.js, tools.js, sidebar.js
scripts/
  seed.py              매체사·게시판·공지·배너 더미 데이터
  batch_rank.py        (Phase 5) 순위 수집 배치
schema.sql
.env.example
CLAUDE.md
```

- JS는 바닐라, 번들러 없음. 날짜 선택은 `flatpickr` CDN, 차트는 `Chart.js` CDN, 아이콘은 Lucide CDN.
- 서버 사이드 렌더 우선. JSON 엔드포인트는 `/api/...` 접두어로 최소화(가격 계산, 키워드 조회, 좋아요).

---

## 6. 개발 단계 (Claude Code는 한 Phase씩)

| Phase | 범위 | 완료 기준 |
|---|---|---|
| **P1 레이아웃·대시보드·콘텐츠** | 골격, tokens/base CSS(프로토타입 CSS 이식), 사이드바(사용자/관리자 분기·아코디언·active)·헤더·하단탭, 대시보드(더미), 공지 목록/상세, 마케팅 정보 목록/상세 + 시리즈 사이드, `seed.py`(매체사 20·공지·정보글·시리즈 5·배너 3·nick_words 120·forbidden_words) | 모든 사이드바 링크 200 응답. 반응형 3단계. 시리즈 읽음 체크 동작 |
| **P2 인증·포인트·마이페이지** | 카카오 로그인, 최초 가입 모달·1만P, 포인트 충전 화면, 무통장 충전요청(req_no·name_mismatch), `point_service` 트랜잭션, 마이페이지 전체(포인트 내역 탭·알림 토글·사업자 정보) | 충전요청 → SQL 승인 → 잔액·내역 반영 |
| **P3 캠페인** | 쇼핑 추적 슬롯(store_slots·추천 수량·프리필), 3채널 생성 화면 v2(채널 탭·진행 표시줄·로고 폴백·프리셋·결제바·부족 시 충전 이동), 관리 v2(요약 4칸·진행률·드로어·status_log), 복사/수정/취소, 상태 전이 + 환불, forbidden_service 사전 경고 | 주문 → 차감·point_tx·status_log, 반려 → 환불, 드로어 타임라인 표시 |
| **P4 어드민·커뮤니티·도구** | 어드민 10화면(운영 현황·주문·충전 승인·매체사(로고 업로드)·인기 트래픽 설정·콘텐츠 에디터·대행의뢰·배너·회원·신고), 인기 트래픽 모아보기(3채널), 커뮤니티 4보드(대행의뢰 포함: 제안·수락·연락처 공개·대행사 인증), 기존 3보드(nick_service·post_nicks·현상금·채택·신고 블라인드·마스킹), 알림, 네이버 API 키워드/연관 조회 + 캐시 + 쿼터 | 관리자가 UI에서 주문 승인·순위 입력·충전 승인·매체사 수정 가능. 같은 글 안 닉네임 유지 |
| **P5 운영** | 순위 수집 배치·효율 자동 계산 배치·환급 배치(5일)·현상금 30일 환불 배치, 리포트 PDF, PG 카드 결제, 알림톡 실연동, 등급 산정, 로그·에러 페이지, 배포 스크립트 | Cafe24 배포 후 실주문 1건 완주 |

각 Phase 시작 전 Claude Code에게: "PROJECT_SPEC 섹션 N만 읽고 Phase N 구현. 다른 Phase 건드리지 말 것. 끝나면 실행 방법과 확인 체크리스트 출력."

---

## 7. CLAUDE.md (프로젝트 루트에 그대로 사용)

```markdown
# CLAUDE.md

## 프로젝트
리워드 트래픽 플랫폼. 스펙은 PROJECT_SPEC_v3.md, 디자인 원본은 prototype_v3.html — 코드 작성 전 반드시 해당 Phase 섹션과 프로토타입의 해당 화면(#p-xxx)을 읽는다. 프로토타입의 CSS 변수·클래스명을 그대로 쓴다(새 이름 만들지 말 것).

## 스택
- Python 3.11, Flask 3, Jinja2 SSR, pymysql, MariaDB 10.6, 바닐라 JS
- ORM 사용 금지. SQL은 app/models/ 안의 함수로만.
- CSS는 tokens.css 변수만 사용. 하드코딩 색상 금지.
- 아이콘은 Lucide만. 이미지 아이콘 금지.

## 규칙
- 포인트 증감은 services/point_service.apply() 외 경로 금지.
- 캠페인 상태 변경은 services/campaign_service.transition() 외 경로 금지 (전이표 검증 + status_log 기록).
- 익명 닉네임은 services/nick_service.pick() 외 경로 금지. 목록 화면에 본문 미리보기 출력 금지.
- 관리자 쓰기 작업은 admin_log에 남긴다.
- 모든 목록 페이지는 pagination 매크로 사용, 페이지당 20.
- 사용자 입력은 서버에서 검증. 링크는 채널별 도메인 화이트리스트.
- 한글 UI 텍스트. 코드·주석은 영어.
- 새 라우트 추가 시 sidebar.html 메뉴 구조(app/__init__.py MENU 상수)와 동기화.

## 실행
cp .env.example .env → mysql < schema.sql → python scripts/seed.py → flask run

## 현재 Phase
P1  (완료 후 여기 갱신)
```

---

## 8. 오픈 이슈 (JDH 결정 필요)

1. 서비스명 / 도메인
2. 매체사 실제 목록·단가 (seed는 더미 8개로 시작)
3. 순위 데이터 소스: 직접 크롤링 vs 외부 API vs 관리자 수동 입력(P4 기본)
4. 네이버 검색광고 API 계정 준비 여부
5. 친구 초대 이벤트 포함 여부 (환급 11%는 P5에 포함됨)
6. 카카오 알림톡 발신 프로필·템플릿 준비(P5)
7. 매체사 실제 로고 파일 (없으면 이니셜로 오픈 가능)
