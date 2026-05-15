"""Vertex AI Pipeline: end-to-end retraining for the customer-group model.

DAG:
    dbt_build  →  train  →  evaluate (gate)  →  register

Every component runs in the same `customer-group-predictor-pipeline` image
(built by infra/scripts/07_build_pipeline_image.sh), so `customergroups`,
`dbt-bigquery`, and Google Cloud SDKs are available without runtime installs.
"""
import os
from typing import NamedTuple

from kfp import dsl
from kfp.dsl import Input, Metrics, Model, Output


def _pipeline_image() -> str:
    img = os.environ.get("PIPELINE_IMAGE")
    if not img:
        raise RuntimeError("PIPELINE_IMAGE env var must be set before compiling.")
    return img


# ---------------------------------------------------------------------------
# Component 1 — dbt build
# Refreshes the curated mart that train consumes.
# ---------------------------------------------------------------------------
@dsl.component(base_image=_pipeline_image())
def dbt_build_op(
    project_id: str,
    dataset: str,
    bq_location: str,
) -> int:
    import os
    import subprocess

    from google.cloud import bigquery

    env = os.environ.copy()
    env["PROJECT_ID"] = project_id
    env["DATASET"] = dataset
    env["BQ_LOCATION"] = bq_location

    print("==> dbt build")
    result = subprocess.run(
        ["dbt", "build",
         "--project-dir", "/app/ml_dbt",
         "--profiles-dir", "/app/ml_dbt/profiles"],
        env=env, check=False, capture_output=True, text=True,
    )
    print(result.stdout)
    if result.returncode != 0:
        print("STDERR:", result.stderr)
        raise RuntimeError(f"dbt build failed (exit {result.returncode})")

    client = bigquery.Client(project=project_id, location=bq_location)
    n = list(client.query(
        f"SELECT COUNT(*) AS n FROM `{project_id}.{dataset}.campaigns_curated`"
    ).result())[0].n
    print(f"campaigns_curated row count: {n}")
    return int(n)


# ---------------------------------------------------------------------------
# Component 2 — train
# Pulls features from BQ curated, trains XGBoost, emits Model + Metrics artifacts.
# ---------------------------------------------------------------------------
@dsl.component(base_image=_pipeline_image())
def train_op(
    project_id: str,
    dataset: str,
    bq_location: str,
    model_artifact: Output[Model],
    metrics_artifact: Output[Metrics],
) -> NamedTuple("TrainOut", [
    ("test_success_rate", float),
    ("test_accuracy", float),
    ("test_macro_f1", float),
]):
    import json
    from pathlib import Path

    import joblib

    from customergroups.data import load_curated_from_bq
    from customergroups.features import FeatureBuilder
    from customergroups.training import Trainer, baseline_always_group1

    df = load_curated_from_bq(project_id, dataset, "campaigns_curated", bq_location)
    print(f"Loaded {len(df)} rows from BQ")

    fb = FeatureBuilder()
    trainer = Trainer(feature_builder=fb, augment=True)
    X_train, X_test, y_train, y_test = trainer.prepare_splits(df)
    baseline = baseline_always_group1(y_test.values)
    print(f"Baseline: {baseline:.4f}")

    xgb_result, xgb_model = trainer.train_xgb(X_train, y_train, X_test, y_test)
    print(f"XGBoost test success: {xgb_result.test_success_rate:.4f}")

    # Persist model bundle (Vertex AI uploads this to GCS automatically)
    bundle_path = Path(model_artifact.path)
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {"model": xgb_model, "feature_builder": fb, "model_name": xgb_result.name},
        bundle_path,
    )
    model_artifact.metadata["model_name"] = xgb_result.name
    model_artifact.metadata["test_success_rate"] = float(xgb_result.test_success_rate)
    model_artifact.metadata["test_accuracy"] = float(xgb_result.test_accuracy)
    model_artifact.metadata["test_macro_f1"] = float(xgb_result.test_macro_f1)
    model_artifact.metadata["baseline_success_rate"] = float(baseline)

    # Metrics artifact (auto-rendered in Vertex AI UI)
    metrics_payload = {
        "baseline_success_rate": baseline,
        "test_success_rate": xgb_result.test_success_rate,
        "test_accuracy": xgb_result.test_accuracy,
        "test_macro_f1": xgb_result.test_macro_f1,
        "cv_accuracy_mean": xgb_result.cv_accuracy_mean,
        "cv_accuracy_std": xgb_result.cv_accuracy_std,
        "improvement_pp": (xgb_result.test_success_rate - baseline) * 100,
    }
    Path(metrics_artifact.path).write_text(json.dumps(metrics_payload, indent=2))
    for k, v in metrics_payload.items():
        metrics_artifact.log_metric(k, float(v))

    from collections import namedtuple
    Out = namedtuple("TrainOut", ["test_success_rate", "test_accuracy", "test_macro_f1"])
    return Out(
        test_success_rate=float(xgb_result.test_success_rate),
        test_accuracy=float(xgb_result.test_accuracy),
        test_macro_f1=float(xgb_result.test_macro_f1),
    )


