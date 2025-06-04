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


def test_cookie_bad_signature_with_different_secret() -> None:
    mgr1 = SessionManager("secret1", 10)
    mgr2 = SessionManager("secret2", 10)
    cookie = mgr1.create_cookie("alice")
    assert mgr2.verify_cookie(cookie) is None


def test_cookie_bad_signature_when_tampered() -> None:
    mgr = SessionManager("secret", 10)
    cookie = mgr.create_cookie("alice")
    tampered = cookie + "tamper"
    assert mgr.verify_cookie(tampered) is None
