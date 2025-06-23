from __future__ import annotations
import uuid

try:
    from uuid6 import uuid7 as _uuid7
except Exception:  # pragma: no cover
    from uuid import uuid4 as _uuid7


def uuid7(*, as_type: str | None = None) -> uuid.UUID | str:
    u = _uuid7()
    return u if as_type == "uuid" else str(u)
