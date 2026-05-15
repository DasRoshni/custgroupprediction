# Customer Group Predictor — developer commands
# Run `make help` (or just `make`) for a list of targets.

# ----- Config ---------------------------------------------------------------
SHELL          := /bin/bash
.SHELLFLAGS    := -eu -o pipefail -c

# Auto-load .env if it exists, so commands like `make deploy` work without
# requiring `PROJECT_ID=... REGION=...` prefixes once you've populated .env.
# .env is gitignored (it's per-developer config); .env.example is committed.
-include .env
export

PYTHON         ?= python3.11
VENV           := .venv
VENV_BIN       := $(VENV)/bin
PIP            := $(VENV_BIN)/pip
PY             := $(VENV_BIN)/python
PYTEST         := $(VENV_BIN)/pytest
UVICORN        := $(VENV_BIN)/uvicorn

PORT           ?= 8000
HOST           ?= 127.0.0.1

API_SRC        := api/src
ML_ARTIFACTS   := ml/artifacts
MODEL_FILE     := $(ML_ARTIFACTS)/model.joblib
METADATA_FILE  := $(ML_ARTIFACTS)/metadata.json

DOCKER_IMAGE   ?= customer-group-predictor:local

.DEFAULT_GOAL  := help

# ----- Help (auto-generated from `## ` comments) ----------------------------
.PHONY: help
help: ## Show this help
	@awk 'BEGIN {FS = ":.*?## "} \
	     /^[a-zA-Z0-9_.-]+:.*?## / {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2} \
	     /^## SECTION/ {printf "\n\033[1m%s\033[0m\n", substr($$0, 12)}' \
	     $(MAKEFILE_LIST)

## SECTION Setup
.PHONY: setup install venv
venv: ## Create the virtualenv (idempotent)
	@test -d $(VENV) || $(PYTHON) -m venv $(VENV)
	@$(PIP) install --quiet --upgrade pip

install: venv ## Install all deps (ml + api + dev) and the customergroups package
	@echo "==> Installing ML deps"
	@$(PIP) install --quiet -r ml/requirements.txt
	@echo "==> Installing API + dev deps"
	@$(PIP) install --quiet -r api/requirements-dev.txt
	@echo "==> Installing customergroups (editable)"
	@$(PIP) install --quiet -e ml/
	@echo "Done. venv at $(VENV)"

setup: install ## Alias for install
	@:

## SECTION Data & training pipeline
.PHONY: curate eda train artifact pipeline data
data: $(MODEL_FILE) ## Build everything the API needs (curate -> train -> artifact)
	@:

curate: ## Step 01 — CSV -> Parquet (drops post-campaign cols)
	@$(PY) ml/scripts/01_curate.py

eda: curate ## Step 02 — EDA plots + findings.md (depends on curate)
	@$(PY) ml/scripts/02_eda.py

train: curate ## Step 03 — Train LR baseline + XGBoost, persist model
	@$(PY) ml/scripts/03_train.py

train-bq: ## Step 03 — Train pulling features from BigQuery campaigns_curated (needs PROJECT_ID)
	@PROJECT_ID=$${PROJECT_ID:?set PROJECT_ID} DATASET=$${DATASET:-marketing} \
	  BQ_LOCATION=$${BQ_LOCATION:-US} \
	  $(PY) ml/scripts/03_train.py

artifact: train ## Step 04 — Write metadata.json (version, perf, SHA-256)
	@$(PY) ml/scripts/04_finalize_artifact.py

$(MODEL_FILE) $(METADATA_FILE): ml/scripts/03_train.py ml/scripts/04_finalize_artifact.py
	@$(MAKE) -s artifact

pipeline: curate eda train artifact ## Full data+ML pipeline end-to-end
	@:

## SECTION Tests & quality
.PHONY: test test-unit test-integration lint format type-check
test: $(MODEL_FILE) ## Run all tests (29 expected)
	@cd api && ../$(PYTEST) -v

test-unit: ## Unit tests only
	@cd api && ../$(PYTEST) -v tests/unit

test-integration: $(MODEL_FILE) ## Integration tests only (need the model)
	@cd api && ../$(PYTEST) -v -m integration

