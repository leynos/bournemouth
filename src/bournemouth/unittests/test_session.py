from __future__ import annotations

import time

from bournemouth.session import SessionManager


def test_cookie_roundtrip() -> None:
    mgr = SessionManager("secret", 10)
    cookie = mgr.create_cookie("alice")
    assert mgr.verify_cookie(cookie) == "alice"


def test_cookie_expiry() -> None:
    mgr = SessionManager("secret", 1)
    cookie = mgr.create_cookie("alice")
    time.sleep(2)
    assert mgr.verify_cookie(cookie) is None
