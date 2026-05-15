"""Centralised exception handlers — map domain errors to HTTP responses."""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from customergroups.features import LeakageError, SchemaError

log = logging.getLogger(__name__)


class ModelNotReadyError(RuntimeError):
    """Service started but model artifact failed to load — return 503."""


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(LeakageError)
    async def _leakage(_: Request, exc: LeakageError) -> JSONResponse:
        log.warning("Leakage attempt: %s", exc)
        return JSONResponse(
            status_code=422,
            content={"error": "leakage_detected", "message": str(exc)},
        )

    @app.exception_handler(SchemaError)
    async def _schema(_: Request, exc: SchemaError) -> JSONResponse:
        log.warning("Schema error: %s", exc)
        return JSONResponse(
            status_code=422,
            content={"error": "schema_invalid", "message": str(exc)},
        )

    @app.exception_handler(ModelNotReadyError)
    async def _not_ready(_: Request, exc: ModelNotReadyError) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"error": "model_not_ready", "message": str(exc)},
        )
