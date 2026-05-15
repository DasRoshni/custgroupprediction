# Deployment Runbook — GCP Cloud Run

End-to-end deploy of the customer-group prediction API. Two paths:
- **Manual** (gcloud only) — fastest for first deploy / PoC.
- **Terraform** (recommended for prod) — declarative, repeatable, codified.

Both deploy the same container image and target the same Cloud Run service.

---

## Prerequisites

- A GCP project with **billing enabled** (Cloud Run, Artifact Registry, Cloud Storage all require it).
- `gcloud` CLI installed and authenticated:
  ```bash
  gcloud auth login
  gcloud config set project <PROJECT_ID>
  ```
- Docker installed locally.
- A trained model artifact (run `python ml/scripts/03_train.py && python ml/scripts/04_finalize_artifact.py` if you haven't).

---

## Architecture target

```
Marketer ──► HTTPS ──► Cloud Run (FastAPI)
                          │
                          ├─► GCS (model.joblib + metadata.json)  ← BigQuery → Vertex AI training pushes here
                          ├─► Cloud Logging  (structured JSON)
                          └─► Cloud Monitoring (Prometheus /metrics scraped)
```

---

## Path A — Manual deploy (gcloud)

### 1. Enable APIs
```bash
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  storage.googleapis.com \
  cloudbuild.googleapis.com \
  logging.googleapis.com \
  monitoring.googleapis.com
```

### 2. Create Artifact Registry repo
```bash
REGION=us-central1
REPO=customer-group-predictor-images
gcloud artifacts repositories create "$REPO" \
  --repository-format=docker --location="$REGION"
```

### 3. Build & push the image
```bash
PROJECT_ID=$(gcloud config get-value project)
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/customer-group-predictor:v1.0.0"

gcloud auth configure-docker "${REGION}-docker.pkg.dev"
docker build -f infra/docker/Dockerfile -t "$IMAGE" .
docker push "$IMAGE"
```

> **Apple Silicon note:** Cloud Run runs `linux/amd64`. If you're on M-series Mac:
> `docker buildx build --platform=linux/amd64 -f infra/docker/Dockerfile -t "$IMAGE" --push .`

### 4. Upload the model artifact to GCS
```bash
BUCKET="${PROJECT_ID}-customer-group-predictor-models"
gsutil mb -l "$REGION" "gs://${BUCKET}/" || true
gsutil cp ml/artifacts/model.joblib   "gs://${BUCKET}/current/model.joblib"
gsutil cp ml/artifacts/metadata.json  "gs://${BUCKET}/current/metadata.json"
```

### 5. Create a runtime service account
```bash
SA="customer-group-predictor-sa"
gcloud iam service-accounts create "$SA" --display-name "API runtime SA"

SA_EMAIL="${SA}@${PROJECT_ID}.iam.gserviceaccount.com"
gsutil iam ch "serviceAccount:${SA_EMAIL}:objectViewer" "gs://${BUCKET}"
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SA_EMAIL}" --role="roles/logging.logWriter"
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SA_EMAIL}" --role="roles/monitoring.metricWriter"
```

### 6. Deploy the Cloud Run service
```bash
gcloud run deploy customer-group-predictor \
  --image="$IMAGE" \
  --region="$REGION" \
  --service-account="$SA_EMAIL" \
  --cpu=2 --memory=2Gi \
  --min-instances=1 --max-instances=10 \
  --concurrency=80 \
  --timeout=60 \
  --allow-unauthenticated \
  --set-env-vars="ENVIRONMENT=prod,LOG_LEVEL=INFO" \
  --set-env-vars="MODEL_PATH=gs://${BUCKET}/current/model.joblib" \
  --set-env-vars="METADATA_PATH=gs://${BUCKET}/current/metadata.json"
```

> For internal-only access: remove `--allow-unauthenticated` and grant `roles/run.invoker` to a Google group.

### 7. Smoke test
```bash
URL=$(gcloud run services describe customer-group-predictor --region="$REGION" --format='value(status.url)')
curl -s "$URL/healthz"
curl -s "$URL/readyz"
curl -s "$URL/v1/model/info" | jq .
```

---

## Path B — Terraform (recommended)

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
# edit terraform.tfvars: project_id, image_tag, invoker_member

terraform init
terraform plan
terraform apply
```

After apply:
```bash
terraform output service_url     # use this in curl/UI
terraform output image_repository
terraform output models_bucket
```

You still need to build/push the image (step 3 above) and upload the model (step 4) — Terraform manages infra, not container builds.

---

## Promoting a new model

```bash
# 1. Train and finalize
python ml/scripts/03_train.py
python ml/scripts/04_finalize_artifact.py

# 2. Upload to a versioned prefix
VERSION=$(jq -r .model_version ml/artifacts/metadata.json)
gsutil cp ml/artifacts/model.joblib   "gs://${BUCKET}/v${VERSION}/model.joblib"
gsutil cp ml/artifacts/metadata.json  "gs://${BUCKET}/v${VERSION}/metadata.json"

# 3. Atomically swap 'current/'
gsutil -m rsync -d "gs://${BUCKET}/v${VERSION}/" "gs://${BUCKET}/current/"

# 4. Force a new revision so Cloud Run reloads the model
gcloud run services update customer-group-predictor --region="$REGION" \
  --update-env-vars="DEPLOYED_AT=$(date -u +%FT%TZ)"
```

`MODEL_PATH` is unchanged, but bumping any env var forces a new revision and the container reloads the model from `current/`.

---

## Rollback

```bash
gcloud run services update-traffic customer-group-predictor \
  --region="$REGION" \
  --to-revisions=<PREVIOUS_REVISION>=100
```

Cloud Run keeps all previous revisions until manually pruned — rollback is instant.

---

## Observability

- **Logs:** Cloud Logging — filter `resource.type="cloud_run_revision" AND resource.labels.service_name="customer-group-predictor"`.
- **Metrics:** `/metrics` Prometheus endpoint is auto-scraped if you enable the Cloud Run + Prometheus integration, or pull via Managed Service for Prometheus.
- **Tracing:** `--set-env-vars="OTEL_EXPORTER=cloudtrace"` plus the OTEL Python instrumentation (out of scope for v1).

---

## Cost estimate

For a low-traffic internal service (e.g., 10k requests/month) with `min-instances=1`:
- Cloud Run: ~$15–25/month (mostly the always-on instance)
- GCS: < $0.05/month
- Artifact Registry: < $0.10/month
- **Total: ~$15–25/month**

Set `min-instances=0` for true scale-to-zero (free when idle, ~3s cold-start penalty).

---

## Security checklist (prod)

- [ ] Remove `--allow-unauthenticated`; require IAM invoker or IAP.
- [ ] Restrict `ingress` to `internal-and-cloud-load-balancing` once a load balancer is in front.
- [ ] Enable CMEK on the GCS bucket and Artifact Registry.
- [ ] VPC Service Controls perimeter around the project.
- [ ] Cloud Armor in front of the load balancer (WAF, rate limit).
- [ ] Set up budget alert at $50/month.
- [ ] Audit logs retained 7 years (Data Access logs enabled).
