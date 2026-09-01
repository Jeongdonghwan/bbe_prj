# CLAUDE.md

## 프로젝트
리워드 트래픽 플랫폼. 스펙은 PROJECT_SPEC_v3.md, 디자인 원본은 prototype_v3.html — 코드 작성 전 반드시 해당 Phase 섹션과 프로토타입의 해당 화면(#p-xxx)을 읽는다. 프로토타입의 CSS 변수·클래스명을 그대로 쓴다(새 이름 만들지 말 것).

## 스택
- Python 3.11, Flask 3, Jinja2 SSR, pymysql, MariaDB 10.6, 바닐라 JS
- ORM 사용 금지. SQL은 app/models/ 안의 함수로만.
- CSS는 tokens.css 변수만 사용. 하드코딩 색상 금지.
- 아이콘은 Lucide만. 이미지 아이콘 금지.

## 규칙
- 포인트·선충전 개념 없음(스펙 v3.1 노트). 결제·취소는 services/payment_service 외 경로 금지 (P3에서 생성).
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
P4 완료 (2026-08-30, a·b·c 전부) → 다음 P5 운영(배치·실 PG·알림톡·리포트·배포)
- 2026-09-01 정리: 앱명 "트래픽"(.env APP_NAME). 목업 데이터(공지·정보·게시글·캠페인·매체명·슬롯)는 전부 "테스트 N" — seed.py도 동일. 메인 배너 8구좌 슬라이더(4개 노출·3초 좌측 자동, dashboard.html+.banner-slider), 배너 이미지는 AD 플레이스홀더. 매체 뱃지 rec/best/new(인기·BEST·NEW, sale 폐기 — schema ENUM 변경). 키워드 도구 로그인 필수+하루 30회. 카카오 플로팅 버튼은 대시보드에서만. 대행의뢰 메뉴 임시 숨김(라우트는 유지, MENU에서만 제거). 게시글 상세 추천(vote)·채널 pill 제거, 목록 조회수는 "조회 N" 텍스트+고정폭 정렬. 인기 트래픽은 "이번 주 N건" 대신 매체별 익명 댓글 토론(media_comments/media_nicks, nick_service.pick_media, POST /popular/comment). 캠페인 생성은 스텝 아코디언(.cols.picked — 매체 선택 시 1열 요약 축소·2/3열 확장) + 효율 게이지(media.eff_level normal/good/best + eff_note 설명, 어드민 설정, 효율 수동% UI 폐기). 대행사 인증 신청은 마이페이지 카드(POST /community/agency/apply, back=/my).
- P4-c 메모: 네이버 검색광고 API는 services/naver_ad.py(HMAC 서명) + keyword_service(lookup/related 24h 캐시, 키 없거나 실패 시 결정적 더미, 더미는 캐시 안 함). 쿼터 keyword_service.quota(로그인 필수·개인당 하루 30회 고정 — 2026-09-01 JDH, keyword_query_log). 쇼핑 추적 슬롯은 생성 화면이 아니라 별도 메뉴 /campaign/store/slots("쇼핑 작업량 권장 체크", 2026-08-31 JDH 결정). 슬롯 갱신 refresh_all_slots(), 매체 효율 media_service.refresh_all_efficiency(), 미입금 만료 payment_service.expire_unpaid(), 의뢰 자동 마감 agency_model.close_stale() — P5에서 스케줄러 등록.
- P4-b 메모: 닉네임은 nick_service(preview→consume→register_post, 댓글은 pick). 마스킹 mask_service(전화·업체명·법인). 신고 3회 자동 블라인드(post_model.report). 알림 notify_service.push(유형별 users.notify_* 존중) — campaign_service.transition 훅, 댓글/답변/제안/수락/인증. /notifications + 헤더 종 배지(unread_count). 대행의뢰 제안은 admin 또는 users.is_agency만, 수락 시 accepted 제안자에게만 연락처 공개. 시리즈 읽음은 로그인 시 series_reads 테이블(세션 병합).
- P4-a 메모: 어드민은 blueprints/admin.py 한 파일(운영 현황·주문·결제/입금 확인·매체사·인기 트래픽·콘텐츠·배너·회원·신고). 모든 쓰기는 `_log()` → admin_log. 입금 계좌·기한은 settings 테이블(없으면 config BANK_INFO). 매체 로고 `static/uploads/media/<id>.<ext>`(정사각 검증, media_service). 콘텐츠 본문은 content_service.sanitize(bleach). 인기 트래픽은 popular_service.build(). scripts/campaign_admin.py는 삭제됨.
- P3 메모: 결제 모델 = 스펙 상단 v3.2 노트. `payment_service`(create/confirm_card/confirm_bank/refund/cancel_pending/expire_unpaid) + `services/pg/`(어댑터, 현재 mock). `campaign_service`(quote/create/update_pending/transition/reject/stop/cancel/record_rank/progress). 캠페인 상태: pay_wait·review·approved·running·rejected·done·stopped·cancelled. 운영 작업은 `scripts/campaign_admin.py` (P4-a에서 어드민 화면으로 이전 후 삭제). 검색량은 keyword_service 더미(해시) → P4-c에서 API.
- P1 메모: 대시보드 실시간 .strip은 스펙 v3에 따라 미렌더(CSS만 이식). 시리즈 읽음은 아직 session['series_reads'] (로그인 사용자용 series_reads 테이블 전환은 미완, P4 콘텐츠 작업 때 처리).
- P2 메모: 로그인 상태는 before_request → g.user, 템플릿 `current_user`. `login_required`/`admin_required`는 blueprints/auth.py. 최초 로그인 판정 = users.phone IS NULL → base.html이 welcome 모달 렌더. 카카오 키 없을 때 DEV_LOGIN=1+DEBUG에서만 /auth/dev-login?as=user|admin|new. 이메일 일반가입 병행(/auth/register, users.email+password_hash — 2026-08-31 JDH 결정, 스펙 '이메일 가입 없음' 폐기). 포인트 충전/승인 스크립트는 v3.1에서 폐기됨 — 마이페이지는 결제 내역(campaigns) 표시. 등급은 사업자/대행사/총판(users.grade biz/agency/master, 운영자 지정 — 결제액 자동 산정 폐기, 대행사 인증 승인 시 agency 자동).
- Windows 로컬: mysql CLI 없음 → `python scripts/seed.py --schema`로 스키마 적용.