lint: ## ruff check (no fixes)
	@$(VENV_BIN)/ruff check api/src ml/src api/tests || true

format: ## ruff format + ruff check --fix
	@$(VENV_BIN)/ruff format api/src ml/src api/tests
	@$(VENV_BIN)/ruff check --fix api/src ml/src api/tests || true

type-check: ## mypy
	@$(VENV_BIN)/mypy api/src ml/src || true

## SECTION Run the API
.PHONY: run run-prod
run: $(MODEL_FILE) ## Start the API with auto-reload (dev). PORT=8000 overridable.
	@PYTHONPATH=$(API_SRC) $(UVICORN) app.main:app --reload --host $(HOST) --port $(PORT)

run-prod: $(MODEL_FILE) ## Start the API like Cloud Run does (no reload)
	@PYTHONPATH=$(API_SRC) $(UVICORN) app.main:app --host 0.0.0.0 --port $(PORT) --workers 1

## SECTION Smoke tests
.PHONY: smoke
smoke: ## Hit /healthz, /readyz, /v1/model/info, /v1/predict (server must be running)
	@echo "--- /healthz ---";        curl -s http://$(HOST):$(PORT)/healthz | python3 -m json.tool
	@echo "--- /readyz ---";         curl -s http://$(HOST):$(PORT)/readyz | python3 -m json.tool
	@echo "--- /v1/model/info ---";  curl -s http://$(HOST):$(PORT)/v1/model/info | python3 -m json.tool
	@$(PY) -c "import json, pandas as pd; from customergroups.columns import PRE_CAMPAIGN_FEATURES; r=pd.read_parquet('data/processed/campaigns_curated.parquet').iloc[0]; print(json.dumps({k: float(r[k]) for k in PRE_CAMPAIGN_FEATURES}))" > /tmp/cgp_payload.json
	@echo "--- /v1/predict ---";     curl -s -X POST http://$(HOST):$(PORT)/v1/predict -H 'Content-Type: application/json' -d @/tmp/cgp_payload.json | python3 -m json.tool

## SECTION Docker
.PHONY: docker-build docker-run docker-stop docker-logs
docker-build: ## Build the production image
	@docker build -f infra/docker/Dockerfile -t $(DOCKER_IMAGE) .

docker-run: ## Run the image locally on :8080
	@docker rm -f cgp-local 2>/dev/null || true
	@docker run -d --name cgp-local -p 8080:8080 $(DOCKER_IMAGE)
	@echo "Container started. Try: curl http://127.0.0.1:8080/v1/model/info"

docker-stop: ## Stop the local container
	@docker rm -f cgp-local 2>/dev/null || true

docker-logs: ## Tail container logs
	@docker logs -f cgp-local

## SECTION GCP Deployment (requires PROJECT_ID + billing)
.PHONY: gcp-install gcp-bootstrap bq-setup image-push model-upload deploy smoke-prod deploy-all
gcp-install: ## Step 0 — Install gcloud CLI via Homebrew (one-time)
	@bash infra/scripts/00_install_gcloud.sh

tfstate-init: ## Step 0b — Create the hardened GCS bucket for Terraform state (one-time)
	@PROJECT_ID=$${PROJECT_ID:?set PROJECT_ID} \
	  TFSTATE_BUCKET=$${TFSTATE_BUCKET:-$${PROJECT_ID}-tfstate} \
	  REGION=$${REGION:-us-central1} \
	  bash infra/scripts/00b_bootstrap_tfstate.sh

gcp-bootstrap: ## Step 1 — Auth, set project, enable APIs (needs PROJECT_ID=...)
	@PROJECT_ID=$${PROJECT_ID:?set PROJECT_ID} REGION=$${REGION:-us-central1} \
	  bash infra/scripts/01_gcp_bootstrap.sh

bq-setup: ## Step 2 — Create BQ dataset + staging + raw + load CSV (needs PROJECT_ID)
	@PROJECT_ID=$${PROJECT_ID:?set PROJECT_ID} REGION=$${REGION:-us-central1} \
	  bash infra/scripts/02_bigquery_setup.sh

