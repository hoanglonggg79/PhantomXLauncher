from __future__ import annotations

_SESSION_TOKEN: str = ""


def set_token(token: str) -> None:
    global _SESSION_TOKEN
    _SESSION_TOKEN = token


def get_token() -> str:
    return _SESSION_TOKEN
