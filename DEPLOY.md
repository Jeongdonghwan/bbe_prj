# 배포 가이드 (MobaXterm → 리눅스 서버, 포트 8034)

고객 디자인 확인용 임시 배포 절차. Ubuntu/Debian 계열 기준.

## 1. 서버 접속
MobaXterm에서 SSH 세션으로 서버 접속.

## 2. 필수 패키지 (최초 1회)
```bash
sudo apt update
sudo apt install -y python3 python3-venv git mariadb-server
sudo systemctl enable --now mariadb
# DB 계정 생성 (비밀번호는 .env와 맞출 것)
sudo mariadb -e "CREATE USER IF NOT EXISTS 'traffic'@'localhost' IDENTIFIED BY '비밀번호'; GRANT ALL ON traffic_hub.* TO 'traffic'@'localhost'; GRANT CREATE ON *.* TO 'traffic'@'localhost'; FLUSH PRIVILEGES;"
```

## 3. 소스 받기 (최초 1회)
```bash
git clone https://github.com/Jeongdonghwan/bbe_prj.git
cd bbe_prj
cp .env.example .env
nano .env   # SECRET_KEY(랜덤 문자열), DB_USER, DB_PASSWORD 수정. FLASK_DEBUG=0, DEV_LOGIN=0 확인
```

## 4. 초기화 + 기동 (최초 1회)
```bash
bash scripts/deploy.sh --init   # venv + 의존성 + 스키마 + 테스트 데이터
```
성공하면 `[deploy] OK — http://서버IP:8034` 출력.

## 5. 방화벽 열기
```bash
sudo ufw allow 8034/tcp   # ufw 사용 시
```
클라우드(AWS/NCP 등)면 콘솔의 보안그룹/ACG에서 TCP 8034 인바운드 허용.

## 6. 접속 확인
브라우저에서 `http://서버IP:8034` — 고객에게 이 주소 전달.

## 이후 갱신 배포
```bash
cd bbe_prj
git pull
bash scripts/deploy.sh   # 재시작 (데이터 유지)
```

## 운영 명령
```bash
tail -f preview.log                  # 로그 보기
pkill -f scripts/serve_preview.py    # 중지
bash scripts/deploy.sh               # 시작/재시작
python scripts/seed.py               # 테스트 데이터 초기화(주의: 계정 포함 전체 리셋)
```

## 비고
- 서버는 waitress(WSGI)로 구동, 디버그·개발용 로그인(dev-login)은 꺼져 있음.
- 카카오 로그인을 쓰려면 카카오 콘솔에 `http://서버IP:8034/auth/kakao/callback` 리다이렉트 등록 + .env의 KAKAO_REST_KEY / KAKAO_REDIRECT_URI 수정. 미설정 시 이메일 가입/로그인으로 확인 가능.
- 결제는 mock PG라 카드 결제 완료 버튼은 디버그 전용 — 프리뷰에서는 무통장입금 흐름으로 확인.
