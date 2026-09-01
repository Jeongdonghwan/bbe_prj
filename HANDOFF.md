# HANDOFF — 클로드코드 1차 개발 지시

## 파일 구성 (프로젝트 루트에 전부 넣기)
```
traffic-hub/
  CLAUDE.md              ← 클로드코드가 매번 읽는 규칙
  PROJECT_SPEC_v3.md     ← 기획·화면·DB·Phase 정의
  prototype_v3.html      ← 디자인 원본 (16화면, 하단 토글로 전환)
  HANDOFF.md             ← 이 파일
```

## 시작 명령 (프로젝트 폴더에서)
```
cd traffic-hub
claude
```

## 프롬프트 1 — P1 (레이아웃·대시보드·콘텐츠)
```
CLAUDE.md와 PROJECT_SPEC_v3.md의 0장, 1장, 2-1~2-2, 2-8의 마케팅 정보 부분, 3장, 4장, 5장, 6장 P1 행을 읽어.
그다음 prototype_v3.html을 열어 사이드바(.sidebar, 사용자/관리자 nav 분기), 헤더, #p-dash, #p-info 화면의 CSS·마크업을 파악해.

P1만 구현해:
1. Flask 앱 골격(5장 구조), config/.env.example, db.py, schema.sql 전체(4장 스키마 전부 — 이후 Phase도 쓰므로 지금 다 만든다), scripts/seed.py
2. prototype의 CSS를 static/css/tokens.css + base.css + components.css로 분리 이식. 클래스명·변수명 그대로.
3. layout/base.html, sidebar.html(MENU 상수 기반, 아코디언·active·관리자 분기), header.html, bottom_tab.html
4. 대시보드 / — 프로토타입 #p-dash 그대로, 데이터는 seed에서
5. 공지 목록·상세 /notice, 마케팅 정보 목록·상세 /community/info + 시리즈 사이드(읽음 체크는 로그인 없으니 세션 기반으로 임시)
6. 나머지 사이드바 링크는 전부 "준비 중" 플레이스홀더 페이지로 200 응답

하지 말 것: 로그인, 포인트, 캠페인, 커뮤니티 글쓰기, 어드민 기능. P2 이후 내용은 건드리지 않는다.
끝나면 실행 방법, 만든 파일 목록, 확인 체크리스트(6장 P1 완료 기준)를 출력하고 CLAUDE.md의 "현재 Phase"를 P1 완료로 갱신해.
```

## 프롬프트 2~5 (P1 확인 후 순서대로)
```
PROJECT_SPEC_v3.md 6장의 P2 행과 2-3, 2-9, 2-10을 읽고 prototype_v3.html의 #p-my를 참고해 P2를 구현해. 다른 Phase는 건드리지 마. 끝나면 실행 방법과 체크리스트를 출력하고 CLAUDE.md 현재 Phase를 갱신해.
```
```
P3: 6장 P3 행 + 2-4, 2-4-1, 2-5 + prototype #p-new, #p-store, #p-manage, #drawer.
```
```
P4: 6장 P4 행 + 2-4-2, 2-6, 2-7, 2-8 전체, 2-11 + prototype #p-popular, #p-anon, #p-qna, #p-agency, #p-adm*, #p-adm-popular.  (한 번에 크면 "P4-a 어드민 / P4-b 커뮤니티 / P4-c 키워드 도구"로 나눠서 시킨다)
```
```
P5: 6장 P5 행. 배치·PG·알림톡·배포.
```

## 중간에 쓰는 명령
- 화면이 프로토타입과 다르면: `prototype_v3.html의 #p-xxx와 지금 /xxx 화면을 비교해서 다른 부분을 표로 정리하고 프로토타입에 맞춰 고쳐.`
- 스펙 해석이 갈리면: `PROJECT_SPEC_v3.md 2-x 기준으로 어떻게 해석했는지 먼저 말하고 구현해.`
- 다음 세션 시작: `CLAUDE.md 읽고 현재 Phase 확인 후, 이전 세션에서 어디까지 됐는지 git log와 파일로 파악해서 요약해줘.`

## P3 전에 JDH가 정해줘야 하는 것
1. 매체사 실제 목록·단가 (seed 교체)
2. 순위 데이터 소스 (수동 입력으로 시작 가능)
3. 서비스명·도메인 (APP_NAME 상수 1곳)
