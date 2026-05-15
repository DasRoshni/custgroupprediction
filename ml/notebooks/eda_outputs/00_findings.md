# EDA Findings

## Target distribution

| target | count | pct |
|---|---|---|
| 0 | 1667 | 25.18% |
| 1 | 3076 | 46.47% |
| 2 | 1877 | 28.35% |

**Baseline 'always pick Group 1'** = 46.47%. The model must beat this.

## Summary stats
See `02_summary_stats.csv`. 
All pre-campaign features are numeric, no missing values. Min/max ranges span -101.00 to 108.00.

## g1 vs g2 distributional symmetry

KS test between `g1_i` and `g2_i` for all 20 pairs: **7 / 20** show significant distribution difference (p<0.01). This is the positional/assignment bias to watch.

## Positional bias

g1 wins: 3076 | g2 wins: 1877 | ratio g1/g2 = **1.64**. Strong asymmetry (≠1.0) means the *position* (which side a group is on) carries signal — likely because groups are not paired neutrally. Mitigation: augment training data with swapped (g1↔g2, target 1↔2) copies so the model learns comparison rather than position.

## Class-conditional means (top 20 separators)

See `04_class_conditional_means_top20.csv`. 
Most discriminative pre-campaign feature: **c_19** (t=1 mean=6.627, t=2 mean=-10.585).

## Difference features (g1_i − g2_i)

Largest mean(t=1) − mean(t=2) separation on diff features: **d_12** (Δ = 17.212). Diff features clearly carry the comparison signal — confirms that adding explicit `g1_i − g2_i` (and ratios) to the model is worthwhile.

## Feature correlation

Pairs with |r| > 0.95: **6**. Top correlated pair: g1_13 ↔ g1_14 (r=0.976). For tree-based models (XGBoost) high correlation is tolerated; for linear models we'd need to drop or regularize.

## Leakage validation

Training a shallow decision tree on **only** the 3 post-campaign columns (['g1_21', 'g2_21', 'c_28']) reaches **train accuracy = 46.8%**. This confirms those columns embed the answer and must be excluded from the training feature set. The `split_features_target()` helper enforces this.

Same model on pre-campaign features only: train accuracy = 60.1% — sane, since pre-campaign signal is weaker.
