"""Unit tests for ModelLoader implementations."""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import pytest

from app.services.model_loader import LocalJoblibLoader
from customergroups.features import FeatureBuilder


def test_local_loader_round_trip(tmp_path: Path) -> None:
    model_path = tmp_path / "model.joblib"
    meta_path = tmp_path / "metadata.json"

    joblib.dump(
        {"model": "dummy-model", "feature_builder": FeatureBuilder(), "model_name": "xgb"},
        model_path,
    )
    meta_path.write_text(json.dumps({"model_name": "xgb", "model_version": "9.9.9"}))

    loaded = LocalJoblibLoader(model_path, meta_path).load()
    assert loaded.model == "dummy-model"
    assert isinstance(loaded.feature_builder, FeatureBuilder)
    assert loaded.metadata["model_version"] == "9.9.9"


def test_local_loader_raises_when_model_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        LocalJoblibLoader(
            tmp_path / "missing.joblib", tmp_path / "missing.json"
        ).load()


def test_local_loader_raises_when_metadata_missing(tmp_path: Path) -> None:
    model_path = tmp_path / "m.joblib"
    joblib.dump({"model": "x", "feature_builder": FeatureBuilder(), "model_name": "n"}, model_path)
    with pytest.raises(FileNotFoundError):
        LocalJoblibLoader(model_path, tmp_path / "missing.json").load()
