terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.36"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# ---------- Project APIs ----------------------------------------------------
resource "google_project_service" "apis" {
  for_each = toset([
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "secretmanager.googleapis.com",
    "storage.googleapis.com",
    "bigquery.googleapis.com",
  ])
  service            = each.value
  disable_on_destroy = false
}

# ---------- Artifact Registry (container images) ----------------------------
resource "google_artifact_registry_repository" "api" {
  location      = var.region
  repository_id = "${var.app_name}-images"
  description   = "Container images for the customer-group predictor API"
  format        = "DOCKER"
  depends_on    = [google_project_service.apis]
}

# ---------- GCS bucket for model artifacts ---------------------------------
resource "google_storage_bucket" "models" {
  name                        = "${var.project_id}-${var.app_name}-models"
  location                    = var.region
  uniform_bucket_level_access = true
  versioning { enabled = true }

  lifecycle_rule {
    condition { num_newer_versions = 10 }
    action { type = "Delete" }
  }
  depends_on = [google_project_service.apis]
}

# ---------- Runtime service account (least-privilege) ----------------------
resource "google_service_account" "api" {
  account_id   = "${var.app_name}-sa"
  display_name = "Customer Group API runtime SA"
}

resource "google_storage_bucket_iam_member" "api_reads_models" {
  bucket = google_storage_bucket.models.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.api.email}"
}

resource "google_project_iam_member" "api_writes_logs" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.api.email}"
}

resource "google_project_iam_member" "api_writes_metrics" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.api.email}"
}

# Read access to BigQuery (for the offline feature path; not needed by the
# stateless API itself but useful for related jobs sharing the SA)
resource "google_project_iam_member" "api_bq_user" {
  project = var.project_id
  role    = "roles/bigquery.dataViewer"
  member  = "serviceAccount:${google_service_account.api.email}"
}

# ---------- Cloud Run service ----------------------------------------------
resource "google_cloud_run_v2_service" "api" {
  name     = var.app_name
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL" # tighten to internal+LB if behind a GLB

  template {
    service_account = google_service_account.api.email

    scaling {
      min_instance_count = 1 # avoid cold starts (model load ~3s)
      max_instance_count = 10
    }

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.api.repository_id}/${var.app_name}:${var.image_tag}"

      env {
        name  = "ENVIRONMENT"
        value = "prod"
      }
      env {
        name  = "LOG_LEVEL"
        value = "INFO"
      }
      env {
        name  = "MODEL_PATH"
        value = "gs://${google_storage_bucket.models.name}/current/model.joblib"
      }
      env {
        name  = "METADATA_PATH"
        value = "gs://${google_storage_bucket.models.name}/current/metadata.json"
      }

      resources {
        limits = {
          cpu    = "2"
          memory = "2Gi"
        }
        startup_cpu_boost = true
      }

      startup_probe {
        http_get { path = "/readyz" }
        initial_delay_seconds = 5
        period_seconds        = 5
        failure_threshold     = 12 # ~60s total — covers cold model load
      }
      liveness_probe {
        http_get { path = "/healthz" }
        period_seconds    = 30
        failure_threshold = 3
      }
    }

    timeout                          = "60s"
    max_instance_request_concurrency = 80
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  depends_on = [google_project_service.apis]
}

# ---------- Public IAM (tighten as needed) ----------------------------------
# For internal-only services, replace 'allUsers' with specific groups.
resource "google_cloud_run_v2_service_iam_member" "invoker" {
  name     = google_cloud_run_v2_service.api.name
  location = google_cloud_run_v2_service.api.location
  role     = "roles/run.invoker"
  member   = var.invoker_member # e.g. "user:marketer@example.com" or "allUsers" (PoC only)
}

output "service_url" {
  value = google_cloud_run_v2_service.api.uri
}

output "image_repository" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.api.repository_id}"
}

output "models_bucket" {
  value = google_storage_bucket.models.name
}
