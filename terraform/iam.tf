resource "google_project_iam_member" "run_sa_datastore_user" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.run_sa.email}"
}