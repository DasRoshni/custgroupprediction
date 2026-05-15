"""Unit tests for the FeatureBuilder — the leakage guard is the critical contract."""
from __future__ import annotations

import pandas as pd
import pytest

from customergroups.columns import PRE_CAMPAIGN_FEATURES, TARGET
from customergroups.features import (
    DIFF_FEATURES,
    ENGINEERED_FEATURES,
    RATIO_FEATURES,
    FeatureBuilder,
    LeakageError,
    SchemaError,
    swap_augment,
)


def _make_pre_campaign_df(n: int = 3) -> pd.DataFrame:
    """Build a tiny DF with only the 67 pre-campaign columns."""
    data = {c: [1.0] * n for c in PRE_CAMPAIGN_FEATURES}
    return pd.DataFrame(data)


def test_engineered_feature_count() -> None:
    assert len(PRE_CAMPAIGN_FEATURES) == 67
    assert len(DIFF_FEATURES) == 20
    assert len(RATIO_FEATURES) == 20
    assert len(ENGINEERED_FEATURES) == 107


def test_transform_happy_path_returns_deterministic_columns() -> None:
    df = _make_pre_campaign_df()
    X = FeatureBuilder().transform(df)
    assert list(X.columns) == ENGINEERED_FEATURES
    assert X.shape == (3, 107)


def test_leakage_guard_rejects_g1_21() -> None:
    df = _make_pre_campaign_df()
    df["g1_21"] = 0.5  # post-campaign
    with pytest.raises(LeakageError, match="g1_21"):
        FeatureBuilder().transform(df)


def test_leakage_guard_rejects_g2_21_and_c_28() -> None:
    df = _make_pre_campaign_df()
    for leak in ["g2_21", "c_28"]:
        bad = df.copy()
        bad[leak] = 1.0
        with pytest.raises(LeakageError, match=leak):
            FeatureBuilder().transform(bad)


def test_schema_error_when_missing_pre_campaign_column() -> None:
    df = _make_pre_campaign_df()
    df = df.drop(columns=["c_15"])
    with pytest.raises(SchemaError, match="c_15"):
        FeatureBuilder().transform(df)


def test_diff_features_are_correct() -> None:
    df = _make_pre_campaign_df()
    df.loc[0, "g1_5"] = 10.0
    df.loc[0, "g2_5"] = 3.0
    X = FeatureBuilder().transform(df)
    assert X.loc[0, "d_5"] == pytest.approx(7.0)


def test_ratio_handles_zero_denominator_without_inf() -> None:
    df = _make_pre_campaign_df()
    df.loc[0, "g1_2"] = 5.0
    df.loc[0, "g2_2"] = 0.0  # would produce inf without safe-divide
    X = FeatureBuilder().transform(df)
    assert pd.notna(X.loc[0, "r_2"])
    assert X.loc[0, "r_2"] not in (float("inf"), float("-inf"))


def test_swap_augment_doubles_rows_and_flips_target() -> None:
    df = _make_pre_campaign_df(n=4)
    df[TARGET] = [0, 1, 2, 1]
    aug = swap_augment(df)
    assert len(aug) == 8
    # original targets unchanged, swapped half flipped
    swapped_half = aug.iloc[4:][TARGET].tolist()
    assert swapped_half == [0, 2, 1, 2]


def test_swap_augment_swaps_g1_g2_columns() -> None:
    df = _make_pre_campaign_df(n=1)
    df.loc[0, "g1_3"] = 11.0
    df.loc[0, "g2_3"] = 99.0
    df[TARGET] = [1]
    aug = swap_augment(df)
    assert aug.loc[1, "g1_3"] == 99.0
    assert aug.loc[1, "g2_3"] == 11.0
