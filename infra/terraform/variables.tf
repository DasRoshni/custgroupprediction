variable "project_id" {
  type        = string
  description = "GCP project ID"
}

variable "region" {
  type        = string
  description = "GCP region for Cloud Run, Artifact Registry, GCS bucket"
  default     = "us-central1"
}

variable "app_name" {
  type        = string
  description = "Name used for service, SA, registry, bucket"
  default     = "customer-group-predictor"
}

variable "image_tag" {
  type        = string
  description = "Tag of the container image deployed to Cloud Run (e.g. git SHA)"
  default     = "latest"
}

variable "invoker_member" {
  type        = string
  description = "IAM principal allowed to invoke /predict. For PoC: 'allUsers'. For prod: 'group:marketing-team@example.com'."
  default     = "allUsers"
}
