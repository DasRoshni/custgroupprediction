"""Prediction endpoints."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from app.core.errors import ModelNotReadyError
from app.schemas.prediction import (
    BatchRequest,
    BatchResponse,
    BatchResponseItem,
    CampaignFeatures,
    ModelInfoResponse,
    PredictionResponse,
)
from app.services.prediction_service import PredictionService

from .deps import get_prediction_service

router = APIRouter(prefix="/v1", tags=["predict"])
log = logging.getLogger(__name__)


@router.post("/predict", response_model=PredictionResponse)
def predict(
    features: CampaignFeatures,
    svc: PredictionService = Depends(get_prediction_service),
) -> PredictionResponse:
    if not svc.is_ready:
        raise ModelNotReadyError("Model not loaded")
    request_id = svc.new_request_id()
    result = svc.predict(features.model_dump())
    log.info(
        "Prediction served",
        extra={
            "request_id": request_id,
            "predicted_group": result["predicted_group"],
            "model_version": svc.metadata.get("model_version"),
        },
    )
    return PredictionResponse(
        predicted_group=result["predicted_group"],
        probabilities=result["probabilities"],
        model_version=svc.metadata.get("model_version", "unknown"),
        model_name=svc.metadata.get("model_name", "unknown"),
        request_id=request_id,
    )


@router.post("/predict/batch", response_model=BatchResponse)
def predict_batch(
    body: BatchRequest,
    svc: PredictionService = Depends(get_prediction_service),
) -> BatchResponse:
    if not svc.is_ready:
        raise ModelNotReadyError("Model not loaded")
    request_id = svc.new_request_id()
    items = [item.model_dump() for item in body.items]
    results = svc.predict_batch(items)
    log.info(
        "Batch prediction served",
        extra={"request_id": request_id, "n": len(results)},
    )
    return BatchResponse(
        predictions=[BatchResponseItem(**r) for r in results],
        model_version=svc.metadata.get("model_version", "unknown"),
        model_name=svc.metadata.get("model_name", "unknown"),
        request_id=request_id,
    )


@router.get("/model/info", response_model=ModelInfoResponse)
def model_info(svc: PredictionService = Depends(get_prediction_service)) -> ModelInfoResponse:
    if not svc.is_ready:
        raise ModelNotReadyError("Model not loaded")
    md = svc.metadata
    perf = md.get("performance", {})
    return ModelInfoResponse(
        model_name=md.get("model_name", "unknown"),
        model_version=md.get("model_version", "unknown"),
        trained_at=md.get("trained_at", "unknown"),
        test_success_rate=perf.get("test_success_rate", 0.0),
        baseline_success_rate=perf.get("baseline_success_rate", 0.0),
        improvement_pp=perf.get("improvement_pp", 0.0),
        test_accuracy=perf.get("test_accuracy", 0.0),
        test_macro_f1=perf.get("test_macro_f1", 0.0),
        artifact_sha256=md.get("artifact_sha256", "unknown"),
        required_features_count=md.get("input_schema", {}).get("count", 0),
    )
