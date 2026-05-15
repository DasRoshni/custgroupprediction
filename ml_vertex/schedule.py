"""
Usage:
    python -m ml_vertex.schedule create   # creates a weekly Monday 03:00 UTC schedule
    python -m ml_vertex.schedule list
    python -m ml_vertex.schedule delete --name <schedule-name>
    python -m ml_vertex.schedule pause    --name <schedule-name>
    python -m ml_vertex.schedule resume   --name <schedule-name>
"""
import argparse
import os
import sys

from google.cloud import aiplatform


def _init(args):
    aiplatform.init(project=args.project, location=args.region)


def cmd_create(args):
    if not args.spec or not os.path.exists(args.spec):
        sys.exit(f"--spec {args.spec} not found; run `make vertex-compile` first")

    pipeline_root = args.pipeline_root or (
        f"gs://{args.project}-customer-group-predictor-models/pipeline-root"
    )
    models_bucket = f"{args.project}-customer-group-predictor-models"

    job = aiplatform.PipelineJob(
        display_name=args.display_name,
        template_path=args.spec,
        pipeline_root=pipeline_root,
        enable_caching=False,
        parameter_values={
            "project_id":          args.project,
            "region":              args.region,
            "dataset":             os.environ.get("DATASET", "marketing"),
            "bq_location":         os.environ.get("BQ_LOCATION", "US"),
            "models_bucket":       models_bucket,
            "model_version":       args.model_version,
            "cloud_run_service":   args.cloud_run_service,
            "baseline":            float(os.environ.get("BASELINE", "0.4645")),
            "min_improvement_pp":  float(os.environ.get("MIN_IMPROVEMENT_PP", "3.0")),
        },
    )

    schedule = job.create_schedule(
        display_name=args.display_name,
        cron=args.cron,
        max_concurrent_run_count=1,
        max_run_count=None,
        service_account=args.service_account,
    )
    print(f"Created schedule: {schedule.resource_name}")
    print(f"Cron:             {args.cron}")
    print(f"Display name:     {args.display_name}")
    print(f"Console:          https://console.cloud.google.com/vertex-ai/pipelines/schedules/"
          f"{schedule.name}?project={args.project}")


def cmd_list(args):
    schedules = aiplatform.PipelineJobSchedule.list()
    if not schedules:
        print("(no schedules)")
        return
    for s in schedules:
        print(f"  {s.display_name:30s}  state={s.state.name}  cron={getattr(s, 'cron', '?')}  "
              f"name={s.resource_name}")


def _find_schedule(name: str):
    for s in aiplatform.PipelineJobSchedule.list():
        if s.display_name == name or s.resource_name.endswith(name) or s.name == name:
            return s
    return None


def cmd_delete(args):
    s = _find_schedule(args.name)
    if not s:
        sys.exit(f"schedule {args.name!r} not found")
    s.delete(sync=True)
    print(f"Deleted: {s.display_name}")


def cmd_pause(args):
    s = _find_schedule(args.name)
    if not s:
        sys.exit(f"schedule {args.name!r} not found")
    s.pause()
    print(f"Paused: {s.display_name}")


def cmd_resume(args):
    s = _find_schedule(args.name)
    if not s:
        sys.exit(f"schedule {args.name!r} not found")
    s.resume()
    print(f"Resumed: {s.display_name}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--project", default=os.environ.get("PROJECT_ID"))
    p.add_argument("--region", default=os.environ.get("REGION", "europe-west3"))
    sub = p.add_subparsers(dest="cmd", required=True)

    pc = sub.add_parser("create")
    pc.add_argument("--spec", default="ml_vertex/pipeline.json")
    pc.add_argument("--display-name", default="customer-group-weekly-retrain")
    pc.add_argument("--cron", default="0 3 * * 1",
                    help="Cron expr (UTC). Default: Mondays 03:00 UTC.")
    pc.add_argument("--pipeline-root", default=None)
    pc.add_argument("--model-version", default=os.environ.get("MODEL_VERSION", "1.1.0"))
    pc.add_argument("--cloud-run-service", default="customer-group-predictor")
    pc.add_argument(
        "--service-account",
        default=os.environ.get(
            "PIPELINE_SA",
            f"customer-group-predictor-sa@{os.environ.get('PROJECT_ID')}.iam.gserviceaccount.com",
        ),
    )
    pc.set_defaults(func=cmd_create)

    pl = sub.add_parser("list")
    pl.set_defaults(func=cmd_list)

    for cmd_name, fn in (("delete", cmd_delete), ("pause", cmd_pause), ("resume", cmd_resume)):
        pp = sub.add_parser(cmd_name)
        pp.add_argument("--name", required=True, help="display name or resource name")
        pp.set_defaults(func=fn)

    args = p.parse_args()
    if not args.project:
        sys.exit("PROJECT_ID env required")

    _init(args)
    args.func(args)


if __name__ == "__main__":
    main()
