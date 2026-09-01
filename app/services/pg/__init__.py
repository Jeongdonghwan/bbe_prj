"""PG adapter registry. Real providers are wired in P5; MockPG is used until then."""
from flask import current_app

from .base import PGAdapter, PGError
from .mock import MockPG

_PROVIDERS = {"mock": MockPG}


def get_adapter() -> PGAdapter:
    name = (current_app.config.get("PG_PROVIDER") or "mock").lower()
    cls = _PROVIDERS.get(name)
    if cls is None:
        raise PGError(f"unknown PG provider: {name}")
    return cls(current_app.config)


__all__ = ["get_adapter", "PGAdapter", "PGError"]
