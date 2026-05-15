"""Unit tests for PredictionService — uses a mock model + the real FeatureBuilder."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pytest

from app.services.model_loader import LoadedModel, ModelLoader
from app.services.prediction_service import PredictionService
from customergroups.features import FeatureBuilder


@dataclass
class _MockModel:
    """Simulates predict_proba — returns a fixed probability vector regardless of input."""

    proba: np.ndarray

    def predict_proba(self, X: Any) -> np.ndarray:
        # Repeat the fixed proba for each input row
        return np.tile(self.proba, (len(X), 1))


class _StubLoader(ModelLoader):
    def __init__(self, proba: list[float]) -> None:
        self._proba = np.array(proba)

    def load(self) -> LoadedModel:
        return LoadedModel(
            model=_MockModel(proba=self._proba),
            feature_builder=FeatureBuilder(),
            metadata={"model_name": "stub", "model_version": "test-1"},
        )


def _make_payload() -> dict[str, float]:
    from customergroups.columns import PRE_CAMPAIGN_FEATURES

    return {c: 1.0 for c in PRE_CAMPAIGN_FEATURES}


def test_is_ready_false_before_load() -> None:
    svc = PredictionService(_StubLoader([0.2, 0.5, 0.3]))
    assert svc.is_ready is False
    assert svc.metadata == {}


def test_predict_raises_when_not_loaded() -> None:
    svc = PredictionService(_StubLoader([0.2, 0.5, 0.3]))
    with pytest.raises(RuntimeError, match="not loaded"):
        svc.predict(_make_payload())


def test_predict_returns_argmax_class() -> None:
    svc = PredictionService(_StubLoader([0.1, 0.7, 0.2]))
    svc.load()
    out = svc.predict(_make_payload())
    assert out["predicted_group"] == 1
    assert out["probabilities"]["1"] == pytest.approx(0.7, rel=1e-3)


def test_predict_batch_returns_indexed_predictions() -> None:
    svc = PredictionService(_StubLoader([0.05, 0.05, 0.9]))
    svc.load()
    payloads = [_make_payload(), _make_payload(), _make_payload()]
    out = svc.predict_batch(payloads)
    assert len(out) == 3
    assert [r["index"] for r in out] == [0, 1, 2]
    assert all(r["predicted_group"] == 2 for r in out)


def test_request_id_is_unique() -> None:
    ids = {PredictionService.new_request_id() for _ in range(100)}
    assert len(ids) == 100
