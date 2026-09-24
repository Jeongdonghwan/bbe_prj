# 운영 점검 스크립트

배포 전/후에 실제 DB 를 상대로 돌린다. 만든 데이터는 스스로 지운다.

```bash
python tests/smoke.py       # 모든 화면 200 확인
python tests/ops_user.py    # 사용자 흐름 — 글쓰기·댓글·캠페인 생성·충전 요청·마이페이지
python tests/ops_admin.py   # 어드민 흐름 — 승인·반려·환불·순위·크레딧·콘텐츠·배너
python tests/ops_guard.py   # 권한 경계 — 비로그인·남의 자료·회원의 어드민 접근
python tests/rank_e2e.py    # 순위 추적 연동 (스텁 순위 서버를 띄워 확인)
```

주의: `ops_user`/`ops_admin` 은 실제로 캠페인을 만들고 크레딧을 차감·환불한다.
운영 DB 에서 돌리면 회원 1명의 잔액이 잠깐 바뀌었다 돌아온다. 되도록 점검용 DB 에서.
