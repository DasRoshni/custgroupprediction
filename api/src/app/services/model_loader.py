"""ModelLoader — Strategy pattern for loading model artifacts.

Two concrete implementations are wired in:
- `LocalJoblibLoader`: loads from a local path (dev, tests, in-container baked-in artifact).
- `GcsJoblibLoader`: loads from a GCS URI (prod default — fetched at startup).

The service code depends only on `ModelLoader` (the abstract base), so swapping
storage backends is config-only — no production code change required.
"""
from __future__ import annotations

import json
import logging
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class LoadedModel:
    model: Any
    feature_builder: Any
    metadata: dict[str, Any]


class ModelLoader(ABC):
    """Abstract loader. Implementations must return a LoadedModel."""

    @abstractmethod
    def load(self) -> LoadedModel: ...


class LocalJoblibLoader(ModelLoader):
    def __init__(self, model_path: Path, metadata_path: Path) -> None:
        self.model_path = Path(model_path)
        self.metadata_path = Path(metadata_path)

    def load(self) -> LoadedModel:
        if not self.model_path.exists():
            raise FileNotFoundError(f"Model not found at {self.model_path}")
        if not self.metadata_path.exists():
            raise FileNotFoundError(f"Metadata not found at {self.metadata_path}")
        log.info("Loading model from %s", self.model_path)
        bundle = joblib.load(self.model_path)
        metadata = json.loads(self.metadata_path.read_text())
        return LoadedModel(
            model=bundle["model"],
            feature_builder=bundle["feature_builder"],
            metadata=metadata,
        )


class GcsJoblibLoader(ModelLoader):
    """Production loader — pulls artifact from GCS at startup.

    Requires `google-cloud-storage`. Cloud Run service account needs
    `roles/storage.objectViewer` on the bucket.
    """

    def __init__(self, gcs_uri_model: str, gcs_uri_metadata: str) -> None:
        if not gcs_uri_model.startswith("gs://"):
            raise ValueError(f"Expected gs:// URI, got {gcs_uri_model}")
        self.gcs_uri_model = gcs_uri_model
        self.gcs_uri_metadata = gcs_uri_metadata

    def load(self) -> LoadedModel:
        try:
            from google.cloud import storage  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "GcsJoblibLoader requires `google-cloud-storage`. Add it to "
                "requirements.txt for prod deployments."
            ) from e

        client = storage.Client()

        def _download(uri: str, suffix: str) -> Path:
            bucket_name, _, blob_name = uri.removeprefix("gs://").partition("/")
            blob = client.bucket(bucket_name).blob(blob_name)
            tmp = Path(tempfile.mktemp(suffix=suffix))
            log.info("Downloading %s -> %s", uri, tmp)
            blob.download_to_filename(str(tmp))
            return tmp

        local_model = _download(self.gcs_uri_model, ".joblib")
        local_meta = _download(self.gcs_uri_metadata, ".json")
        bundle = joblib.load(local_model)
        metadata = json.loads(local_meta.read_text())
        return LoadedModel(
            model=bundle["model"],
            feature_builder=bundle["feature_builder"],
            metadata=metadata,
        )
