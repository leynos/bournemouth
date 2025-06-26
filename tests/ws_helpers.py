"""Utilities for asserting against WebSocket streams in pytest.

Spin up a background *pump* task that feeds every incoming frame into an
``asyncio.Queue``. Tests interact with that queue so the event loop is never
blocked waiting for a frame and deadlines are applied once per expectation.

Usage
-----
```
async with ws_collector(ws) as coll:
    await ws.send_json({"prompt": "Hello"})
    msgs = await coll.collect_until(lambda m: m.get("event") == "done")
    assert "".join(m["content"] for m in msgs if m["event"] == "chunk") \
        .startswith("Hello")
```

Licence: ISC (same as project)
"""
from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
import logging
from types import TracebackType
from typing import Any, Self

_logger = logging.getLogger(__name__)

_T = Callable[[Any], bool]


@dataclass(slots=True)
class _Pump:
    ws: Any
    q: asyncio.Queue[Any] = field(default_factory=asyncio.Queue)
    done: asyncio.Event = field(default_factory=asyncio.Event)
    _task: asyncio.Task[None] | None = None

    async def __aenter__(self) -> Self:
        self._task = asyncio.create_task(self._run(), name="ws-pump")
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None:
        await self.aclose()
        return False

    async def _run(self) -> None:
        try:
            while not self.ws.closed:
                raw = await self.ws.receive_text()
                try:
                    msg = json.loads(raw)
                except Exception:
                    msg = raw
                await self.q.put(msg)
        except Exception:  # pragma: no cover - defensive
            _logger.debug(
                "WebSocket pump terminated due to exception",
                exc_info=True,
            )
        finally:
            self.done.set()

    async def next(self, *, timeout: float | None = None) -> Any:
        """Return the next frame from the queue within ``timeout`` seconds."""
        if timeout is None:
            return await self.q.get()
        return await asyncio.wait_for(self.q.get(), timeout)

    def _remaining(self, deadline: float | None) -> float | None:
        if deadline is None:
            return None
        left = deadline - asyncio.get_event_loop().time()
        if left <= 0:
            raise TimeoutError("deadline reached")
        return left

    async def _get_next(self, left: float | None) -> Any:
        try:
            return await self.next(timeout=left)
        except asyncio.TimeoutError as exc:  # pragma: no cover - defensive
            raise TimeoutError("deadline reached") from exc

    async def collect(self, n: int | None = None, *, timeout: float | None = None) -> list[Any]:
        """Collect up to ``n`` messages until ``timeout`` or EOF."""
        deadline = asyncio.get_event_loop().time() + timeout if timeout else None
        out: list[Any] = []
        while n is None or len(out) < n:
            left = self._remaining(deadline)
            out.append(await self._get_next(left))
            if self.done.is_set() and self.q.empty():
                break
        return out

    async def collect_until(
        self, predicate: _T, *, timeout: float | None = 5.0
    ) -> list[Any]:
        """Collect messages until ``predicate`` returns ``True`` or times out."""
        msgs: list[Any] = []
        deadline: float | None = (
            asyncio.get_event_loop().time() + timeout if timeout else None
        )
        while True:
            if deadline is not None:
                left = deadline - asyncio.get_event_loop().time()
                if left <= 0:
                    raise TimeoutError("deadline reached")
            else:
                left = None
            msg = await self.next(timeout=left)
            msgs.append(msg)
            if predicate(msg):
                return msgs

    async def aclose(self) -> None:
        """Stop the pump task and close the WebSocket."""
        if self._task and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        if not self.ws.closed:
            await self.ws.close()


@contextlib.asynccontextmanager
async def ws_collector(ws: Any) -> AsyncIterator[_Pump]:
    """Collect messages from a WebSocket into a queue."""
    async with _Pump(ws) as pump:
        yield pump
