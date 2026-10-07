# SEO 콘텐츠 허브 (2026-10-07)

목표: 대행사 없이 마케팅을 직접 하려는 **사장님·판매자**가 검색으로 들어와 가입·캠페인 만들기로 이어지게.
타깃 키워드는 판매자 검색어("치과 마케팅", "스마트스토어 리뷰 늘리기"), 손님 검색량은 페이지 안의 근거 데이터.

## 구성

| 묶음 | 주소 | 수 | 근거 데이터 |
|---|---|---|---|
| 업종 허브 | `/learn/치과-마케팅/` | 54 | 업종 전국 손님 검색량, 지역별 수요, 업종 광고 규정 |
| 업종 × 각도 | `/learn/치과-리뷰-관리/` | 324 | 6각도(홍보-방법·플레이스-상위노출·리뷰-관리·네이버-광고·마케팅-비용·키워드-찾기) |
| 지역 × 업종 | `/learn/강남-치과-마케팅/` | 520 | 상권 손님 검색량·연관 키워드·지역 순위 |
| 지역 허브 | `/learn/강남-마케팅/` | ~105 | 상권 업종별 검색량 |
| 플랫폼 × 각도 | `/learn/스마트스토어-리뷰-늘리기/` | 20 | 판매자 검색량, 실제 매체 단가 |
| 쇼핑 카테고리 | `/learn/스마트스토어-무선청소기-판매/` | 42 | 구매자 검색량·세부 키워드 |
| 블로그 | `/blog/<slug>/` | 매일 | `content/blog/*.md` (루틴 자동 발행) |

## 파일

- 데이터: `data/seo/{place,biz,store,seller}.json` ← `scripts/seo_collect.py` (네이버 검색광고 키워드도구, `--seller` 로 판매자 키워드만)
- 페이지: `app/services/seo_pages.py` (문장 뱅크 + 빌더) → `app/blueprints/seo.py` → `templates/learn/*.html`
- 구조화 데이터: `app/services/jsonld.py` (Organization·WebSite·BreadcrumbList·FAQPage·ItemList·Article·Place·Service)
- 품질 게이트: `scripts/seo_check.py --learn [--fix]` / `--blog` (금지 표현·키워드 반복·글자수·title/desc 길이·h1·3-gram Jaccard ≤ 35%)
  — `--fix` 는 유사도로 걸린 페이지의 salt(`data/seo/salt.json`)를 올려 문장 조합을 바꾼다.
- 블로그 큐: `scripts/seo_keywords.py` → `content/keywords.json` + `content/keyword-cursor.json`, 실행 지침 `docs/BLOG_ROUTINE.md`
- 서버: `scripts/cron.py pull_content` (06:00·14:00, deploy.sh 가 crontab 등록)

## 기술 기준

- 주소는 끝 슬래시 통일(슬래시 없으면 308), canonical·og:url 은 `PUBLIC_URL` 기준 + 퍼센트 인코딩.
- 데이터에 없는 조합은 진짜 404 (soft 404 금지).
- `/sitemap.xml` 은 인덱스 → `sitemap-static/learn/blog.xml`. `/rss.xml` 블로그 최신 50편. robots 에 sitemap 명시.
- 서치어드바이저·서치콘솔 소유확인: `.env NAVER_SITE_VERIFICATION` / `GOOGLE_SITE_VERIFICATION`.

## 검색엔진 등록 순서

1. 네이버 서치어드바이저·구글 서치콘솔에 `https://셀프마이마케팅.kr` 등록 → 소유확인 메타 값을 `.env` 에 넣고 deploy.
2. 사이트맵 `https://xn--hz2ba848cszgbqko5fcyd.kr/sitemap.xml`, RSS `/rss.xml` 제출.
3. 네이버 수집 요청(하루 50개 한도) 순서: `/` → `/intro` → `/learn/` → 플랫폼 주제 20개 → 업종 허브 → 나머지는 사이트맵에 맡긴다.
4. 2주 뒤 색인 수·노출 키워드 확인 → 반응 좋은 묶음의 각도를 늘린다.
