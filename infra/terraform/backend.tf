# Remote Terraform state — store in GCS, not on developer laptops.
#
# Why a remote backend matters (fintech non-negotiable):
#   - State files contain plaintext outputs of every resource (URIs, SA emails,
#     IAM bindings) and must never live in git.
#   - Versioning + object lock on the bucket give point-in-time recovery and
#     defend against accidental `terraform destroy`.
#   - State locking prevents concurrent applies from corrupting state.
#   - CMEK encryption (optional) meets data-residency / key-control requirements.
#
# One-time setup BEFORE the first `terraform init`:
#   make tfstate-init PROJECT_ID=<id> TFSTATE_BUCKET=<id>-tfstate
#
# Then update `bucket =` below to match TFSTATE_BUCKET and run:
#   terraform init -migrate-state
#
# Each environment gets its own prefix so dev / staging / prod states are
# isolated even if they share a bucket.

terraform {
  backend "gcs" {
    bucket = "roshni-das-511-tfstate"  # created by `make tfstate-init`
    prefix = "customer-group-predictor/prod"
  }
}
