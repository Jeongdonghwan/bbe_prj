# CLAUDE.md

## 프로젝트
리워드 트래픽 플랫폼. 스펙은 PROJECT_SPEC_v3.md, 디자인 원본은 prototype_v3.html — 코드 작성 전 반드시 해당 Phase 섹션과 프로토타입의 해당 화면(#p-xxx)을 읽는다. 프로토타입의 CSS 변수·클래스명을 그대로 쓴다(새 이름 만들지 말 것).

## 스택
- Python 3.11, Flask 3, Jinja2 SSR, pymysql, MariaDB 10.6, 바닐라 JS
- ORM 사용 금지. SQL은 app/models/ 안의 함수로만.
- CSS는 tokens.css 변수만 사용. 하드코딩 색상 금지.
- 아이콘은 Lucide만. 이미지 아이콘 금지.

## 규칙
- 결제 모델 v3.3 (2026-09-16, v3.1 폐기): 선충전 **크레딧**. 무통장 충전 요청(charge_requests, VAT 10%는 입금액에만) → 어드민 승인/직접 충전(credit_ledger + users.credit_balance, services/credit_service — 잔액 변경은 models/credit.apply()만). 캠페인은 생성 시 크레딧 차감(VAT 없음) 후 바로 review, 환불(반려 전액·중단 잔여)은 크레딧 반환. 카드/건별 PG 결제 폐기(pay/bank 라우트·payments 테이블은 레거시 조회용). 결제·취소는 여전히 payment_service 경유(credit 분기 포함).
- 캠페인 상태 변경은 services/campaign_service.transition() 외 경로 금지 (전이표 검증 + status_log 기록).
- 익명 닉네임은 services/nick_service.pick() 외 경로 금지. 익명·마케팅 정보 목록은 마케팅광장(ranking_product_next) 스타일 리스트(.category-list-*, 2줄 미리보기 포함 — 2026-08-31 JDH 결정으로 기존 '미리보기 금지' 규칙 폐기).
- 관리자 쓰기 작업은 admin_log에 남긴다.
- 모든 목록 페이지는 pagination 매크로 사용, 페이지당 20.
- 사용자 입력은 서버에서 검증. 링크는 채널별 도메인 화이트리스트.
- 한글 UI 텍스트. 코드·주석은 영어.
- 새 라우트 추가 시 sidebar.html 메뉴 구조(app/__init__.py MENU 상수)와 동기화.

## 실행
cp .env.example .env → mysql < schema.sql → python scripts/seed.py → flask run

## 현재 Phase
- 2026-09-21 캠페인 위저드 개편(CAMPAIGN_WIZARD_SPEC.md): 5스텝(상품 정보 / [광고 설정] 광고 유형·유입 설정 / 일정 / 최종 확인), 폭 1000px·높이 가변, 통과한 스텝만 클릭 이동. macro 4종 재사용(macros/wizard_steps·ad_type_list·count_stepper·period_picker·cost_summary) + css/wizard.css + js/wizard.js. 광고 유형은 라디오 1열(단가 우측). 일일 목표 유입수는 직접 입력 가능, 최소 100·상한 없음(media.max_daily=0이면 무제한). **접수 24시간, 구동은 익일부터(constants.ORDER_CUTOFF=16:00 이후 접수는 익익일, 당일 시작 없음 — campaign_service.earliest_start)**, 시작일은 사용자가 선택. 제출 시 서버가 단가를 다시 읽어 총액 재계산하고 client_total과 다르면 거부. URL은 채널별 경로 패턴 검증(constants.URL_PATTERNS, 쿼리 보존). 매체 카탈로그는 constants.MEDIA_CATALOG(실서비스 목록). 카피 규칙: 이모지 금지, "생성" 대신 "만들기".
- 2026-09-16 크레딧 전환: 충전 위저드 /credit/charge(3스텝: 금액+입금자명 → 세금계산서 사업자정보 → 확인, templates/credit/charge.html, .wiz 공용 위저드 CSS). 마이페이지 = My 크레딧 카드 + 충전 요청/사용 내역 탭. 캠페인 생성 = 4스텝 위저드(상품 URL·이름 수동 입력 → 매체 타일·키워드·일일 유입수(100단위) · 요청사항(extra.request_note) → 기간 10/20/30일(DATE_PRESETS, 시작일 서버 계산) → 비용 요약+보유 크레딧, 부족 시 충전 유도). campaign_service.create_with_credit(). 어드민 /admin/credits: 충전 요청 승인·거절 + 회원 직접 충전·차감 + 최근 원장. deploy 시 migrate.py가 스키마 반영.
P4 완료 (2026-08-30, a·b·c 전부) → 다음 P5 운영(배치·실 PG·알림톡·리포트·배포)
- 2026-09-22 인기 트래픽 시안 I (기준 문서: Downloads/prototype_popular_traffic (1).html — 프로토타입이 디자인 정본, 재해석 금지. 09-21 의 보라 색면·TRAFFIC·검정 2px 테두리 버전은 전부 폐기): /popular 페이지 + 대시보드 위젯 + 공용 드로어. CSS는 static/css/popular.css 로 옮기되 위젯이 대시보드에도 올라가서 :root 를 쓰면 전역 토큰을 덮어쓰므로 **토큰은 --p-*, 클래스는 p- 접두사**로 두고 .poppage/.p-widget/.p-drawer/.p-scrim 에만 선언한다.
  - 카드: 흰 카드 14px 라운드 + 정사각 타일(상단 24% 그룹 띠 — 리워드 핑크 #FFB6C1 / 유입플 하늘 #87CEFA (09-22 JDH 선택, 프로토타입 틴트 대체) / 기성 연회색 #f2f2f3, 아래 연회색 바탕에 흰 원 + 900 굵기 이름, 글자 수 4↑ 32px·6↑ 26px·기본 38px + BBene). 카드에는 순위 메달을 넣지 않는다 — 운영팀 추천은 "이번 주 운영팀 추천" 섹션의 큰 카드 3장(타일 16:11, 한줄평 포함)으로만. 로고 이미지는 무시하고 이름 텍스트 타일만.
  - 채널 탭 순서는 어디서든 constants.TRAFFIC_CHANNELS (쇼핑·스토어 → 플레이스 → 쿠팡), 기본 쇼핑·스토어. 탭·정렬은 클라이언트 전환(세 채널 전부 렌더), 현재 채널은 history.replaceState 로 ?ch= 반영. 콘텐츠 폭 .poppage max-width 1140px, 그리드 minmax(200px) → 한 줄 5개.
  - 페이지 구조: 이번 주 운영팀 추천(weekly_ranks 1~3) → 전체 상품(추천순·후기순·단가순) → 그룹 소제목(자체 개발 · 리워드 / 자체 개발 · 유입플 / 기성 매체). 자체가 없는 채널은 자체 섹션 숨김.
  - 드로어 헤더 마크는 타일 축소판(.p-mark.p-mk.p-lg 72px, 괄호 떼고 글자 수로 14/18/22px), 순위는 이름 옆 .p-medal 로만. 나머지 섹션은 09-21 과 같다. "캠페인 만들기"는 실제 위저드 경로 /campaign/<ch>/new?type=<id>.
  - 위젯: "운영팀 주간 인기 트래픽" + ? 툴팁(title) + 전체 보기 / 밑줄형 채널 탭 / 5행(1~3위 메달·4~5 숫자 · 이름 · ★평점·후기·자체|기성·환불불가 · 단가). 마크·로고 없음. 마지막 캠페인 채널 기억 로직 없음.
  - 후기 0건: 카드·위젯은 프로토타입 rate() 그대로 "후기 없음" 텍스트, 드로어는 "등록된 후기가 없습니다"만(평균·분포 바 생략).
  - media(=ad_types)의 origin(own/ready) / group_key(reward/inflow) / no_refund_days / rank_lead_days / op_note / rating_avg / review_cnt, weekly_ranks(주 시작 월요일), reviews 정책(완료 캠페인당 1건, 캠페인 키워드·기간 복사, nick_service.draw() 고정, review.recount() 로만 집계)은 09-21 그대로. 설명·한줄평은 어드민 입력값이라 시드에 넣지 말 것.
  - 매체별 익명 댓글(media_comments/media_nicks, nick_service.pick_media)은 09-21 폐기·삭제 완료(migrate 가 DROP).
  - 미구현: 어드민(순위·설명 편집), 위저드 Step 2 자동 선택(?type= 은 로그만 남김).
- 2026-09-21 캠페인 위저드 v3 (기준 문서: Downloads/prototype_wizard_v3.html + HANDOFF_v3.md — 프로토타입이 디자인 정본, 재해석 금지): 5스텝(상품 정보 / [광고 설정] 광고 유형·유입 설정 / 일정 / 최종 확인), 1000px 고정·내용 높이. 프로토타입 CSS를 wizard.css로 통째 이식하되 전역 CSS와 충돌해서 **모든 클래스에 `w-` 접두사**를 붙이고 `.wzpage` 아래로 스코프했다(프로토타입의 .wiz/.card/.tabs/.in/.btn/.steps가 기존 전역 규칙과 40곳 충돌). 프로토타입 토큰(--brand/--ink/--line/--sh-1..3)은 wizard.css :root에 그대로, 단 다크모드 블록은 제외(앱 전체가 라이트 전용)하고 폰트는 Pretendard 유지.
  - 광고 유형(Step 2)은 마스터-디테일: 그룹 탭 + 3열 카드 / 우측 300px sticky 패널(설명·"이런 상품에 맞아요" 칩·"진행 방식" 번호목록·100회x10일 기준 비용). 패널 데이터는 media.description/fit_for/flow_steps(JSON)·badge/badge_until에서 오고 전부 **어드민 입력값**이다 — 시드에 넣지 말 것. description이 NULL이면 "설명이 아직 등록되지 않았습니다.".
  - 뱃지 ENUM hot/best/new/pick(인기·BEST·NEW·추천, rec→hot 이관). badge_until이 지나면 표시 안 함 — 판정은 models/media.decorate()에서 하고 list_by_channel/get이 자동 적용(badge_label 세팅).
  - "오늘의 인기" 띠는 daily_picks(pick_date, channel, type_ids JSON), 어드민 매체사 관리 상단에서 채널별로 저장(POST /admin/media/picks).
  - 접수는 24시간, 구동은 **익일부터**. ORDER_CUTOFF=16:00 이후 접수는 익익일 — campaign_service.earliest_start()가 유일한 판정 지점이고 서버에서 재검증한다. 당일 시작 없음.
  - 일일 목표 유입수 상한 없음(media.max_daily=0 = 상한 없음, MEDIA_MIN_DAILY=100). 총액은 서버가 unit_price로 다시 계산해 client_total과 대조하고 다르면 거절.
  - 매체 카탈로그는 실제 목록(플레이스 7 / 스토어 27 / 쿠팡 2, constants.MEDIA_CATALOG) — "테스트 N"은 is_active=0으로 내렸다.
  - 상품명(store·coupang)은 **선택 입력** (2026-09-21 JDH). 비우면 main_keyword를 biz_name(목록 표시명)으로 쓴다 — 판정은 _parse_form 한 곳. 플레이스명(place)은 여전히 필수.
  - 사이드바 hover 확장 모션은 tokens.css의 --side-ease/--side-open/--side-close/--side-*-delay로만 조절한다 (2026-09-21 JDH "너무 급하게 펴지고 닫힌다"). 펼침 .34s(지연 .07s — 스치고 지나갈 때 안 열리게), 닫힘 .4s(지연 .16s — 곧장 닫히지 않게), 라벨은 display 전환이라 transition이 안 먹어서 @keyframes sideLabelIn으로 페이드인. 프로토타입 원본은 width .22s ease 하나였다.
  - 사이드바 섹션 캡션(.nav-sec>h6)은 프로토타입이 #6B7280(밝은 사이드바 시절 잔재)이라 보라색 배경에서 안 보였다 → tokens.css --sidebar-cap. 유저/어드민 사이드바 둘 다 어두워서 반투명 흰색으로 통일.
- 2026-09-01 정리: 앱명 "트래픽"(.env APP_NAME). 목업 데이터(공지·정보·게시글·캠페인·매체명·슬롯)는 전부 "테스트 N" — seed.py도 동일. 메인 배너 8구좌 슬라이더(4개 노출·3초 좌측 자동, dashboard.html+.banner-slider), 배너 이미지는 AD 플레이스홀더. 매체 뱃지 rec/best/new(인기·BEST·NEW, sale 폐기 — schema ENUM 변경). 키워드 도구 로그인 필수+하루 30회. 카카오 플로팅 버튼은 대시보드에서만. 대행의뢰 메뉴 임시 숨김(라우트는 유지, MENU에서만 제거). 게시글 상세 추천(vote)·채널 pill 제거, 목록 조회수는 "조회 N" 텍스트+고정폭 정렬. 인기 트래픽은 "이번 주 N건" 대신 매체별 익명 댓글 토론 — 2026-09-21 폐기, 후기(reviews)로 대체됨. 캠페인 생성은 스텝 아코디언(.cols.picked — 매체 선택 시 1열 요약 축소·2/3열 확장) + 효율 게이지(media.eff_level normal/good/best + eff_note 설명, 어드민 설정, 효율 수동% UI 폐기). 대행사 인증 신청은 마이페이지 카드(POST /community/agency/apply, back=/my).
- P4-c 메모: 네이버 검색광고 API는 services/naver_ad.py(HMAC 서명) + keyword_service(lookup/related 24h 캐시, 키 없거나 실패 시 결정적 더미, 더미는 캐시 안 함). 쿼터 keyword_service.quota(로그인 필수·개인당 하루 30회 고정 — 2026-09-01 JDH, keyword_query_log). 쇼핑 추적 슬롯은 생성 화면이 아니라 별도 메뉴 /campaign/store/slots("쇼핑 작업량 권장 체크", 2026-08-31 JDH 결정). 슬롯 갱신 refresh_all_slots(), 매체 효율 media_service.refresh_all_efficiency(), 미입금 만료 payment_service.expire_unpaid(), 의뢰 자동 마감 agency_model.close_stale() — P5에서 스케줄러 등록.
- P4-b 메모: 닉네임은 nick_service(preview→consume→register_post, 댓글은 pick). 마스킹 mask_service(전화·업체명·법인). 신고 3회 자동 블라인드(post_model.report). 알림 notify_service.push(유형별 users.notify_* 존중) — campaign_service.transition 훅, 댓글/답변/제안/수락/인증. /notifications + 헤더 종 배지(unread_count). 대행의뢰 제안은 admin 또는 users.is_agency만, 수락 시 accepted 제안자에게만 연락처 공개. 시리즈 읽음은 로그인 시 series_reads 테이블(세션 병합).
- P4-a 메모: 어드민은 blueprints/admin.py 한 파일(운영 현황·주문·결제/입금 확인·매체사·인기 트래픽·콘텐츠·배너·회원·신고). 모든 쓰기는 `_log()` → admin_log. 입금 계좌·기한은 settings 테이블(없으면 config BANK_INFO). 매체 로고 `static/uploads/media/<id>.<ext>`(정사각 검증, media_service). 콘텐츠 본문은 content_service.sanitize(bleach). 인기 트래픽은 popular_service.build(). scripts/campaign_admin.py는 삭제됨.
- P3 메모: 결제 모델 = 스펙 상단 v3.2 노트. `payment_service`(create/confirm_card/confirm_bank/refund/cancel_pending/expire_unpaid) + `services/pg/`(어댑터, 현재 mock). `campaign_service`(quote/create/update_pending/transition/reject/stop/cancel/record_rank/progress). 캠페인 상태: pay_wait·review·approved·running·rejected·done·stopped·cancelled. 운영 작업은 `scripts/campaign_admin.py` (P4-a에서 어드민 화면으로 이전 후 삭제). 검색량은 keyword_service 더미(해시) → P4-c에서 API.
- P1 메모: 대시보드 실시간 .strip은 스펙 v3에 따라 미렌더(CSS만 이식). 시리즈 읽음은 아직 session['series_reads'] (로그인 사용자용 series_reads 테이블 전환은 미완, P4 콘텐츠 작업 때 처리).
- P2 메모: 로그인 상태는 before_request → g.user, 템플릿 `current_user`. `login_required`/`admin_required`는 blueprints/auth.py. 최초 로그인 판정 = users.phone IS NULL → base.html이 welcome 모달 렌더. 카카오 키 없을 때 DEV_LOGIN=1+DEBUG에서만 /auth/dev-login?as=user|admin|new. 이메일 일반가입 병행(/auth/register, users.email+password_hash — 2026-08-31 JDH 결정, 스펙 '이메일 가입 없음' 폐기). 포인트 충전/승인 스크립트는 v3.1에서 폐기됨 — 마이페이지는 결제 내역(campaigns) 표시. 등급은 사업자/대행사/총판(users.grade biz/agency/master, 운영자 지정 — 결제액 자동 산정 폐기, 대행사 인증 승인 시 agency 자동).
- Windows 로컬: mysql CLI 없음 → `python scripts/seed.py --schema`로 스키마 적용.
