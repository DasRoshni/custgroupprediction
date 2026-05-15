"""PredictionService — orchestrates feature build + model inference.

Depends only on the abstract `ModelLoader`, so storage backend can be swapped
without changing the service code.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

import pandas as pd

from .model_loader import LoadedModel, ModelLoader

log = logging.getLogger(__name__)


class PredictionService:
    """Holds a loaded model and exposes single + batch prediction."""

    def __init__(self, loader: ModelLoader) -> None:
        self._loader = loader
        self._loaded: LoadedModel | None = None

    # ----- lifecycle -----
    def load(self) -> None:
        """Eager-load on app startup. Raises if loading fails (fail-fast)."""
        self._loaded = self._loader.load()
        log.info(
            "Loaded model %s version %s",
            self._loaded.metadata.get("model_name"),
            self._loaded.metadata.get("model_version"),
        )

    @property
    def is_ready(self) -> bool:
        return self._loaded is not None

    @property
    def metadata(self) -> dict[str, Any]:
        if self._loaded is None:
            return {}
        return self._loaded.metadata

    # ----- inference -----
    def predict(self, features: dict[str, Any]) -> dict[str, Any]:
        return self.predict_batch([features])[0]

    def predict_batch(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if self._loaded is None:
            raise RuntimeError("Model not loaded — call load() first")

        df = pd.DataFrame(items)
        X = self._loaded.feature_builder.transform(df)
        probas = self._loaded.model.predict_proba(X)
        preds = probas.argmax(axis=1)

        out: list[dict[str, Any]] = []
        for i, (p, pr) in enumerate(zip(preds, probas)):
            out.append(
                {
                    "index": i,
                    "predicted_group": int(p),
                    "probabilities": {str(c): float(pr[c]) for c in range(len(pr))},
                }
            )
        return out

    @staticmethod
    def new_request_id() -> str:
        return uuid.uuid4().hex
