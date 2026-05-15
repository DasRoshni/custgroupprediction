"""Integration tests — hit the FastAPI app via TestClient with the real model loaded."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


pytestmark = pytest.mark.integration


def test_healthz(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_readyz_reports_ready(client: TestClient) -> None:
    r = client.get("/readyz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ready"
    assert body["model_loaded"] is True
    assert body["model_version"] is not None


def test_model_info_includes_perf_metrics(client: TestClient) -> None:
    r = client.get("/v1/model/info")
    assert r.status_code == 200
    body = r.json()
    assert body["model_name"] == "xgboost"
    assert body["required_features_count"] == 67
    assert body["test_success_rate"] > body["baseline_success_rate"]
    assert body["improvement_pp"] > 0


def test_predict_happy_path(client: TestClient, sample_row: dict[str, float]) -> None:
    r = client.post("/v1/predict", json=sample_row)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["predicted_group"] in (0, 1, 2)
    assert set(body["probabilities"].keys()) == {"0", "1", "2"}
    assert abs(sum(body["probabilities"].values()) - 1.0) < 1e-4
    assert body["model_name"] == "xgboost"
    assert body["request_id"]


def test_predict_rejects_leakage_column(client: TestClient, sample_row: dict[str, float]) -> None:
    """The most important contract — post-campaign columns must never reach the model."""
    bad = {**sample_row, "g1_21": 0.5}  # post-campaign — should be 422
    r = client.post("/v1/predict", json=bad)
    assert r.status_code == 422
    body = r.json()
    errors = body["detail"]
    assert any("g1_21" in str(e.get("loc", [])) for e in errors)
    assert any(e.get("type") == "extra_forbidden" for e in errors)


@pytest.mark.parametrize("leakage_field", ["g1_21", "g2_21", "c_28"])
def test_predict_rejects_all_post_campaign_fields(
    client: TestClient, sample_row: dict[str, float], leakage_field: str
) -> None:
    bad = {**sample_row, leakage_field: 1.0}
    r = client.post("/v1/predict", json=bad)
    assert r.status_code == 422


def test_predict_missing_field_returns_422(
    client: TestClient, sample_row: dict[str, float]
) -> None:
    bad = {k: v for k, v in sample_row.items() if k != "c_15"}
    r = client.post("/v1/predict", json=bad)
    assert r.status_code == 422
    body = r.json()
    assert any("c_15" in str(e.get("loc", [])) for e in body["detail"])


def test_predict_batch(client: TestClient, sample_row: dict[str, float]) -> None:
    body = {"items": [sample_row, sample_row, sample_row]}
    r = client.post("/v1/predict/batch", json=body)
    assert r.status_code == 200, r.text
    out = r.json()
    assert len(out["predictions"]) == 3
    assert [p["index"] for p in out["predictions"]] == [0, 1, 2]
    # batch is deterministic — all rows are identical so predictions match
    preds = {p["predicted_group"] for p in out["predictions"]}
    assert len(preds) == 1


def test_batch_max_size_enforced(client: TestClient, sample_row: dict[str, float]) -> None:
    body = {"items": [sample_row] * 1001}  # over the 1000 max
    r = client.post("/v1/predict/batch", json=body)
    assert r.status_code == 422


def test_metrics_endpoint_exposed(client: TestClient) -> None:
    r = client.get("/metrics")
    assert r.status_code == 200
    assert b"http_requests_total" in r.content or b"python_info" in r.content