image-push: ## Step 3 — Build linux/amd64 image and push to Artifact Registry
	@PROJECT_ID=$${PROJECT_ID:?set PROJECT_ID} REGION=$${REGION:-us-central1} \
	  IMAGE_TAG=$${IMAGE_TAG:-v1.0.0} bash infra/scripts/03_build_and_push.sh

model-upload: $(MODEL_FILE) ## Step 4 — Upload model.joblib + metadata.json to GCS
	@PROJECT_ID=$${PROJECT_ID:?set PROJECT_ID} REGION=$${REGION:-us-central1} \
	  bash infra/scripts/04_upload_model.sh

deploy: ## Step 5 — terraform apply (creates Cloud Run service)
	@PROJECT_ID=$${PROJECT_ID:?set PROJECT_ID} REGION=$${REGION:-us-central1} \
	  IMAGE_TAG=$${IMAGE_TAG:-v1.0.0} INVOKER_MEMBER=$${INVOKER_MEMBER:-allUsers} \
	  bash infra/scripts/05_deploy_cloud_run.sh

smoke-prod: ## Step 6 — Smoke-test the live Cloud Run service
	@bash infra/scripts/06_smoke_test.sh

deploy-all: gcp-bootstrap bq-setup image-push model-upload deploy smoke-prod ## Full deploy in order (~30 min)
	@:

## SECTION dbt (BigQuery curated layer)
DBT          := $(VENV_BIN)/dbt
DBT_PROFILES := ml_dbt/profiles
DBT_PROJECT  := ml_dbt

.PHONY: dbt-deps dbt-debug dbt-run dbt-test dbt-build dbt-docs
dbt-deps: ## Install dbt-bigquery + project packages
	@$(PIP) install --quiet 'dbt-bigquery==1.8.3'

dbt-debug: ## Verify dbt can connect to BigQuery
	@DBT_PROFILES_DIR=$(DBT_PROFILES) $(DBT) debug --project-dir $(DBT_PROJECT)

dbt-run: ## Build all dbt models (staging -> intermediate -> marts)
	@DBT_PROFILES_DIR=$(DBT_PROFILES) $(DBT) run --project-dir $(DBT_PROJECT)

dbt-test: ## Run all dbt tests (schema + singular)
	@DBT_PROFILES_DIR=$(DBT_PROFILES) $(DBT) test --project-dir $(DBT_PROJECT)

dbt-build: ## Run + test in one pass (CI-style)
	@DBT_PROFILES_DIR=$(DBT_PROFILES) $(DBT) build --project-dir $(DBT_PROJECT)

dbt-docs: ## Generate + serve dbt docs at http://localhost:8580
	@DBT_PROFILES_DIR=$(DBT_PROFILES) $(DBT) docs generate --project-dir $(DBT_PROJECT)
	@DBT_PROFILES_DIR=$(DBT_PROFILES) $(DBT) docs serve  --project-dir $(DBT_PROJECT) --port 8580

## SECTION BigQuery (requires gcloud + billing)
.PHONY: bq-load
bq-load: ## (Legacy) Load CSV into BigQuery raw table only
	@PROJECT_ID=$${PROJECT_ID:?set PROJECT_ID} infra/bigquery/load.sh data/raw/customerGroups.csv

## SECTION Clean
.PHONY: clean clean-artifacts clean-venv clean-all
clean: ## Remove caches (pytest, mypy, ruff, __pycache__)
	@find . -type d -name __pycache__   -prune -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name .pytest_cache -prune -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name .mypy_cache   -prune -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name .ruff_cache   -prune -exec rm -rf {} + 2>/dev/null || true

clean-artifacts: ## Remove trained model + processed data
	@rm -rf $(ML_ARTIFACTS)/*.joblib $(ML_ARTIFACTS)/*.json $(ML_ARTIFACTS)/*.png $(ML_ARTIFACTS)/*.csv
	@rm -rf data/processed/*.parquet
	@rm -rf ml/notebooks/eda_outputs

clean-venv: ## Remove the virtualenv
	@rm -rf $(VENV)

clean-all: clean clean-artifacts clean-venv ## Nuke everything (back to fresh clone)
	@:
