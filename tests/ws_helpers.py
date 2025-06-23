"""
Light-weight utilities for asserting against WebSocket streams in pytest.

Key idea
--------
Spin up a background *pump* task that feeds every incoming frame into
an asyncio.Queue.  Tests interact purely with that queue, so we never
block the event-loop on an unknown recv() – and we only apply a
deadline once per logical expectation, not on every frame.

Usage
-----
async with ws_collector(ws) as coll:
    await ws.send_json({"prompt": "Hello"})
    msgs = await coll.collect_until(lambda m: m.get("event") == "done")
    assert "".join(m["content"] for m in msgs if m["event"] == "chunk") \
           .startswith("Hello")

Licence: ISC (same as project)
"""
from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any, Self

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
        except Exception:
            pass
        finally:
            self.done.set()

    async def next(self, *, timeout: float | None = None) -> Any:
        if timeout is None:
            return await self.q.get()
        return await asyncio.wait_for(self.q.get(), timeout)

    async def collect(self, n: int | None = None, *, timeout: float | None = None) -> list[Any]:
        deadline: float | None = (
            asyncio.get_event_loop().time() + timeout if timeout else None
        )
        out: list[Any] = []
        while n is None or len(out) < n:
            if deadline is not None:
                left = deadline - asyncio.get_event_loop().time()
                if left <= 0:
                    raise TimeoutError("deadline reached")
            else:
                left = None
            try:
                msg = await self.next(timeout=left)
            except asyncio.TimeoutError as e:
                raise TimeoutError("deadline reached") from e
            out.append(msg)
            if self.done.is_set() and self.q.empty():
                break
        return out

    async def collect_until(
        self, predicate: _T, *, timeout: float | None = 5.0
    ) -> list[Any]:
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
        if self._task and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        if not self.ws.closed:
            await self.ws.close()


@contextlib.asynccontextmanager
async def ws_collector(ws: Any) -> AsyncIterator[_Pump]:
    async with _Pump(ws) as pump:
        yield pump
