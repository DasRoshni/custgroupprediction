"""Step 01 — Curate raw CSV → parquet (full + features-only).

Run:
    python ml/scripts/01_curate.py
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml" / "src"))

from customergroups.data import load_raw_csv, write_curated  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def main() -> None:
    raw = ROOT / "data" / "raw" / "customerGroups.csv"
    out = ROOT / "data" / "processed"

    df = load_raw_csv(raw)
    print(f"Rows: {len(df):,}   Cols: {df.shape[1]}")
    print("Target distribution:")
    print(df["target"].value_counts(normalize=True).sort_index().mul(100).round(2).to_string())
    print()
    paths = write_curated(df, out)
    print("Wrote:")
    for k, v in paths.items():
        print(f"  {k}: {v.relative_to(ROOT)}  ({v.stat().st_size/1024:.1f} KB)")


if __name__ == "__main__":
    main()
