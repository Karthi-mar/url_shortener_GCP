variable "project_id"{
  description = "GCP project ID"
  type = string
  default = "karthi-url-shortener-2026"
}

variable "region" {
  description = " GCP region"
  type = string
  default = "us-central1"
}

variable "repository_id"{
  description = "Articfact registry repository name" 
  type = string
  default = "url-shortener"
}

variable "github_repo"{
  description = " Github repo as 'owner/repo' , used to restrict workload identity federation"
  type = string
  default = "Karthi-mar/url_shortener_GCP"
}
    