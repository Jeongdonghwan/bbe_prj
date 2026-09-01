"""Mock PG: approves instantly. Used in development (DEBUG '모의 결제 성공' button) until a real PG is chosen."""
import secrets

from .base import PGAdapter, PGResult


class MockPG(PGAdapter):
    name = "mock"
    needs_client_flow = False

    def request(self, payment, campaign, user):
        return {"provider": "mock", "order_id": campaign["order_no"], "amount": payment["amount"]}

    def confirm(self, payment, token=None):
        return PGResult(ok=True, tid=f"MOCK-{secrets.token_hex(6).upper()}", message="mock approved")

    def cancel(self, payment, amount, reason):
        return PGResult(ok=True, tid=payment.get("pg_tid"), message=f"mock cancelled {amount}")
