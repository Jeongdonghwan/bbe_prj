"""Application configuration loaded from .env."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")

    DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
    DB_PORT = int(os.getenv("DB_PORT", "3306"))
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_NAME = os.getenv("DB_NAME", "traffic_hub")
    DB_POOL_SIZE = 5

    # Service name is managed in exactly one place (spec 0).
    APP_NAME = os.getenv("APP_NAME", "비베네")
    KAKAO_CHAT_URL = os.getenv("KAKAO_CHAT_URL", "http://pf.kakao.com/_uuxgxaX/chat")

    PER_PAGE = 20

    # Dev bypass login (/auth/dev-login). Off by default — set DEV_LOGIN=1 (+ FLASK_DEBUG=1) to enable.
    DEV_LOGIN = os.getenv("DEV_LOGIN", "0") == "1"

    KAKAO_REST_KEY = os.getenv("KAKAO_REST_KEY", "")
    KAKAO_REDIRECT_URI = os.getenv("KAKAO_REDIRECT_URI", "http://127.0.0.1:5000/auth/kakao/callback")

    # PG adapter (services/pg). "mock" until a provider is chosen (P5).
    PG_PROVIDER = os.getenv("PG_PROVIDER", "mock")
    PG_CLIENT_KEY = os.getenv("PG_CLIENT_KEY", "")
    PG_SECRET_KEY = os.getenv("PG_SECRET_KEY", "")

    # Bank transfer account shown after a 무통장 order.
    BANK_INFO = {
        "bank": os.getenv("BANK_NAME", "국민은행"),
        "account": os.getenv("BANK_ACCOUNT", "000000-00-000000"),
        "holder": os.getenv("BANK_HOLDER", "트래픽허브"),
    }

    # Rank server partner API (product preview; 순위 연동은 docs/RANK_INTEGRATION.md).
    # Empty -> preview is skipped and the wizard falls back to manual entry.
    RANK_SERVER_URL = os.getenv("RANK_SERVER_URL", "")
    RANK_API_TOKEN = os.getenv("RANK_API_TOKEN", "")
    # 추적 슬롯은 순위 서버에서 `partner:bbe` 공용 계정을 쓴다. 우리가 지우면 트리플업 쪽
    # 추적도 끊기므로 기본은 끈다. 순위 서버 운영자와 합의한 뒤에만 켤 것.
    RANK_UNTRACK_ON_STOP = os.getenv("RANK_UNTRACK_ON_STOP", "0") == "1"

    # Naver Search Ad API (P4-c). Empty -> deterministic dummy data.
    NAVER_AD_ACCESS_LICENSE = os.getenv("NAVER_AD_ACCESS_LICENSE", "")
    NAVER_AD_SECRET_KEY = os.getenv("NAVER_AD_SECRET_KEY", "")
    NAVER_AD_CUSTOMER_ID = os.getenv("NAVER_AD_CUSTOMER_ID", "")
