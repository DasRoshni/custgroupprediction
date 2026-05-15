"""Step 04 — Wrap the model artifact with metadata for the API service to consume.

Run:
    python ml/scripts/04_finalize_artifact.py
"""
from __future__ import annotations

import hashlib
import json
import logging
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml" / "src"))

from customergroups import __version__ as pkg_version  # noqa: E402
from customergroups.columns import PRE_CAMPAIGN_FEATURES  # noqa: E402
from customergroups.features import ENGINEERED_FEATURES  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def _git_sha() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return None


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    art = ROOT / "ml" / "artifacts"
    model_path = art / "model.joblib"
    metrics_path = art / "metrics.json"

    bundle = joblib.load(model_path)
    metrics = json.loads(metrics_path.read_text())

    metadata = {
        "model_name": bundle["model_name"],
        "model_version": "1.0.0",
        "package_version": pkg_version,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": _git_sha(),
        "python": platform.python_version(),
        "input_schema": {
            "required_features": PRE_CAMPAIGN_FEATURES,
            "count": len(PRE_CAMPAIGN_FEATURES),
            "post_campaign_columns_forbidden": ["g1_21", "g2_21", "c_28"],
        },
        "engineered_features": {
            "names": ENGINEERED_FEATURES,
            "count": len(ENGINEERED_FEATURES),
        },
        "performance": {
            "baseline_success_rate": metrics["baseline_always_g1_success_rate"],
            "test_success_rate": metrics[bundle["model_name"]]["test_success_rate"],
            "test_accuracy": metrics[bundle["model_name"]]["test_accuracy"],
            "test_macro_f1": metrics[bundle["model_name"]]["test_macro_f1"],
            "improvement_pp": metrics["improvement_pp"],
            "cv_accuracy_mean": metrics[bundle["model_name"]]["cv_accuracy_mean"],
            "cv_accuracy_std": metrics[bundle["model_name"]]["cv_accuracy_std"],
        },
        "artifact_sha256": _file_sha256(model_path),
    }

    out = art / "metadata.json"
    out.write_text(json.dumps(metadata, indent=2))
    log.info("Wrote %s", out)
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
