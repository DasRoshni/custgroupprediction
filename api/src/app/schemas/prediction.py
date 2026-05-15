"""Request/response schemas for the prediction API."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, create_model

from customergroups.columns import C_PRE, G1_PRE, G2_PRE, PRE_CAMPAIGN_FEATURES


# Build CampaignFeatures dynamically from the canonical column list so the schema
# can never drift from `customergroups.columns`. All 67 features are typed as
# `float` (Pydantic accepts ints and promotes them).
#
# `extra="forbid"` is the schema-level leakage guard:
# any post-campaign field in the payload (g1_21, g2_21, c_28) is rejected with
# 422 before it ever reaches the model.
CampaignFeatures = create_model(
    "CampaignFeatures",
    __config__=ConfigDict(extra="forbid"),
    **{name: (float, ...) for name in PRE_CAMPAIGN_FEATURES},
)


class PredictionResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    predicted_group: Literal[0, 1, 2] = Field(
        description="0 = neither profitable, 1 = pick group 1, 2 = pick group 2"
    )
    probabilities: dict[str, float] = Field(
        description="Class probabilities, e.g. {'0': 0.10, '1': 0.60, '2': 0.30}"
    )
    model_version: str
    model_name: str
    request_id: str


class BatchRequest(BaseModel):
    items: list[CampaignFeatures] = Field(min_length=1, max_length=1000)  # type: ignore[valid-type]


class BatchResponseItem(BaseModel):
    index: int
    predicted_group: Literal[0, 1, 2]
    probabilities: dict[str, float]


class BatchResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    predictions: list[BatchResponseItem]
    model_version: str
    model_name: str
    request_id: str


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]


class ReadyResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    status: Literal["ready", "not_ready"]
    model_loaded: bool
    model_version: str | None = None


class ModelInfoResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    model_name: str
    model_version: str
    trained_at: str
    test_success_rate: float
    baseline_success_rate: float
    improvement_pp: float
    test_accuracy: float
    test_macro_f1: float
    artifact_sha256: str
    required_features_count: int
