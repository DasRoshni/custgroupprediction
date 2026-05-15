# Security & Credentials Model

This is the operating model for credentials, secrets, and least-privilege IAM
in this project. Designed for a fintech-grade GCP deployment.

---

## 1. Credential model (per environment)

| Environment | How code authenticates | Long-lived keys? |
|---|---|---|
| Local dev | `gcloud auth application-default login` → user ADC | ❌ Never |
| CI/CD | Workload Identity Federation → short-lived OIDC token | ❌ Never |
| Cloud Run (runtime) | Attached service account → metadata server | ❌ Never |

**Anti-pattern:** copying a service account JSON key to a laptop or CI
secret. With Workload Identity, no JSON keys are needed anywhere.

If you absolutely must impersonate a service account locally:
```bash
gcloud auth application-default login \
  --impersonate-service-account=foo@proj.iam.gserviceaccount.com
```

---

## 2. What goes in `.env` vs Secret Manager

| Class | Examples | Where |
|---|---|---|
| Config (not secret) | `PROJECT_ID`, region, bucket names, image tag | `.env` (gitignored) or repo `.env.example` |
| Runtime config | log level, env name, feature flags | Cloud Run env vars |
| **Secrets** | DB password, third-party API tokens, JWT signing keys | Secret Manager, mounted as env or file at runtime |

Cloud Run can mount a Secret Manager secret directly into the container:

```hcl
env {
  name = "DB_PASSWORD"
  value_source {
    secret_key_ref {
      secret  = google_secret_manager_secret.db.secret_id
      version = "latest"
    }
  }
}
```

---

## 3. IAM principles

- **One service account per workload.** The Cloud Run API SA is distinct from the
  training pipeline SA, the CI deploy SA, and any human user.
- **Least privilege.** Grant the minimum role needed. Never `roles/owner` to anything
  that isn't a break-glass admin SA.
- **No `Editor` role in production.** Prefer narrow roles like
  `roles/run.invoker`, `roles/storage.objectViewer`, `roles/bigquery.dataViewer`.
- **Use `iam.disableServiceAccountKeyCreation` org policy** to prevent anyone
  (including admins) from minting long-lived keys.
- **Quarterly access review.** Run `gcloud projects get-iam-policy` against every
  project; review every member binding; require justification for retention.

---

## 4. State & infrastructure

- Terraform state lives in a versioned, CMEK-encrypted GCS bucket — never local.
  Bootstrap with `make tfstate-init`.
- `terraform.tfvars` is gitignored; commit `terraform.tfvars.example`.
- `backend.tf` is committed with a placeholder bucket; each environment has a
  different `prefix=` so dev/staging/prod don't share state.
- CI runs `terraform plan` on PRs and posts the plan as a PR comment.
  `terraform apply` runs only on merge to main.

---

## 5. Data & encryption

| Resource | Encryption at rest | Notes |
|---|---|---|
| BigQuery raw + curated | Google-managed (default) → CMEK in prod | Per-table KMS key reference |
| GCS models bucket | Google-managed → CMEK in prod | `gsutil kms encryption -k ...` |
| Artifact Registry | Google-managed → CMEK in prod | CMEK at repo creation |
| Cloud Run revisions | Encrypted ephemeral disk | No persistent disk |
| Terraform state bucket | CMEK | Bootstrap script optional `KMS_KEY` |

Encryption in transit: TLS 1.3 everywhere. Cloud Run's `*.run.app` URL is
auto-provisioned with managed certs. Internal traffic over Google network is
encrypted by default.

---

## 6. Audit & monitoring

- **Cloud Audit Logs**: enable Admin Activity, Data Access (Read + Write) on
  `cloudresourcemanager.googleapis.com`, `bigquery.googleapis.com`,
  `storage.googleapis.com`, `iam.googleapis.com`. Retain 7 years.
- **Log sink** → BigQuery dataset (e.g. `audit_logs`) with row-level access.
- **Alert policies** on:
  - Service account key creation (should be zero with org policy)
  - IAM binding changes on production projects
  - 5xx rate > 1% sustained for 5 min
  - p95 latency > 300 ms sustained for 10 min
  - Cloud Run instance count saturation

---

## 7. VPC Service Controls (production hardening)

For a true fintech production deployment, wrap the project(s) in a VPC SC
perimeter so that even with compromised credentials, data cannot be exfiltrated
to outside services.

Inside the perimeter:
- BigQuery, GCS, Artifact Registry, Cloud Run

Egress rules: explicit allow-lists only.

This is project-org-level work and not part of the Terraform in this repo —
it's set up once at the org level by the platform team.

---

## 8. Secret rotation

- Service account keys: **never minted** (org policy).
- Secret Manager values: rotation schedule configured per secret (typical: 90 d).
  Notification topic fires a Cloud Function that calls the upstream system's
  rotation endpoint, writes the new version, and increments the secret version.
- TLS certs: auto-renewed by Cloud Run / managed certs.

---

## 9. Incident response (basics)

If a credential is suspected leaked:

1. **Disable the SA immediately**:
   ```bash
   gcloud iam service-accounts disable <SA_EMAIL>
   ```
2. **Revoke any keys** (should be zero):
   ```bash
   gcloud iam service-accounts keys list --iam-account=<SA_EMAIL>
   gcloud iam service-accounts keys delete <KEY_ID> --iam-account=<SA_EMAIL>
   ```
3. **Rotate dependent secrets** (anything the SA could read).
4. **Pull audit logs** to determine blast radius (Cloud Audit Logs in BigQuery).
5. **File incident report** within the team's SLA (usually < 24 h for fintech).

---

## 10. Checklist before production go-live

- [ ] `make tfstate-init` complete; state in GCS, CMEK on bucket
- [ ] `terraform.tfvars` not committed
- [ ] No SA JSON keys exist (`gcloud iam service-accounts keys list ...` returns 0)
- [ ] Workload Identity Federation configured for CI
- [ ] Cloud Run service uses dedicated SA with narrow roles
- [ ] `--allow-unauthenticated` removed; `roles/run.invoker` granted to known principals only
- [ ] Cloud Armor security policy attached (WAF, rate limits)
- [ ] Audit Data Access logs enabled on BQ + GCS
- [ ] CMEK on BQ, GCS models bucket, Artifact Registry, tfstate bucket
- [ ] VPC Service Controls perimeter includes the project
- [ ] Monitoring alert policies + PagerDuty integration
- [ ] Budget alert at $50/month (tunable)
- [ ] Quarterly IAM access review scheduled
- [ ] Runbook for credential leak / model rollback / drift breach
