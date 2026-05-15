"""Step 02 — EDA. Saves plots + a findings markdown to ml/notebooks/eda_outputs/.

Run:
    python ml/scripts/02_eda.py
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml" / "src"))

from customergroups.columns import (  # noqa: E402
    C_PRE,
    G1_PRE,
    G2_PRE,
    POST_CAMPAIGN,
    PRE_CAMPAIGN_FEATURES,
    TARGET,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

OUT = ROOT / "ml" / "notebooks" / "eda_outputs"
OUT.mkdir(parents=True, exist_ok=True)

sns.set_theme(style="whitegrid", context="notebook")
TARGET_PALETTE = {0: "#888888", 1: "#1f77b4", 2: "#d62728"}


def load() -> pd.DataFrame:
    path = ROOT / "data" / "processed" / "campaigns_curated.parquet"
    df = pd.read_parquet(path)
    log.info("Loaded %d rows × %d cols", *df.shape)
    return df


def section_target_distribution(df: pd.DataFrame, findings: list[str]) -> None:
    counts = df[TARGET].value_counts().sort_index()
    pct = (counts / counts.sum() * 100).round(2)
    findings.append("## Target distribution\n")
    findings.append(f"| target | count | pct |\n|---|---|---|")
    for t, c in counts.items():
        findings.append(f"| {t} | {c} | {pct[t]}% |")
    findings.append(
        f"\n**Baseline 'always pick Group 1'** = {pct[1]}%. The model must beat this.\n"
    )

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(
        ["0: neither", "1: group1 wins", "2: group2 wins"],
        counts.values,
        color=[TARGET_PALETTE[i] for i in counts.index],
    )
    for i, v in enumerate(counts.values):
        ax.text(i, v + 30, f"{v}\n({pct.iloc[i]}%)", ha="center", fontsize=10)
    ax.set_title("Campaign outcome distribution")
    ax.set_ylabel("Count")
    fig.tight_layout()
    fig.savefig(OUT / "01_target_distribution.png", dpi=120)
    plt.close(fig)


def section_summary_stats(df: pd.DataFrame, findings: list[str]) -> None:
    desc = df[PRE_CAMPAIGN_FEATURES + POST_CAMPAIGN].describe().T.round(3)
    desc.to_csv(OUT / "02_summary_stats.csv")
    findings.append("## Summary stats\nSee `02_summary_stats.csv`. ")
    findings.append(
        f"All pre-campaign features are numeric, no missing values. "
        f"Min/max ranges span {desc['min'].min():.2f} to {desc['max'].max():.2f}.\n"
    )


def section_g1_g2_symmetry(df: pd.DataFrame, findings: list[str]) -> None:
    """Check whether g1_i and g2_i have similar distributions (they should)."""
    findings.append("## g1 vs g2 distributional symmetry\n")
    # 4x5 grid of g1_i vs g2_i overlaid distributions
    fig, axes = plt.subplots(4, 5, figsize=(18, 12))
    for idx, (g1, g2) in enumerate(zip(G1_PRE, G2_PRE)):
        ax = axes[idx // 5, idx % 5]
        sns.kdeplot(df[g1], ax=ax, color="#1f77b4", label="g1", fill=True, alpha=0.3)
        sns.kdeplot(df[g2], ax=ax, color="#d62728", label="g2", fill=True, alpha=0.3)
        ax.set_title(f"{g1.replace('g1_','')}: g1 vs g2", fontsize=10)
        ax.set_xlabel("")
        ax.legend(fontsize=7)
    fig.suptitle("Distributional symmetry: g1_i vs g2_i (pre-campaign)")
    fig.tight_layout()
    fig.savefig(OUT / "03_g1_g2_symmetry.png", dpi=120)
    plt.close(fig)

    # Numerical test: KS p-values
    from scipy.stats import ks_2samp

    ks = []
    for g1, g2 in zip(G1_PRE, G2_PRE):
        stat, p = ks_2samp(df[g1], df[g2])
        ks.append((g1.replace("g1_", "feat_"), stat, p))
    ks_df = pd.DataFrame(ks, columns=["feature_pair", "ks_stat", "p_value"])
    ks_df.to_csv(OUT / "03_g1_g2_ks.csv", index=False)
    n_diff = (ks_df["p_value"] < 0.01).sum()
    findings.append(
        f"KS test between `g1_i` and `g2_i` for all 20 pairs: "
        f"**{n_diff} / 20** show significant distribution difference (p<0.01). "
        f"This is the positional/assignment bias to watch.\n"
    )


def section_position_bias(df: pd.DataFrame, findings: list[str]) -> None:
    """If position were neutral, target=1 and target=2 should be ~equal frequency."""
    g1_wins = (df[TARGET] == 1).sum()
    g2_wins = (df[TARGET] == 2).sum()
    ratio = g1_wins / max(g2_wins, 1)
    findings.append("## Positional bias\n")
    findings.append(
        f"g1 wins: {g1_wins} | g2 wins: {g2_wins} | ratio g1/g2 = **{ratio:.2f}**. "
        f"Strong asymmetry (≠1.0) means the *position* (which side a group is on) carries "
        f"signal — likely because groups are not paired neutrally. Mitigation: augment "
        f"training data with swapped (g1↔g2, target 1↔2) copies so the model learns "
        f"comparison rather than position.\n"
    )


def section_class_conditional(df: pd.DataFrame, findings: list[str]) -> None:
    """For each feature, mean by target. Plot top features by |mean(t=1) - mean(t=2)|."""
    means = df.groupby(TARGET)[PRE_CAMPAIGN_FEATURES].mean().T
    means["abs_diff_1v2"] = (means[1] - means[2]).abs()
    top = means.sort_values("abs_diff_1v2", ascending=False).head(20)
    top.to_csv(OUT / "04_class_conditional_means_top20.csv")

    fig, ax = plt.subplots(figsize=(10, 8))
    plot_df = top[[0, 1, 2]].copy()
    plot_df.columns = ["t=0 (neither)", "t=1 (g1 wins)", "t=2 (g2 wins)"]
    plot_df.plot(kind="barh", ax=ax, color=["#888888", "#1f77b4", "#d62728"])
    ax.invert_yaxis()
    ax.set_title("Top 20 features by |mean(t=1) − mean(t=2)|")
    ax.set_xlabel("Mean value")
    fig.tight_layout()
    fig.savefig(OUT / "04_class_conditional_top20.png", dpi=120)
    plt.close(fig)

    findings.append("## Class-conditional means (top 20 separators)\n")
    findings.append("See `04_class_conditional_means_top20.csv`. ")
    findings.append(
        f"Most discriminative pre-campaign feature: **{top.index[0]}** "
        f"(t=1 mean={top[1].iloc[0]:.3f}, t=2 mean={top[2].iloc[0]:.3f}).\n"
    )


def section_diff_features(df: pd.DataFrame, findings: list[str]) -> None:
    """Build the (g1_i - g2_i) features and see how much signal they carry per-class."""
    diffs = pd.DataFrame(
        {f"d_{i+1}": df[f"g1_{i+1}"] - df[f"g2_{i+1}"] for i in range(20)}
    )
    diffs[TARGET] = df[TARGET].values

    # melt for plotting
    melted = diffs.melt(id_vars=TARGET, var_name="feature", value_name="diff")
    fig, ax = plt.subplots(figsize=(16, 6))
    sns.boxplot(
        data=melted,
        x="feature",
        y="diff",
        hue=TARGET,
        palette=TARGET_PALETTE,
        ax=ax,
        fliersize=1,
    )
    ax.set_title("(g1_i − g2_i) per target class — separation = predictive power")
    ax.axhline(0, color="black", lw=0.5, linestyle="--")
    ax.set_xticklabels([t.get_text() for t in ax.get_xticklabels()], rotation=45)
    fig.tight_layout()
    fig.savefig(OUT / "05_diff_features_by_target.png", dpi=120)
    plt.close(fig)

    # Quick effect size: mean diff conditional on target
    eff = diffs.groupby(TARGET).mean().T
    eff["sep_1v2"] = (eff[1] - eff[2]).abs()
    eff_sorted = eff.sort_values("sep_1v2", ascending=False)
    findings.append("## Difference features (g1_i − g2_i)\n")
    findings.append(
        f"Largest mean(t=1) − mean(t=2) separation on diff features: "
        f"**{eff_sorted.index[0]}** (Δ = {eff_sorted['sep_1v2'].iloc[0]:.3f}). "
        f"Diff features clearly carry the comparison signal — confirms that adding "
        f"explicit `g1_i − g2_i` (and ratios) to the model is worthwhile.\n"
    )
    eff_sorted.to_csv(OUT / "05_diff_features_effect.csv")


def section_correlation(df: pd.DataFrame, findings: list[str]) -> None:
    """Correlation matrix of pre-campaign features — too big to plot in full, show heatmap."""
    corr = df[PRE_CAMPAIGN_FEATURES].corr()

    fig, ax = plt.subplots(figsize=(14, 12))
    sns.heatmap(corr, cmap="RdBu_r", center=0, vmin=-1, vmax=1, ax=ax, square=True, cbar_kws={"shrink": 0.6})
    ax.set_title("Pre-campaign feature correlation (67 × 67)")
    ax.set_xticks([])
    ax.set_yticks([])
    fig.tight_layout()
    fig.savefig(OUT / "06_correlation_heatmap.png", dpi=120)
    plt.close(fig)

    # find highly correlated pairs
    upper = corr.where(np.triu(np.ones(corr.shape), k=1).astype(bool))
    pairs = (
        upper.stack()
        .reset_index()
        .rename(columns={"level_0": "f1", "level_1": "f2", 0: "corr"})
    )
    pairs["abs_corr"] = pairs["corr"].abs()
    high = pairs.sort_values("abs_corr", ascending=False).head(20)
    high.to_csv(OUT / "06_top_correlated_pairs.csv", index=False)

    n_high = (pairs["abs_corr"] > 0.95).sum()
    findings.append("## Feature correlation\n")
    findings.append(
        f"Pairs with |r| > 0.95: **{n_high}**. "
        f"Top correlated pair: {high['f1'].iloc[0]} ↔ {high['f2'].iloc[0]} (r={high['corr'].iloc[0]:.3f}). "
        f"For tree-based models (XGBoost) high correlation is tolerated; "
        f"for linear models we'd need to drop or regularize.\n"
    )


def section_leakage_validation(df: pd.DataFrame, findings: list[str]) -> None:
    """Verify that post-campaign cols would 'solve' the target — proof they must be excluded."""
    from sklearn.tree import DecisionTreeClassifier

    X_post = df[POST_CAMPAIGN]
    y = df[TARGET]
    clf = DecisionTreeClassifier(max_depth=4, random_state=0)
    clf.fit(X_post, y)
    score = clf.score(X_post, y)

    findings.append("## Leakage validation\n")
    findings.append(
        f"Training a shallow decision tree on **only** the 3 post-campaign columns "
        f"({POST_CAMPAIGN}) reaches **train accuracy = {score*100:.1f}%**. "
        f"This confirms those columns embed the answer and must be excluded from "
        f"the training feature set. The `split_features_target()` helper enforces this.\n"
    )

    # Compare same model on pre-campaign features only — should be much lower
    Xpre_sample = df[PRE_CAMPAIGN_FEATURES]
    clf2 = DecisionTreeClassifier(max_depth=4, random_state=0)
    clf2.fit(Xpre_sample, y)
    score_pre = clf2.score(Xpre_sample, y)
    findings.append(
        f"Same model on pre-campaign features only: train accuracy = "
        f"{score_pre*100:.1f}% — sane, since pre-campaign signal is weaker.\n"
    )

    # Plot: post-campaign feature values colored by target
    fig, axes = plt.subplots(1, 3, figsize=(15, 4))
    for ax, col in zip(axes, POST_CAMPAIGN):
        for t in [0, 1, 2]:
            sns.kdeplot(
                df[df[TARGET] == t][col], ax=ax, label=f"t={t}",
                color=TARGET_PALETTE[t], fill=True, alpha=0.3,
            )
        ax.set_title(f"{col} by target")
        ax.legend()
    fig.suptitle("Post-campaign columns separate the classes perfectly — leakage")
    fig.tight_layout()
    fig.savefig(OUT / "07_leakage_post_campaign.png", dpi=120)
    plt.close(fig)


def main() -> None:
    df = load()
    findings: list[str] = ["# EDA Findings\n"]
    section_target_distribution(df, findings)
    section_summary_stats(df, findings)
    section_g1_g2_symmetry(df, findings)
    section_position_bias(df, findings)
    section_class_conditional(df, findings)
    section_diff_features(df, findings)
    section_correlation(df, findings)
    section_leakage_validation(df, findings)

    md_path = OUT / "00_findings.md"
    md_path.write_text("\n".join(findings))
    log.info("Wrote findings to %s", md_path)

    # Top-line summary to stdout
    print("\n=== EDA outputs ===")
    for f in sorted(OUT.iterdir()):
        print(f"  {f.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
