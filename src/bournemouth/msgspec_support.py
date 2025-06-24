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
    """
    Serialises a Python object to a JSON string using msgspec.
    
    Parameters
    ----------
    obj : typing.Any
        The Python object to serialise.
    
    Returns
    -------
    str
        A JSON-formatted string representation of the object.
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
        """
        Validates and converts the JSON request body to a msgspec.Struct instance based on the resource's schema attribute.
        
        If the resource defines a schema attribute for the current HTTP method (e.g., POST_SCHEMA) that is a subclass of msgspec.Struct, the request body is parsed and strictly validated against this schema. The validated object is injected into the params dictionary under the "body" key.
        """

        Parameters
        ----------
        req : falcon.Request
            The incoming HTTP request.
        resp : falcon.Response
            The HTTP response object.
        resource : object
            The resource object being processed.
        params : dict[str, typing.Any]
            The parameters dictionary where the validated body will be injected.
        schema_attr = f"{req.method.upper()}_SCHEMA"
        schema = getattr(resource, schema_attr, None)
        if schema is None:
            return
        if not isinstance(schema, type) or not issubclass(schema, msgspec.Struct):
            return
        media_data = await req.get_media()
        validated = msgspec.convert(media_data, schema, strict=True)
        params["body"] = validated



    Parameters
    ----------
    req : falcon.Request
        The HTTP request object.
    resp : falcon.Response
        The HTTP response object.
    ex : msgspec.ValidationError
        The validation error that occurred.
    params : dict[str, typing.Any]
        The request parameters.

    Raises

        Parameters
        ----------
        protocol : str, default="json"
            The protocol to use for WebSocket communication.
    ------
    falcon.HTTPUnprocessableEntity
        Always raised with the validation error details.
async def handle_msgspec_validation_error(
    req: falcon.Request,
    resp: falcon.Response,
    ex: msgspec.ValidationError,
    params: dict[str, typing.Any],
) -> None:
    """
    Raises an HTTP 422 Unprocessable Entity response when a msgspec validation error occurs.
    
    The response includes the validation error message in the description.

        Parameters
        ----------
        req : falcon.asgi.Request
            The ASGI request object.
        ws : falcon.asgi.WebSocket
            The WebSocket connection object.
        resource : object
            The WebSocket resource being processed.
        params : dict[str, typing.Any]
            The request parameters.
    """
    raise falcon.HTTPUnprocessableEntity(
        title="Validation Error",
        description=str(ex),
    )


class MsgspecWebSocketMiddleware:
    """Attach msgspec encoder/decoder to websocket requests."""

    def __init__(self, protocol: str = "json") -> None:
        """
        Initialises the middleware for msgspec-based WebSocket integration, supporting only the "json" protocol.
        
        Raises
        ------
        ValueError
            If a protocol other than "json" is specified.
        """
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
        """
        Attaches the msgspec encoder instance and decoder class to the request context for use in WebSocket resource handling.
        """
        req.context.msgspec_encoder = self.encoder
        req.context.msgspec_decoder_cls = self.decoder_cls
