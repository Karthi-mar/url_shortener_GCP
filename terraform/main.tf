resource "google_project_service" "artifact_registry"{
    service = "artifactregistry.googleapis.com"
    disable_on_destroy = false
}


resource "google_project_service" "iam"{
    service = "iam.googleapis.com"
    disable_on_destroy = false
}

resource "google_artifact_registry_repository" "url_shortener" {
  location               = var.region
  repository_id          = var.repository_id
  format                  = "DOCKER"
  cleanup_policy_dry_run  = false

  cleanup_policies {
    id     = "delete-old-versions"
    action = "DELETE"
    condition {
      tag_state = "ANY"
    }
  }

  cleanup_policies {
    id     = "keep-latest-n"
    action = "KEEP"
    most_recent_versions {
      keep_count = var.image_keep_count
    }
  }

  depends_on = [google_project_service.artifact_registry]
}

resource "google_service_account" "run_sa" {
  account_id   = "url-shortener-run-sa"
  display_name = "URL Shortener Cloud Run runtime identity"

  depends_on = [google_project_service.iam]
}


