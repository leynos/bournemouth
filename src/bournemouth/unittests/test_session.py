"""Unit tests for session cookie management."""
from __future__ import annotations

from freezegun import freeze_time

from bournemouth.session import SessionManager


def test_cookie_roundtrip() -> None:
    """A generated cookie should round-trip correctly."""
    mgr = SessionManager("secret", 10)
    cookie = mgr.create_cookie("alice")
    assert mgr.verify_cookie(cookie) == "alice"


def test_cookie_expiry() -> None:
    """Expired cookies should not validate."""
    with freeze_time() as frozen:
        mgr = SessionManager("secret", 1)
        cookie = mgr.create_cookie("alice")
        frozen.tick(2)
        assert mgr.verify_cookie(cookie) is None


def test_cookie_bad_signature_with_different_secret() -> None:
    """Verification fails if the secret differs."""
    mgr1 = SessionManager("secret1", 10)
    mgr2 = SessionManager("secret2", 10)
    cookie = mgr1.create_cookie("alice")
    assert mgr2.verify_cookie(cookie) is None


def test_cookie_bad_signature_when_tampered() -> None:
    """Tampering with the cookie invalidates the signature."""
    mgr = SessionManager("secret", 10)
    cookie = mgr.create_cookie("alice")
    tampered = cookie + "tamper"
    assert mgr.verify_cookie(tampered) is None
