"""UUID generation utilities with fallback support.

Provide UUIDv7 generation using the :mod:`uuid-v7` library when available,
falling back to :func:`uuid.uuid4` otherwise.
"""

from __future__ import annotations
import uuid

try:
    from uuid_v7.base import uuid7 as _uuid7
except ImportError:  # pragma: no cover
    from uuid import uuid4 as _uuid7


def uuid7(*, return_type: str | None = None) -> uuid.UUID | str:
    """Return a UUIDv7 identifier or a string representation.

    Parameters
    ----------
    return_type : str or None, optional
        Specify ``"uuid"`` to return a :class:`uuid.UUID` object. Anything else
        yields the hex string.

    Returns
    -------
    uuid.UUID or str
        A UUID object or string value depending on ``return_type``.
    """
    u = _uuid7()
    return u if return_type == "uuid" else str(u)
