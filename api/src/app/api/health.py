"""Health & readiness endpoints — required by Cloud Run."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.schemas.prediction import HealthResponse, ReadyResponse
from app.services.prediction_service import PredictionService

from .deps import get_prediction_service

router = APIRouter(tags=["health"])


@router.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    """Liveness — process is up. Cloud Run probes this."""
    return HealthResponse(status="ok")


@router.get("/readyz", response_model=ReadyResponse)
def readyz(svc: PredictionService = Depends(get_prediction_service)) -> ReadyResponse:
    """Readiness — model loaded. Used by Cloud Run startup probe."""
    if not svc.is_ready:
        return ReadyResponse(status="not_ready", model_loaded=False, model_version=None)
    return ReadyResponse(
        status="ready",
        model_loaded=True,
        model_version=svc.metadata.get("model_version"),
    )
