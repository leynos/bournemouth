from __future__ import annotations

import typing

import falcon
import msgspec

__all__ = [
    "AsyncMsgspecMiddleware",
    "handle_msgspec_validation_error",
    "json_handler",
]

_ENCODER = msgspec.json.Encoder()
_DECODER = msgspec.json.Decoder()


def _msgspec_loads_json_robust(content: typing.Any) -> typing.Any:
    try:
        return _DECODER.decode(content)
    except msgspec.DecodeError as ex:  # pragma: no cover - integration tested
        raise falcon.MediaMalformedError(
            title="Invalid JSON",
            description=f"The JSON payload is malformed: {ex!s}",
        ) from ex


json_handler = falcon.media.JSONHandler(
    dumps=_ENCODER.encode,
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
        params[schema.__name__.lower()] = validated


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
