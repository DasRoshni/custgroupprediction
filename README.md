# custgroupprediction

End-to-end ML system that predicts which of two customer groups (Group 1 vs Group 2) will be more profitable for a marketing campaign. XGBoost classifier served via FastAPI on Cloud Run, fed by a BigQuery → dbt → Vertex AI Pipelines training stack.

- **Live service:** `https://customer-group-predictor-95597606705.europe-west3.run.app`
- **Model:** XGBoost — test success rate 53.93%, **+7.48 pp lift** over the 46.45% always-pick-Group-1 baseline (test accuracy 57.33%, CV accuracy 60.66%). Source: `ml/artifacts/metrics.json`.
- **Auto-retrain:** Vertex AI Pipeline schedule, Mondays 03:00 UTC. Promotion gate compares the new model to both the baseline and the currently-deployed model.

---

## Repo layout

```
api/         FastAPI service (predictor)
ml/          Training code + columns/features modules
ml_dbt/      dbt project (staging → intermediate → marts)
ml_vertex/   Kubeflow pipeline DSL + scheduler
infra/       Terraform, Dockerfiles, bash scripts
docs/        Case study, exec summary, interview deck (md + pdf)
data/        customerGroups.csv (raw) + processed artifacts
```

Everything is driven by the top-level `Makefile` — `make help` lists all targets.

---

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.11+ | `brew install python@3.11` |
| Make | any | preinstalled on macOS |
| Docker (optional, for container run) | 24+ | Docker Desktop |
| gcloud CLI (optional, for GCP deploy) | latest | `make gcp-install` |
| pandoc + Chrome (optional, for docs PDFs) | — | `brew install pandoc` |

You only need Python + Make to run the service locally. Everything else is for the GCP path.

---

## Setup

One command bootstraps the venv, installs ml + api + dev deps, and registers the `customergroups` package in editable mode:

```bash
make install
```

This creates `.venv/` at the repo root. All subsequent `make` targets use it automatically — no need to `source .venv/bin/activate` unless you want to run Python directly.

To verify the install:

```bash
make test       # 27 pytest tests (api/tests/) — unit + integration
make dbt-test   # 14 dbt tests (12 schema/source assertions + 2 singular)
make lint       # ruff check
```

---

## Run the service locally

The API needs a trained model artifact (`ml/artifacts/model.joblib`) to start. The Makefile builds it for you on demand.

### Quick start (dev, with auto-reload)

```bash
make run
```

Equivalent to: curate CSV → train XGBoost → write metadata → start `uvicorn` with `--reload` on port 8000.

First run takes ~30s for training; subsequent runs skip rebuilding the model (Make dependency-tracks the artifact).

### Production-style run (no reload, single worker)

```bash
make run-prod
```

Mirrors how Cloud Run invokes the container.

### Smoke test

In a separate terminal, with the server running:

```bash
make smoke
```

Hits `/healthz`, `/readyz`, `/v1/model/info`, and `/v1/predict` with a sample payload.

### Manual request

```bash
curl -s http://localhost:8000/v1/predict \
  -H 'content-type: application/json' \
  -d @docs/examples/predict_request.json | jq
```
---

## Common workflows

| Task | Command |
|------|---------|
| Retrain locally on the CSV | `make train` |
| Retrain pulling from BigQuery | `make train-bq PROJECT_ID=...` |
| Full ML pipeline (curate → eda → train → artifact) | `make pipeline` |
| Rebuild docs PDFs | `make pdfs` |
| Run dbt against BigQuery | `make dbt-build` |
| Compile + submit a Vertex AI pipeline run | `make vertex-run PROJECT_ID=...` |
| Clean caches | `make clean` |
| Nuke venv + artifacts | `make clean-all` |

---

## Run in Docker (optional)

```bash
make docker-build      # builds linux/amd64 image
make docker-run        # serves on http://localhost:8080
make docker-logs       # tail
make docker-stop
```

---

## Deploy to GCP (optional)

Requires a GCP project with billing enabled. Set `PROJECT_ID` and run:

```bash
make deploy-all PROJECT_ID=<your-project>
```

This runs, in order: gcp-bootstrap → bq-setup → image-push → model-upload → terraform apply → smoke-prod. End-to-end takes ~30 min on a cold project.

---

## Troubleshooting

- **`make run` fails on first launch with "model.joblib not found"** — let it finish; the target trains the model before starting uvicorn. If training fails, run `make train` directly to see the error.
- **`make install` complains about Python version** — ensure `python3.11` is on PATH. The Makefile pins it explicitly.
- **Port 8000 already in use** — `make run PORT=8001`.
- **Cloud Run `/healthz` returns 404 from the edge** — known GCP quirk; use `/readyz` instead.
