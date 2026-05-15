"""Submit a Vertex AI pipeline run.

Reads config from env (set in .env). Idempotent — each run gets a unique
display name based on UTC timestamp.
"""
from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone

from google.cloud import aiplatform


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", default="ml_vertex/pipeline.json")
    parser.add_argument("--project", default=os.environ.get("PROJECT_ID"))
    parser.add_argument("--region", default=os.environ.get("REGION", "us-central1"))
    parser.add_argument("--service-account", default=os.environ.get("PIPELINE_SA"))
    parser.add_argument("--pipeline-root", default=os.environ.get("PIPELINE_ROOT"))
    parser.add_argument("--sync", action="store_true",
                        help="Wait for the pipeline to finish (default: return job URL).")
    args = parser.parse_args()

    if not args.project:
        raise SystemExit("PROJECT_ID env required")
    if not args.pipeline_root:
        args.pipeline_root = f"gs://{args.project}-customer-group-predictor-models/pipeline-root"
    if not args.service_account:
        args.service_account = f"customer-group-predictor-sa@{args.project}.iam.gserviceaccount.com"

    aiplatform.init(project=args.project, location=args.region)

    job = aiplatform.PipelineJob(
        display_name=f"customer-group-retrain-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}",
        template_path=args.spec,
        pipeline_root=args.pipeline_root,
        enable_caching=False,  # caching can mask bugs during development
        parameter_values={
            "project_id":          args.project,
            "dataset":             os.environ.get("DATASET", "marketing"),
            "bq_location":         os.environ.get("BQ_LOCATION", "US"),
            "models_bucket":       f"{args.project}-customer-group-predictor-models",
            "model_version":       os.environ.get("MODEL_VERSION", "1.1.0"),
            "baseline":            float(os.environ.get("BASELINE", "0.4645")),
            "min_improvement_pp":  float(os.environ.get("MIN_IMPROVEMENT_PP", "3.0")),
        },
    )

    job.submit(service_account=args.service_account)
    print(f"Submitted: {job.resource_name}")
    print(f"Console:  https://console.cloud.google.com/vertex-ai/pipelines/runs/"
          f"{job.name}?project={args.project}")

    if args.sync:
        print("Waiting for pipeline to finish...")
        job.wait()
        print(f"Final state: {job.state}")


if __name__ == "__main__":
    main()
