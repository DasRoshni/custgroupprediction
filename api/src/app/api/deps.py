"""FastAPI dependency providers — service singletons resolved per request."""
from __future__ import annotations

from fastapi import Request

from app.services.prediction_service import PredictionService


def get_prediction_service(request: Request) -> PredictionService:
    """Return the singleton PredictionService stored on the app state."""
    svc: PredictionService = request.app.state.prediction_service
    return svc
