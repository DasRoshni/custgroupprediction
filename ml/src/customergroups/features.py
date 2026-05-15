"""Feature engineering with leakage guard and swap augmentation.

The `FeatureBuilder` is shared by training and serving — single source of truth
so the production API can never drift from how the model was trained.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from .columns import (
    POST_CAMPAIGN,
    PRE_CAMPAIGN_FEATURES,
    TARGET,
)

log = logging.getLogger(__name__)

# Derived feature names — must stay deterministic for model reproducibility.
DIFF_FEATURES = [f"d_{i+1}" for i in range(20)]                    # g1_i - g2_i
RATIO_FEATURES = [f"r_{i+1}" for i in range(20)]                   # g1_i / g2_i (safe)

ENGINEERED_FEATURES = PRE_CAMPAIGN_FEATURES + DIFF_FEATURES + RATIO_FEATURES  # 67 + 20 + 20 = 107


class LeakageError(ValueError):
    """Raised when post-campaign columns are passed to feature building."""


class SchemaError(ValueError):
    """Raised when input is missing required pre-campaign columns."""


class FeatureBuilder:
    """Builds the model-ready feature matrix.

    Two guarantees:
      1. Will raise `LeakageError` if any post-campaign column is present.
      2. Output column order is deterministic — `ENGINEERED_FEATURES`.
    """

    EPS = 1e-6  # safe-divide epsilon for ratios

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        self._validate(df)

        out = df[PRE_CAMPAIGN_FEATURES].copy()

        # Difference features: g1_i - g2_i
        for i, name in enumerate(DIFF_FEATURES, start=1):
            out[name] = df[f"g1_{i}"] - df[f"g2_{i}"]

        # Ratio features: safe-divide
        for i, name in enumerate(RATIO_FEATURES, start=1):
            num = df[f"g1_{i}"].astype(float)
            den = df[f"g2_{i}"].astype(float)
            out[name] = num / (den + np.where(den >= 0, self.EPS, -self.EPS))

        # Replace inf with NaN, then NaN with 0 (some ratios can blow up if both ~0)
        out[RATIO_FEATURES] = (
            out[RATIO_FEATURES].replace([np.inf, -np.inf], np.nan).fillna(0.0)
        )

        # Final column order check
        return out[ENGINEERED_FEATURES]

    def _validate(self, df: pd.DataFrame) -> None:
        leaked = [c for c in POST_CAMPAIGN if c in df.columns]
        if leaked:
            raise LeakageError(
                f"Post-campaign columns present in input: {leaked}. "
                "These must never be features."
            )
        missing = [c for c in PRE_CAMPAIGN_FEATURES if c not in df.columns]
        if missing:
            raise SchemaError(f"Missing required pre-campaign columns: {missing}")


def swap_augment(df: pd.DataFrame) -> pd.DataFrame:
    """Return df + a swapped copy where g1↔g2 and target 1↔2.

    Use for training only. Comparison-symmetric features (c_*) are kept as-is,
    on the assumption that they were defined symmetrically. If any c_* feature is
    actually g1-vs-g2 directional, this assumption needs revisiting per-feature.

    Effect:
      - removes positional bias from training distribution (g1 wins 1.64x in raw)
      - doubles the training-set size for the model
    """
    if TARGET not in df.columns:
        raise ValueError("swap_augment requires the target column")

    swapped = df.copy()
    # Swap g1_i <-> g2_i for i = 1..21 (including post-campaign if present, we'll just keep names)
    rename: dict[str, str] = {}
    for i in range(1, 22):  # 1..21 covers pre + post
        g1, g2 = f"g1_{i}", f"g2_{i}"
        if g1 in swapped.columns and g2 in swapped.columns:
            rename[g1] = g2
            rename[g2] = g1
    swapped = swapped.rename(columns=rename)

    # Reorder columns back to original
    swapped = swapped[df.columns.tolist()]

    # Flip target labels 1 <-> 2; target 0 unchanged
    swapped[TARGET] = swapped[TARGET].replace({1: 2, 2: 1})

    augmented = pd.concat([df, swapped], ignore_index=True)
    log.info(
        "Swap-augmented: %d -> %d rows. Target distribution after augmentation:\n%s",
        len(df),
        len(augmented),
        augmented[TARGET].value_counts(normalize=True).sort_index().round(3).to_string(),
    )
    return augmented
