"""Shared pytest fixtures."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from customergroups.columns import PRE_CAMPAIGN_FEATURES

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def project_root() -> Path:
    return ROOT


@pytest.fixture(scope="session")
def raw_csv_path(project_root: Path) -> Path:
    return project_root / "data" / "raw" / "customerGroups.csv"


@pytest.fixture(scope="session")
def curated_parquet_path(project_root: Path) -> Path:
    return project_root / "data" / "processed" / "campaigns_curated.parquet"


@pytest.fixture(scope="session")
def sample_row(curated_parquet_path: Path) -> dict[str, Any]:
    """One real pre-campaign row, leakage columns stripped."""
    df = pd.read_parquet(curated_parquet_path).iloc[[0]]
    row = df[PRE_CAMPAIGN_FEATURES].iloc[0].to_dict()
    return {k: float(v) for k, v in row.items()}


@pytest.fixture(scope="session")
def client() -> TestClient:
    """FastAPI TestClient — triggers lifespan so the model is loaded."""
    from app.main import create_app  # imported lazily so settings env applies

    app = create_app()
    with TestClient(app) as c:
        yield c