# ---------------------------------------------------------------------------
# Component 3 — evaluate
# Gate: returns True iff success rate beats baseline by min_improvement_pp.
# ---------------------------------------------------------------------------
@dsl.component(base_image=_pipeline_image())
def evaluate_op(
    test_success_rate: float,
    baseline: float,
    min_improvement_pp: float,
) -> bool:
    improvement_pp = (test_success_rate - baseline) * 100
    approved = improvement_pp >= min_improvement_pp
    print(f"baseline={baseline:.4f} success={test_success_rate:.4f} "
          f"improvement={improvement_pp:.2f}pp threshold={min_improvement_pp:.2f}pp "
          f"approved={approved}")
    return bool(approved)


# ---------------------------------------------------------------------------
# Component 4 — register
# Copies model + metadata to GCS (versioned + current/) so Cloud Run picks it up.
# ---------------------------------------------------------------------------
@dsl.component(base_image=_pipeline_image())
def register_op(
    project_id: str,
    models_bucket: str,
    model_version: str,
    model_artifact: Input[Model],
    metrics_artifact: Input[Metrics],
) -> str:
    import hashlib
    import json
    import platform
    from datetime import datetime, timezone
    from pathlib import Path

    from google.cloud import storage

    from customergroups.columns import PRE_CAMPAIGN_FEATURES
    from customergroups.features import ENGINEERED_FEATURES

    src = Path(model_artifact.path)
    sha = hashlib.sha256()
    with src.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)

    metrics = json.loads(Path(metrics_artifact.path).read_text())
    metadata = {
        "model_name": model_artifact.metadata.get("model_name", "xgboost"),
        "model_version": model_version,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "trained_by": "vertex-ai-pipeline",
        "python": platform.python_version(),
        "input_schema": {
            "required_features": PRE_CAMPAIGN_FEATURES,
            "count": len(PRE_CAMPAIGN_FEATURES),
            "post_campaign_columns_forbidden": ["g1_21", "g2_21", "c_28"],
        },
        "engineered_features": {
            "names": ENGINEERED_FEATURES,
            "count": len(ENGINEERED_FEATURES),
        },
        "performance": metrics,
        "artifact_sha256": sha.hexdigest(),
    }
    meta_path = Path(model_artifact.path).parent / "metadata.json"
    meta_path.write_text(json.dumps(metadata, indent=2))

    client = storage.Client(project=project_id)
    bucket = client.bucket(models_bucket)
    bucket.blob(f"v{model_version}/model.joblib").upload_from_filename(str(src))
    bucket.blob(f"v{model_version}/metadata.json").upload_from_filename(str(meta_path))
    bucket.blob("current/model.joblib").upload_from_filename(str(src))
    bucket.blob("current/metadata.json").upload_from_filename(str(meta_path))

    model_uri = f"gs://{models_bucket}/current/model.joblib"
    print(f"Promoted: {model_uri}")
    return model_uri


# ---------------------------------------------------------------------------
# Component 5 — Vertex AI Model Registry upload
# Registers the GCS-promoted model as a tracked, versioned Vertex AI Model.
# Reuses an existing model entry if display_name matches (creates a new version).
# ---------------------------------------------------------------------------
@dsl.component(base_image=_pipeline_image())
def vertex_registry_op(
    project_id: str,
    region: str,
    models_bucket: str,
    model_version: str,
    test_success_rate: float,
    test_accuracy: float,
    test_macro_f1: float,
) -> str:
    from google.cloud import aiplatform

    aiplatform.init(project=project_id, location=region)
    display_name = "customer-group-predictor"

    # The artifact_uri must point at a GCS *directory* (not the file), since
    # the Vertex AI Model Registry treats it as a folder of model files.
    artifact_uri = f"gs://{models_bucket}/v{model_version}/"
    print(f"artifact_uri: {artifact_uri}")

    # If a registered model with this display name already exists, register a
    # new version under it (parent_model). Otherwise create a fresh entry.
    existing = aiplatform.Model.list(filter=f'display_name="{display_name}"')
    parent_model = existing[0].resource_name if existing else None
    print(f"parent_model: {parent_model or '(new entry)'}")

    # Container spec — we use the prediction service container so the model
    # CAN be deployed to a Vertex AI Endpoint later if needed.
    serving_image = (
        f"{region}-docker.pkg.dev/{project_id}/customer-group-predictor-images/"
        "customer-group-predictor:v1.0.1"
    )

    model = aiplatform.Model.upload(
        display_name=display_name,
        artifact_uri=artifact_uri,
        serving_container_image_uri=serving_image,
        serving_container_predict_route="/v1/predict",
        serving_container_health_route="/readyz",
        serving_container_ports=[8080],
        parent_model=parent_model,
        version_aliases=[f"v{model_version.replace('.', '-')}"],
        version_description=(
            f"Trained {test_success_rate:.4f} success rate "
            f"(acc {test_accuracy:.4f}, macroF1 {test_macro_f1:.4f}). "
            f"Source: Vertex AI Pipeline."
        ),
        labels={
            "trained_by":  "vertex-ai-pipeline",
            "framework":   "xgboost",
            "task":        "classification",
        },
    )
    print(f"Registered: {model.resource_name}")
    print(f"Version:    {model.version_id}")
    return model.resource_name


