"""Data loading & curation. The leakage guard lives here."""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from .columns import POST_CAMPAIGN, PRE_CAMPAIGN_FEATURES, TARGET

log = logging.getLogger(__name__)

ALL_EXPECTED_COLS: list[str] = PRE_CAMPAIGN_FEATURES + POST_CAMPAIGN + [TARGET]


def load_curated_from_bq(
    project_id: str,
    dataset: str = "marketing",
    table: str = "campaigns_curated",
    location: str | None = None,
) -> pd.DataFrame:
    """Load the dbt-built curated table from BigQuery.

    The curated table already has dbt-engineered diff/ratio features and
    excludes post-campaign leakage columns. We strip those engineered features
    here so the Python `FeatureBuilder` regenerates them — keeping the
    serving-path feature engineering as the single source of truth.

    The stripped lineage metadata (`_*`) is also dropped before training.
    """
    from google.cloud import bigquery  # local import to keep optional

    client = bigquery.Client(project=project_id, location=location)
    fqtn = f"`{project_id}.{dataset}.{table}`"
    log.info("Loading curated features from %s", fqtn)
    # ORDER BY _record_hash for deterministic row order across runs (reproducible splits)
    df = client.query(
        f"SELECT * FROM {fqtn} ORDER BY _record_hash"
    ).to_dataframe()

    drop_cols = [
        c for c in df.columns
        if c.startswith("_") or c.startswith("d_") or c.startswith("r_")
    ]
    df = df.drop(columns=drop_cols)
    log.info(
        "Loaded %d rows × %d cols from BQ (dropped %d engineered/lineage cols)",
        len(df), df.shape[1], len(drop_cols),
    )
    return df


def load_raw_csv(path: str | Path) -> pd.DataFrame:
    """Load the source CSV with strict column validation."""
    df = pd.read_csv(path)
    missing = [c for c in ALL_EXPECTED_COLS if c not in df.columns]
    extra = [c for c in df.columns if c not in ALL_EXPECTED_COLS]
    if missing:
        raise ValueError(f"CSV missing expected columns: {missing}")
    if extra:
        raise ValueError(f"CSV has unexpected columns: {extra}")
    df[TARGET] = df[TARGET].astype(int)
    log.info("Loaded %d rows × %d cols from %s", len(df), df.shape[1], path)
    return df


def split_features_target(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Return (X, y) where X is **only** pre-campaign features. Leakage guard."""
    leaked = [c for c in POST_CAMPAIGN if c in df.columns]
    if leaked:
        log.warning("Dropping post-campaign columns (leakage): %s", leaked)
    X = df[PRE_CAMPAIGN_FEATURES].copy()
    y = df[TARGET].copy()
    return X, y


def write_curated(df: pd.DataFrame, out_dir: str | Path) -> dict[str, Path]:
    """Write the full curated parquet + a features-only parquet (post-campaign stripped)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    full_path = out_dir / "campaigns_curated.parquet"
    df.to_parquet(full_path, index=False)

    features_only_path = out_dir / "campaigns_features_only.parquet"
    df[PRE_CAMPAIGN_FEATURES + [TARGET]].to_parquet(features_only_path, index=False)

    log.info("Wrote %s and %s", full_path, features_only_path)
    return {"full": full_path, "features_only": features_only_path}
