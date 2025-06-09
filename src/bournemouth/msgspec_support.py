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

_ENCODER = msgspec_json.Encoder()
_DECODER = msgspec_json.Decoder()


def _msgspec_loads_json_robust(content: bytes | str) -> typing.Any:
    try:
        return _DECODER.decode(content)
    except msgspec.DecodeError as ex:  # pragma: no cover - integration tested
        raise falcon.MediaMalformedError(
            falcon.MEDIA_JSON,
            title="Invalid JSON",
            description=f"The JSON payload is malformed: {ex!s}",
        ) from ex


def _dumps(obj: typing.Any) -> str:
    """Encode ``obj`` as JSON using msgspec's encoder."""

    return _ENCODER.encode(obj).decode("utf-8")


json_handler = falcon.media.JSONHandler(
    dumps=_dumps,
    loads=_msgspec_loads_json_robust,
)


class AsyncMsgspecMiddleware:
    async def process_resource(
        self,
        req: falcon.Request,
        resp: falcon.Response,
        resource: object,
        params: dict[str, typing.Any],
    ) -> None:
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
    raise falcon.HTTPUnprocessableEntity(
        title="Validation Error",
        description=str(ex),
    )


class MsgspecWebSocketMiddleware:
    def __init__(self, protocol: str = "json") -> None:
        if protocol != "json":
            raise ValueError(f"Unsupported msgspec protocol: {protocol}")
        self.encoder = msgspec_json.Encoder()
        self.decoder_cls = msgspec_json.Decoder

    async def process_resource_ws(
        self,
        req: falcon.asgi.Request,
        ws: falcon.asgi.WebSocket,
        resource: object,
        params: dict[str, typing.Any],
    ) -> None:
        req.context.msgspec_encoder = self.encoder
        req.context.msgspec_decoder_cls = self.decoder_cls
