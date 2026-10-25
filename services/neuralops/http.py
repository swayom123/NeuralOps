import asyncio
import logging
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from .config import settings

logger = logging.getLogger("neuralops")


def envelope(request: Request, status: int, code: str, message: str):
    return JSONResponse(
        {
            "code": code,
            "message": message,
            "request_id": getattr(request.state, "request_id", ""),
        },
        status_code=status,
    )


class BodyLimit:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        # Buffer a strictly bounded body before parsing. Covers chunked uploads too.
        body, more = bytearray(), True
        if dict(scope.get("headers", [])).get(b"content-encoding", b"identity") != b"identity":
            response = JSONResponse(
                {
                    "code": "UNSUPPORTED_ENCODING",
                    "message": "Compressed requests are not accepted at this gateway.",
                    "request_id": str(uuid4()),
                },
                status_code=415,
            )
            return await response(scope, receive, send)
        try:
            async with asyncio.timeout(15):
                while more:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    body.extend(message.get("body", b""))
                    if len(body) > settings().max_body_bytes:
                        response = JSONResponse(
                            {
                                "code": "PAYLOAD_TOO_LARGE",
                                "message": "Request exceeds 1 MiB.",
                                "request_id": str(uuid4()),
                            },
                            status_code=413,
                        )
                        return await response(scope, receive, send)
                    more = message.get("more_body", False)
        except TimeoutError:
            response = JSONResponse(
                {
                    "code": "REQUEST_TIMEOUT",
                    "message": "Request body deadline exceeded.",
                    "request_id": str(uuid4()),
                },
                status_code=408,
            )
            return await response(scope, receive, send)
        delivered = False

        async def limited_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, limited_receive, send)


class Headers(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.request_id = str(uuid4())
        try:
            response = await call_next(request)
        except Exception:  # noqa: BLE001 — security/process boundary; redact error details
            # Do not log exception strings: database errors can include secret-bearing parameters.
            logger.error("request_failed request_id=%s", request.state.request_id)
            response = envelope(request, 503, "SERVICE_UNAVAILABLE", "Service unavailable. Retry later.")
        response.headers.update(
            {
                "x-request-id": request.state.request_id,
                "cache-control": "no-store",
                "x-content-type-options": "nosniff",
                "referrer-policy": "no-referrer",
                "x-frame-options": "DENY",
            }
        )
        if settings().environment == "production":
            response.headers["strict-transport-security"] = "max-age=31536000; includeSubDomains"
        return response


def configure(app: FastAPI):
    app.add_middleware(BodyLimit)
    app.add_middleware(Headers)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        if exc.status_code in {403, 404} and getattr(request.state, "organization_id", None):
            from .db import SessionLocal, audit, set_tenant

            with SessionLocal.begin() as db:
                set_tenant(db, request.state.organization_id)
                audit(
                    db,
                    request.state.organization_id,
                    request.state.actor,
                    "request.denied",
                    request.url.path[:128],
                    request.state.request_id,
                    "denied",
                )
        detail = (
            exc.detail
            if isinstance(exc.detail, dict)
            else {"code": "REQUEST_REJECTED", "message": str(exc.detail)}
        )
        return envelope(request, exc.status_code, detail["code"], detail["message"])

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return envelope(
            request,
            422,
            "VALIDATION_ERROR",
            "Invalid request fields. Check types, bounds and required values.",
        )
