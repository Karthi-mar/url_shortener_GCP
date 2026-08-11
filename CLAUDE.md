# Project: Cloud-Native URL Shortener (DevOps Portfolio Project)

## Context
This is a solo portfolio project built to demonstrate practical DevOps skills for
job applications (DevOps / SRE roles). The author has decent conceptual knowledge
of GCP, Docker, Terraform, GitHub Actions, and Flask, but limited hands-on
implementation experience. The primary goal of this project is **implementation**,
not novel engineering — every piece should be simple enough to explain line-by-line
in an interview.

**Explicitly out of scope for now** (do not introduce unless the author asks):
- MLOps / ML pipelines 
- Prometheus / Grafana / observability stack
for now lets avoid these but will add if needed


A dedicated GCP project is used exclusively for this build.

## Cost constraint: this project must run at $0/month
The author is using Google Cloud's permanent "Always Free" tier, not the $300
trial credit(if needed the 300 dollar please let me know). All design and implementation choices must respect this:

- **Region**: all resources go in `us-central1` (Always Free quotas are
  region-restricted).
- **Cloud Run**: must be configured with `min-instances=0` (scale to zero) so
  there is never an idle billed instance.
- **Artifact Registry**: free storage is only **0.5 GB total** — this is the
  easiest limit to blow past since every image push adds a version. A cleanup
  policy (keep last 2–3 image versions, auto-delete the rest) must be part of
  the Terraform config or the CD workflow from the start, not added later.
- **Firestore**: stays comfortably under the 1 GB free limit for this project;
  no special handling needed.
- **No Cloud SQL** — it has no permanent free tier (this is why Firestore was
  chosen for the data tier).
- **GitHub Actions**: repo should be public to get unlimited free CI/CD
  minutes.
- **Billing account**: must be linked to the GCP project (required by Google
  as of Feb 2026 even for free-tier usage) but a **budget alert** (e.g. at
  $1) should be set up as a safety net — this is a required setup step, not
  optional.
- When suggesting any new GCP resource, note whether it has an Always Free
  tier before adding it. If it doesn't, flag it and ask before proceeding.

## Architecture (2-tier, serverless)
```
GitHub Actions (CI/CD)
  -> lint/test on PR
  -> build Docker image -> push to Artifact Registry
  -> deploy new revision to Cloud Run (on merge to main)

Terraform (IaC) provisions:
  - Artifact Registry repo
  - Cloud Run service
  - Service account + least-privilege IAM bindings
  - Firestore database (native mode)
  - Secret Manager entries as needed

App tier:  Flask REST API, containerized, running on Cloud Run
Data tier: Firestore (serverless NoSQL — no VPC connector needed)
```

## API surface (keep minimal — do not expand without asking)
- `POST /shorten` — create a short URL
- `GET /<code>` — redirect to original URL
- `GET /urls` — list all shortened URLs
- `DELETE /<code>` — delete a short URL
- `GET /healthz` — health check for Cloud Run

## Build phases (work through in order, one at a time)
1. Flask app running locally with an in-memory dict (get logic right first)
2. Swap in-memory store for Firestore client
3. Dockerize (multi-stage build, small final image, non-root user)
4. Terraform: Artifact Registry + service account + IAM
5. Terraform: Cloud Run service + Firestore
6. GitHub Actions CI workflow (lint + test on every PR)
7. GitHub Actions CD workflow (build, push, deploy on merge to main)
8. GitHub Actions workflow for `terraform plan` (PR) / `terraform apply` (merge)
9. README with architecture diagram + setup instructions

## Working agreement for Claude
- Briefly explain any new concept (a Terraform resource, a GitHub Actions
  feature, a GCP service) before or while implementing it — the author is
  learning, not just outsourcing.
- Do not introduce tools, services, or complexity beyond the current phase
  without asking first.
- Prefer patterns from official GCP / Terraform provider docs over clever
  shortcuts.
- Keep IAM least-privilege — call out any broad role bindings explicitly.
- Favor code the author can confidently narrate in an interview over code
  that's merely clever or terse.
- If a decision has real tradeoffs (e.g. Firestore vs Cloud SQL), state the
  tradeoff briefly and default to the simpler option unless told otherwise.

## Target repo structure
```
.
├── app/
│   ├── main.py
│   ├── requirements.txt
│   └── tests/
├── Dockerfile
├── terraform/
│   ├── main.tf
│   ├── variables.tf
│   ├── outputs.tf
│   └── iam.tf
├── .github/
│   └── workflows/
│       ├── ci.yml
│       ├── cd.yml
│       └── terraform.yml
└── README.md
```   something like this , but feel free to edit as well.

## Progress log (updated after each phase — full narrative in README.md)

**GCP account setup — done:**
- Project: `karthi-url-shortener-2026`, account `karthimarvel1@gmail.com`, "No organization"
- Billing linked, budget alert set up by author in Console (~$1/₹10 threshold)
- Firestore database created: **Standard edition**, Native mode, `us-central1`

**Phase 1 (Flask app, in-memory dict) — done.**
`app/main.py`, `app/requirements.txt`, `app/requirements-dev.txt`, `app/pytest.ini`,
`app/tests/test_main.py` (9 tests). All 5 endpoints implemented and verified.

**Phase 2 (Firestore) — done.**
In-memory dict replaced with a real Firestore collection (`urls`, short code = document ID).
Key decisions: Standard edition over Enterprise (simpler, matches free tier assumptions
already in this file); tests run against real Firestore, no emulator (kept simple, free
tier makes cost a non-issue); `GCP_PROJECT_ID` hardcoded as a constant in `main.py`
(required — ADC user credentials carry no project ID, `firestore.Client()` fails without
one passed explicitly).

**Phase 3 (Dockerize) — done.**
Multi-stage `Dockerfile` (`python:3.12-slim`, non-root `appuser`, gunicorn). Key fix
kept from an earlier draft: `main.py` creates its Firestore client lazily (on first
request) rather than at import time, because gunicorn forks worker processes after
import and gRPC clients aren't fork-safe. Verified: container builds, runs as
non-root, all 5 endpoints work against real Firestore.

**Repo status:** git repo initialized, pushed to `github.com/Karthi-mar/url_shortener_GCP`.
`Terraform/variables.tf` exists (project_id, region, repository_id, github_repo vars)
— Phase 4 not started yet, left untracked/unpushed until then.

See `README.md` for the full phase-by-phase build journal, setup/run instructions, and
the dict→Firestore code mapping.

