"""Step 03 — Train LR baseline + XGBoost. Persist artifacts & metrics.

Run:
    python ml/scripts/03_train.py
"""
from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import asdict
from pathlib import Path

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml" / "src"))

from customergroups.columns import TARGET  # noqa: E402
from customergroups.data import load_curated_from_bq  # noqa: E402
from customergroups.features import FeatureBuilder  # noqa: E402
from customergroups.training import Trainer, baseline_always_group1  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def _load_training_data() -> pd.DataFrame:
    """Prefer BigQuery curated mart (built by dbt). Fall back to local parquet."""
    project_id = os.environ.get("PROJECT_ID")
    if project_id:
        dataset = os.environ.get("DATASET", "marketing")
        location = os.environ.get("BQ_LOCATION") or None
        try:
            return load_curated_from_bq(project_id, dataset, "campaigns_curated", location)
        except Exception:  # noqa: BLE001
            log.exception("BQ load failed — falling back to local parquet")

    parquet = ROOT / "data" / "processed" / "campaigns_curated.parquet"
    log.info("Loading curated features from %s", parquet)
    return pd.read_parquet(parquet)


def main() -> None:
    df = _load_training_data()
    log.info("Loaded %d rows × %d cols", *df.shape)

    fb = FeatureBuilder()
    trainer = Trainer(feature_builder=fb, augment=True)
    X_train, X_test, y_train, y_test = trainer.prepare_splits(df)
    log.info("Train: %s  Test: %s", X_train.shape, X_test.shape)

    baseline = baseline_always_group1(y_test.values)
    log.info("Baseline (always pick g1) success rate on test: %.4f", baseline)

    lr_result, lr_model = trainer.train_lr(X_train, y_train, X_test, y_test)
    xgb_result, xgb_model = trainer.train_xgb(X_train, y_train, X_test, y_test)

    # Pick the winner by test success rate
    winner_result, winner_model = max(
        [(lr_result, lr_model), (xgb_result, xgb_model)],
        key=lambda pair: pair[0].test_success_rate,
    )
    log.info("Winner: %s (success rate %.4f)", winner_result.name, winner_result.test_success_rate)

    # Persist artifacts
    art_dir = ROOT / "ml" / "artifacts"
    art_dir.mkdir(parents=True, exist_ok=True)

    joblib.dump(
        {"model": winner_model, "feature_builder": fb, "model_name": winner_result.name},
        art_dir / "model.joblib",
    )

    # Save metrics for both models + baseline
    metrics = {
        "baseline_always_g1_success_rate": baseline,
        "winner": winner_result.name,
        "improvement_pp": (winner_result.test_success_rate - baseline) * 100,
        "logistic_regression": asdict(lr_result),
        "xgboost": asdict(xgb_result),
    }
    (art_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))

    # Save feature importance CSV (winner)
    fi = pd.Series(winner_result.feature_importance).sort_values(ascending=False)
    fi.to_csv(art_dir / "feature_importance.csv", header=["importance"])

    # Confusion matrix plot for winner
    cm = np.array(winner_result.confusion)
    fig, ax = plt.subplots(figsize=(6, 5))
    sns.heatmap(
        cm, annot=True, fmt="d", cmap="Blues",
        xticklabels=["pred 0", "pred 1", "pred 2"],
        yticklabels=["true 0", "true 1", "true 2"],
        ax=ax,
    )
    ax.set_title(f"Confusion matrix — {winner_result.name}\n"
                 f"success rate {winner_result.test_success_rate:.3f}  "
                 f"(baseline {baseline:.3f})")
    fig.tight_layout()
    fig.savefig(art_dir / "confusion_matrix.png", dpi=120)
    plt.close(fig)

    # Print final comparison
    print("\n" + "=" * 60)
    print("FINAL RESULTS")
    print("=" * 60)
    print(f"Baseline (always pick g1):     {baseline:.4f}")
    print(f"Logistic Regression test:      acc={lr_result.test_accuracy:.4f}  f1m={lr_result.test_macro_f1:.4f}  success={lr_result.test_success_rate:.4f}")
    print(f"XGBoost test:                  acc={xgb_result.test_accuracy:.4f}  f1m={xgb_result.test_macro_f1:.4f}  success={xgb_result.test_success_rate:.4f}")
    print(f"\nWinner: {winner_result.name}")
    print(f"Improvement over baseline: +{(winner_result.test_success_rate - baseline) * 100:.2f} pp")
    print(f"\nArtifacts saved to: {art_dir}")


if __name__ == "__main__":
    main()