# ---------------------------------------------------------------------------
# Component 6 — Cloud Run redeploy
# Forces a new revision so the serving container reloads the latest model
# from gs://.../current/. Done by bumping a no-op env var; Cloud Run treats
# any template change as a new revision and rolls it out atomically.
# ---------------------------------------------------------------------------
@dsl.component(base_image=_pipeline_image())
def redeploy_cloud_run_op(
    project_id: str,
    region: str,
    service_name: str,
    model_version: str,
) -> str:
    from datetime import datetime, timezone

    from google.cloud import run_v2

    client = run_v2.ServicesClient()
    name = f"projects/{project_id}/locations/{region}/services/{service_name}"
    service = client.get_service(name=name)

    # Bump the MODEL_VERSION_DEPLOYED env var on the container. Any template
    # change forces Cloud Run to roll out a new revision.
    container = service.template.containers[0]
    new_env = []
    seen = False
    for ev in container.env:
        if ev.name in ("MODEL_VERSION_DEPLOYED", "DEPLOYED_AT"):
            seen = True
            continue  # drop stale, we'll re-add below
        new_env.append(ev)
    new_env.append(run_v2.EnvVar(
        name="MODEL_VERSION_DEPLOYED",
        value=f"{model_version}@{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
    ))
    del container.env[:]
    container.env.extend(new_env)

    print(f"forcing new revision for {service_name} (was-stale={seen})")
    op = client.update_service(service=service)
    result = op.result(timeout=600)
    print(f"new revision: {result.latest_ready_revision}")
    return result.latest_ready_revision


# ---------------------------------------------------------------------------
# Pipeline definition
# ---------------------------------------------------------------------------
@dsl.pipeline(
    name="customer-group-retrain",
    description="Refresh BQ curated → train XGBoost → evaluate → promote to Cloud Run.",
)
def retrain_pipeline(
    project_id: str,
    region: str = "europe-west3",
    dataset: str = "marketing",
    bq_location: str = "US",
    models_bucket: str = "",
    model_version: str = "1.1.0",
    cloud_run_service: str = "customer-group-predictor",
    baseline: float = 0.4645,
    min_improvement_pp: float = 3.0,
):
    dbt = dbt_build_op(
        project_id=project_id,
        dataset=dataset,
        bq_location=bq_location,
    )

    train = train_op(
        project_id=project_id,
        dataset=dataset,
        bq_location=bq_location,
    ).after(dbt)

    evaluate = evaluate_op(
        test_success_rate=train.outputs["test_success_rate"],
        baseline=baseline,
        min_improvement_pp=min_improvement_pp,
    )

    # Gate: only register + promote if evaluation approves
    with dsl.If(evaluate.outputs["Output"] == True):  # noqa: E712
        register = register_op(
            project_id=project_id,
            models_bucket=models_bucket,
            model_version=model_version,
            model_artifact=train.outputs["model_artifact"],
            metrics_artifact=train.outputs["metrics_artifact"],
        )

        # Register in Vertex AI Model Registry (depends on GCS upload completing
        # so artifact_uri actually contains the new files)
        registry = vertex_registry_op(
            project_id=project_id,
            region=region,
            models_bucket=models_bucket,
            model_version=model_version,
            test_success_rate=train.outputs["test_success_rate"],
            test_accuracy=train.outputs["test_accuracy"],
            test_macro_f1=train.outputs["test_macro_f1"],
        ).after(register)

        # Force Cloud Run to roll out a new revision that picks up the
        # freshly-promoted model in gs://.../current/.
        redeploy_cloud_run_op(
            project_id=project_id,
            region=region,
            service_name=cloud_run_service,
            model_version=model_version,
        ).after(register, registry)
