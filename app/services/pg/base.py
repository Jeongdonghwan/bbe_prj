"""PG adapter interface. Every provider (Toss, NicePay, Inicis...) implements these three calls."""
from dataclasses import dataclass


class PGError(Exception):
    pass


@dataclass
class PGResult:
    ok: bool
    tid: str | None = None
    message: str = ""
    raw: dict | None = None


class PGAdapter:
    name = "base"
    #: True when the provider needs a client-side widget/redirect before confirm().
    needs_client_flow = True

    def __init__(self, config):
        self.config = config

    def request(self, payment, campaign, user) -> dict:
        """Return parameters the client needs to open the PG window (order id, amount, keys...)."""
        raise NotImplementedError

    def confirm(self, payment, token: str | None) -> PGResult:
        """Server-side approval after the client flow. Must be idempotent per payment."""
        raise NotImplementedError

    def cancel(self, payment, amount: int, reason: str) -> PGResult:
        """Full or partial cancel of an approved payment."""
        raise NotImplementedError
