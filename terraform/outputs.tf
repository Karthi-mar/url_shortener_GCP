output "artifact_registry_repository_url" {
  description = "Full path of the Artifact Registry repo, for use in docker push/CI"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.url_shortener.repository_id}"
}

output "run_service_account_email" {
  description = "Email of the Cloud Run runtime service account"
  value       = google_service_account.run_sa.email
}
