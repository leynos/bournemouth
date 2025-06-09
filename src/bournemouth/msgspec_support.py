from __future__ import annotations

import typing

import falcon
import msgspec

__all__ = [
    "AsyncMsgspecMiddleware",
    "MsgspecProcessor",
    "MsgspecWebSocketMiddleware",
    "handle_msgspec_validation_error",
    "json_handler",
]

_ENCODER = msgspec.json.Encoder()
_DECODER = msgspec.json.Decoder()


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


class MsgspecProcessor:
    def __init__(
        self,
        encoder: msgspec.json.Encoder,
        decoder_factory: typing.Callable[
            [type[typing.Any]], msgspec.json.Decoder[typing.Any]
        ],
    ) -> None:
        self._encoder = encoder
        self._decoder_factory = decoder_factory

    async def receive_struct(
        self, ws: falcon.asgi.WebSocket, expected_type: type[typing.Any]
    ) -> typing.Any:
        raw_data = await ws.receive_text()
        decoder = self._decoder_factory(expected_type)
        return decoder.decode(raw_data)  # pyright: ignore[reportUnknownArgumentType]

    async def send_struct(
        self, ws: falcon.asgi.WebSocket, message: msgspec.Struct
    ) -> None:
        raw = self._encoder.encode(message)
        await ws.send_text(raw.decode("utf-8"))


class MsgspecWebSocketMiddleware:
    def __init__(self, protocol: str = "json") -> None:
        if protocol != "json":
            raise ValueError(f"Unsupported msgspec protocol: {protocol}")
        self._encoder = msgspec.json.Encoder()

        def factory(t: type[typing.Any]) -> msgspec.json.Decoder[typing.Any]:
            return msgspec.json.Decoder(t)

        self._decoder_factory = factory

    async def process_resource_ws(
        self,
        req: falcon.asgi.Request,
        ws: falcon.asgi.WebSocket,
        resource: object,
        params: dict[str, typing.Any],
    ) -> None:
        processor = MsgspecProcessor(self._encoder, self._decoder_factory)
        req.context.msgspec_processor = processor
