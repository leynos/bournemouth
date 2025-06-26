from __future__ import annotations

import msgspec

# Centralised alias for msgspec.Struct used across the project.
Struct = msgspec.Struct  # pyright: ignore[reportUntypedBaseClass]

__all__ = ["Struct"]
