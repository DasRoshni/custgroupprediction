"""Column definitions — single source of truth for feature/leakage groupings."""
from __future__ import annotations

G1_PRE = [f"g1_{i}" for i in range(1, 21)]          # g1_1..g1_20
G2_PRE = [f"g2_{i}" for i in range(1, 21)]          # g2_1..g2_20
C_PRE = [f"c_{i}" for i in range(1, 28)]            # c_1..c_27

POST_CAMPAIGN = ["g1_21", "g2_21", "c_28"]          # MUST be dropped from training features
TARGET = "target"

PRE_CAMPAIGN_FEATURES: list[str] = G1_PRE + G2_PRE + C_PRE  # 20 + 20 + 27 = 67? actually 20+20+27 = 67
# correction: g1 pre = 20, g2 pre = 20, c pre = 27 → 67 features.
# (Per the brief: g1_1..g1_20 pre, g2_1..g2_20 pre, c_1..c_27 pre.)

assert len(PRE_CAMPAIGN_FEATURES) == 67, (
    f"Expected 67 pre-campaign features, got {len(PRE_CAMPAIGN_FEATURES)}"
)
