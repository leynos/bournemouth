"""Integrate msgspec serialization with Falcon."""

from __future__ import annotations

import typing

import falcon
import falcon.asgi
import falcon.media
import msgspec
from msgspec import json as msgspec_json

__all__ = [
    "AsyncMsgspecMiddleware",
    "MsgspecWebSocketMiddleware",
    "handle_msgspec_validation_error",
    "json_handler",
]


class UnsupportedMsgspecProtocolError(ValueError):
    """Raised when an unsupported msgspec protocol is requested."""

    def __init__(self, protocol: str) -> None:
        super().__init__(f"Unsupported msgspec protocol: {protocol}")


_ENCODER = msgspec_json.Encoder()
_DECODER = msgspec_json.Decoder()


def _msgspec_loads_json_robust(
    content: bytes | str,
) -> dict[str, typing.Any] | list[typing.Any] | str | int | float | bool | None:
    try:
        return _DECODER.decode(content)
    except msgspec.DecodeError as ex:  # pragma: no cover - integration tested
        raise falcon.MediaMalformedError(
            falcon.MEDIA_JSON,
            title="Invalid JSON",
            description=f"The JSON payload is malformed: {ex!s}",
        ) from ex


def _dumps(
    obj: dict[str, typing.Any] | list[typing.Any] | str | int | float | bool | None,
) -> str:
    """Encode ``obj`` as JSON using msgspec's encoder."""
    return _ENCODER.encode(obj).decode("utf-8")


json_handler = falcon.media.JSONHandler(
    dumps=_dumps,
    loads=_msgspec_loads_json_robust,
)


class AsyncMsgspecMiddleware:
    """Validate request bodies using msgspec schemas."""

    async def process_resource(
        self,
        req: falcon.Request,
        resp: falcon.Response,
        resource: object,
        params: dict[str, typing.Any],
    ) -> None:
        """Convert JSON request bodies to ``msgspec.Struct`` instances.

        Parameters
        ----------
        req:
            Incoming HTTP request.
        resp:
            HTTP response object (unused).
        resource:
            The resource handling the request.
        params:
            Parameter dictionary passed to the resource.
        """
        schema_attr = f"{req.method.upper()}_SCHEMA"
        schema = getattr(resource, schema_attr, None)
        if schema is None:
            return
        if not isinstance(schema, type) or not issubclass(schema, msgspec.Struct):
            return
        media_data = await req.get_media()
        validated = msgspec.convert(media_data, schema, strict=True)
        params["body"] = validated


async def handle_msgspec_validation_error(
    req: falcon.Request,
    resp: falcon.Response,
    ex: msgspec.ValidationError,
    params: dict[str, typing.Any],
) -> None:
    """Return a ``422`` response when msgspec validation fails.

    Parameters
    ----------
    req:
        Request that triggered the validation error.
    resp:
        Response object used to send the error.
    ex:
        The validation error raised by ``msgspec``.
    params:
        Parameters dictionary passed to the handler.
    """
    raise falcon.HTTPUnprocessableEntity(
        title="Validation Error",
        description=str(ex),
    )


class MsgspecWebSocketMiddleware:
    """Attach msgspec encoder/decoder to websocket requests."""

    def __init__(self, protocol: str = "json") -> None:
        """Create middleware for encoding and decoding WebSocket payloads.

        Parameters
        ----------
        protocol : str, optional
            Encoding protocol to use. Only ``"json"`` is supported.
        """
        if protocol != "json":
            raise UnsupportedMsgspecProtocolError(protocol)
        self.encoder = msgspec_json.Encoder()
        self.decoder_cls = msgspec_json.Decoder

    async def process_resource_ws(
        self,
        req: falcon.asgi.Request,
        ws: falcon.asgi.WebSocket,
        resource: object,
        params: dict[str, typing.Any],
    ) -> None:
        """Expose encoder and decoder classes via ``req.context``.

        Parameters
        ----------
        req:
            Incoming WebSocket request.
        ws:
            WebSocket connection instance.
        resource:
            The websocket resource.
        params:
            Parameter dictionary passed to the resource.
        """
        req.context.msgspec_encoder = self.encoder
        req.context.msgspec_decoder_cls = self.decoder_cls
