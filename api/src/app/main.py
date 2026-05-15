"""FastAPI application factory + startup wiring."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.predict import router as predict_router
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.services.model_loader import LocalJoblibLoader
from app.services.prediction_service import PredictionService

log = logging.getLogger(__name__)


def _build_loader(settings: Settings):
    """Pick the loader strategy based on env config.

    - `MODEL_PATH=gs://...`  -> GcsJoblibLoader (prod default on Cloud Run)
    - otherwise              -> LocalJoblibLoader (dev/test)
    """
    model_path = str(settings.model_path)
    if model_path.startswith("gs://"):
        from app.services.model_loader import GcsJoblibLoader
        return GcsJoblibLoader(
            gcs_uri_model=model_path,
            gcs_uri_metadata=str(settings.metadata_path),
        )
    return LocalJoblibLoader(
        model_path=settings.model_path, metadata_path=settings.metadata_path
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    log.info("Starting %s (env=%s)", settings.app_name, settings.environment)

    loader = _build_loader(settings)
    svc = PredictionService(loader=loader)
    try:
        svc.load()
        app.state.prediction_service = svc
        log.info("Prediction service ready")
    except Exception:
        log.exception("Failed to load model — service will respond 503 on /predict")
        app.state.prediction_service = svc  # not ready, but app still serves /healthz

    yield

    log.info("Shutting down %s", settings.app_name)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Customer Group Predictor",
        version="0.1.0",
        description="Predicts which customer group to target in a marketing campaign.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(predict_router)

    if settings.enable_metrics:
        try:
            from prometheus_fastapi_instrumentator import Instrumentator
            Instrumentator().instrument(app).expose(app, endpoint="/metrics")
        except ImportError:
            log.warning("prometheus_fastapi_instrumentator not installed — /metrics disabled")

    return app


app = create_app()
