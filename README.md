# Cloud-Native URL Shortener

A solo DevOps/SRE portfolio project: a URL shortener built as a 2-tier serverless
app (Flask on Cloud Run + Firestore), provisioned with Terraform and deployed via
GitHub Actions — designed to run at **$0/month** on GCP's Always Free tier.

Full architecture, constraints, and build phases are specified in
[CLAUDE.md](CLAUDE.md). This document is a **running build journal, updated after
each phase**, plus practical "how to run this right now" instructions.

## Status

| Phase | What | Status |
|---|---|---|
| 1 | Flask app, in-memory dict | ✅ Done |
| 2 | Swap in Firestore | ✅ Done |
| 3 | Dockerize | ✅ Done |
| 4 | Terraform: Artifact Registry + IAM | ✅ Done |
| 5 | Terraform: Cloud Run + Firestore | ⬜ Not started |
| 6 | GitHub Actions CI | ⬜ Not started |
| 7 | GitHub Actions CD | ⬜ Not started |
| 8 | Terraform plan/apply workflow | ⬜ Not started |
| 9 | Final README + architecture diagram | ⬜ Not started |

## Quick Start — run it locally right now

Reflects the project's **current** state (post-Phase 2): a Flask app backed by real Firestore.

### Prerequisites
- Python 3.14+
- [gcloud CLI](https://cloud.google.com/sdk/docs/install), authenticated (`gcloud auth login`)
- Local Application Default Credentials set up: `gcloud auth application-default login`
- A GCP project with a Firestore database already created (Standard edition, Native mode, region `us-central1` — see Phase 2 journal entry below for exact steps)
- The project ID `karthi-url-shortener-2026` is currently hardcoded in `app/main.py` (`GCP_PROJECT_ID`) — change that constant if you fork this against a different project

### Setup
```powershell
cd d:\Cloud\2_tier
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r app\requirements.txt
```

### Run
```powershell
cd app
..\.venv\Scripts\python.exe main.py
```
Server starts at `http://127.0.0.1:8080`.

### Try it
```powershell
# Create a short URL
Invoke-RestMethod -Uri "http://127.0.0.1:8080/shorten" -Method POST -ContentType "application/json" -Body '{"url":"https://example.com"}'

# List all short URLs
Invoke-RestMethod -Uri "http://127.0.0.1:8080/urls" -Method GET

# Follow a redirect — paste http://127.0.0.1:8080/<code> (from the response above) into a browser

# Delete one
Invoke-RestMethod -Uri "http://127.0.0.1:8080/<code>" -Method DELETE

# Health check
Invoke-RestMethod -Uri "http://127.0.0.1:8080/healthz" -Method GET
```
Every `POST /shorten` writes a real document to Firestore — check
**GCP Console → Firestore → Data → `urls` collection** to see it appear live.

### Run tests
```powershell
cd d:\Cloud\2_tier
.\.venv\Scripts\python.exe -m pip install -r app\requirements-dev.txt
cd app
..\.venv\Scripts\python.exe -m pytest -v
```
Tests hit the real Firestore database (no mocks/emulator) and clean up after
themselves — the collection will be empty again once the suite finishes. Expect
~30s runtime (real network round-trips), not instant.

## Project structure (current)
```
2_tier/
├── CLAUDE.md
├── README.md
├── .venv/                    (not committed)
└── app/
    ├── main.py                Flask app + Firestore logic
    ├── requirements.txt        flask, google-cloud-firestore
    ├── requirements-dev.txt    + pytest
    ├── pytest.ini              pythonpath config so tests can `import main`
    └── tests/
        └── test_main.py        9 tests, all endpoints
```

## Build Journal

### Phase 1 — Flask app, in-memory dict
Built all 5 endpoints (`POST /shorten`, `GET /<code>`, `GET /urls`, `DELETE /<code>`,
`GET /healthz`) against a plain Python dict (`url_store = {}`), to get routing and
logic right before introducing any infrastructure. Verified manually (PowerShell
`Invoke-RestMethod`/`curl` against every endpoint, including checking the redirect's
`Location` header) and with a 9-test pytest suite (`app/tests/test_main.py`), using
Flask's `test_client()` and an `autouse` fixture that clears `url_store` before/after
every test so tests can't leak state into each other.

### Phase 2 — Swap in Firestore
Replaced `url_store = {}` with a real Firestore collection (`urls`), using the short
code itself as the document ID (not an auto-generated one) — so `GET /<code>` is a
direct document lookup, not a search.

**Setup done for this phase:**
- Created the Firestore database via Console: Firestore → Create Database →
  **Standard edition**, **Native mode**, region **`us-central1`** (locked in
  permanently at creation — edition/location can't change later). Enterprise
  edition was considered and rejected: it's a newer per-unit-billing SKU built for
  MongoDB-API compatibility — unnecessary complexity here. Standard edition has its
  own daily free tier (50K reads / 20K writes / 20K deletes) and matches the
  classic Firestore Native mode CLAUDE.md was written around.
- Local auth: `gcloud auth application-default login` (Application Default
  Credentials) — lets local Python code authenticate as your user identity, no key
  files involved. One-time setup; credentials cached at
  `%APPDATA%\gcloud\application_default_credentials.json`.
- **Gotcha hit:** `firestore.Client()` with no arguments failed with
  `OSError: Project was not passed and could not be determined from the environment`.
  Cause: ADC user credentials identify *you*, not a specific project — there's no
  project ID to infer. Fix: pass it explicitly —
  `firestore.Client(project=GCP_PROJECT_ID)`, with `GCP_PROJECT_ID` as a
  module-level constant in `main.py`.

**Code mapping (dict → Firestore):**

| Old (dict) | New (Firestore) |
|---|---|
| `code not in url_store` | `not urls_collection.document(code).get().exists` |
| `url_store[code] = original_url` | `urls_collection.document(code).set({"original_url": original_url})` |
| `url_store.get(code)` | `urls_collection.document(code).get()`, then check `.exists`, read via `.to_dict()["original_url"]` |
| `del url_store[code]` | `urls_collection.document(code).delete()` — **note:** silently no-ops on a missing doc, so existence must be checked *first* to still return 404 correctly |
| `url_store.items()` | `urls_collection.stream()` — yields document snapshots, each with `.id` and `.to_dict()` |

**How a request actually flows (traced for `POST /shorten`):**
1. `python main.py` starts Flask and opens the Firestore client connection
   (`db = firestore.Client(...)`) — once at boot, before any request arrives.
2. Client sends `POST /shorten` with `{"url": "..."}`.
3. Flask routes it to `shorten_url()`, which validates the URL, then calls
   `generate_short_code()` — a real network call to Firestore to check the random
   code isn't already taken.
4. `.set({...})` — a second real network call that writes the document into the
   actual cloud database (project → database `(default)` → collection `urls` →
   document ID = the short code).
5. Flask returns the JSON response.
6. At this exact point, the document is visible in Console → Firestore → Data.

**Testing decision:** tests run against the real Firestore database, not a local
emulator or mocks. The emulator would add a JVM dependency and extra env-var wiring
for a benefit (faster/offline CI) that doesn't matter yet — cost isn't a concern
since Firestore's free tier is generous and CLAUDE.md already treats it as "no
special handling needed." Might revisit this if test speed becomes a real problem
once GitHub Actions CI (Phase 6) is built.

**Why Firestore's Data tab can look empty after testing:** every verification pass
(manual and automated) ends by deleting whatever it created — the manual walkthrough
explicitly calls `DELETE`, and the pytest `clear_store` fixture wipes the whole
`urls` collection before *and* after every test. An empty collection after running
tests is the expected, correct end-state — not a bug. To see a document persist, run
a manual `POST /shorten` and skip the delete step (see Quick Start above).

### Phase 3 — Dockerize
Multi-stage build: a `builder` stage installs Python dependencies (`pip install
--user`), and a separate minimal runtime stage copies only the installed packages
and `main.py` from it — no compilers or pip caches end up in the final image. Base
image is `python:3.12-slim`. The container runs as a dedicated `appuser` (created
via `useradd --create-home`), not root. Flask's dev server is replaced by
**gunicorn** as the actual production process.

**A real gunicorn/Firestore gotcha, and the fix already in place:** `main.py`
creates its Firestore client **lazily** — on first request, via a
`get_urls_collection()` helper backed by a module-level `_db_client` cache — instead
of eagerly at import time. Reason: gunicorn's master process imports `main.py` once,
then *forks* worker processes from it (`CMD ... --workers 2 --threads 4`). gRPC
clients (used internally by the Firestore client library) aren't fork-safe — a
client created in the master *before* the fork can hang or crash inside the forked
workers. Creating it lazily means each worker creates its own client only after
it's already running as its own process, sidestepping the issue entirely.

**Dockerfile mechanics worth knowing:**
- `COPY --from=builder /root/.local /home/appuser/.local` — copies only the
  installed pip packages from the builder stage, not the build-time cruft.
- `ENV PATH=/home/appuser/.local/bin:$PATH` — pip installed with `--user` puts
  scripts (including `gunicorn` itself) under `~/.local/bin`, which isn't on `PATH`
  by default; this makes `gunicorn` resolvable in the final `CMD`.
- `ENV PORT=8080` is a *default* — Cloud Run injects its own `PORT` at container
  runtime, which overrides this; it just means `docker run` works locally without
  passing `-e PORT=8080` manually.
- `CMD exec gunicorn --bind 0.0.0.0:$PORT ...` uses **shell form** (not the
  JSON-array form Docker's linter suggests) deliberately — shell form is required
  for `$PORT` to actually get expanded at container startup. The `exec` at the
  front avoids the usual downside of shell-form `CMD` (an intermediate shell
  process swallowing OS signals): `exec` replaces the shell process with gunicorn
  directly, so Cloud Run's shutdown `SIGTERM` reaches gunicorn correctly.
- One instruction-syntax gotcha hit while fixing this: Dockerfiles don't support
  trailing `# comment`s on most instructions the way shell scripts do — only `RUN`
  (whose entire line is handed to a real shell) honors them. On `COPY`/`ENV`/etc.,
  a trailing `#comment` gets parsed as extra literal arguments instead of being
  ignored, breaking the instruction. Fix: put the comment on its own line above.

**Local testing nuance:** the container has no gcloud config baked in, so it can't
use Application Default Credentials the way the host machine does. For local
`docker run` testing only, the host's ADC file gets mounted in and pointed to via
an env var:
```powershell
docker run -d -p 8080:8080 `
  -e GOOGLE_APPLICATION_CREDENTIALS=/tmp/adc.json `
  -v "$env:APPDATA\gcloud\application_default_credentials.json:/tmp/adc.json:ro" `
  url-shortener:phase3
```
(Note: this must be run from PowerShell, not Git Bash — Git Bash's MSYS runtime
auto-translates `/tmp/adc.json`-style arguments into Windows host paths before
Docker ever sees them, silently corrupting the mount.) Real deployment (Phase 5)
uses the Cloud Run service's attached service account instead — no ADC or mounted
credentials involved at all in production, this is a local-testing-only workaround.

**Verified:** `docker build` succeeds; container runs as `appuser` (uid 1000, not
root); all 5 endpoints behave identically to the non-containerized version, tested
against real Firestore; final image is `python:3.12-slim` base + ~63MB of app
layers.

### Phase 4 — Terraform: Artifact Registry + service account + IAM
First Terraform phase. Local state (no remote/GCS backend) — deliberate
simplicity choice for a solo project; state files are gitignored
(`*.tfstate`), but `.terraform.lock.hcl` **is** committed (it pins exact
provider versions/checksums for reproducibility, unlike the downloaded
provider binaries in `.terraform/`, which aren't).

**Resources created (`terraform/`):**
- `google_project_service` × 2 — declaratively enables `artifactregistry.googleapis.com`
  and `iam.googleapis.com`, instead of a manual `gcloud services enable` step.
- `google_artifact_registry_repository` (`url-shortener`, `us-central1`, DOCKER
  format) — with a cleanup policy active from creation (`cleanup_policy_dry_run
  = false`), not bolted on later:
  ```hcl
  cleanup_policies {
    id     = "delete-old-versions"
    action = "DELETE"
    condition { tag_state = "ANY" }
  }
  cleanup_policies {
    id     = "keep-latest-n"
    action = "KEEP"
    most_recent_versions { keep_count = var.image_keep_count }  # 3
  }
  ```
  `KEEP` policies take priority over `DELETE` when both match a version — net
  effect: keep the last 3 image pushes, auto-delete everything older, directly
  enforcing the 0.5GB Artifact Registry free-tier cap from CLAUDE.md.
- `google_service_account` (`url-shortener-run-sa`) — a dedicated **runtime**
  identity for the future Cloud Run service (Phase 5). Deliberately separate
  from any future CI/CD deployer identity (Phase 7, via Workload Identity
  Federation) — the running container shouldn't have permission to deploy new
  revisions or push images, only to do its actual job.
- `google_project_iam_member` — grants that service account exactly one role,
  `roles/datastore.user` (Firestore Native mode's standard read/write role;
  Firestore has no finer-grained IAM than project level). Used `_iam_member`
  specifically (not `_iam_binding` or a full policy resource) so this only ever
  touches this one grant, without fighting over ownership of the whole role's
  member list.

**Deliberately not granted:** Artifact Registry or logging roles on the runtime
SA. Cloud Run pulls images via its own Google-managed service agent (not the
runtime SA), and this app's stdout/stderr logging is captured by the Cloud Run
platform itself — neither needs the runtime SA to call those APIs directly.

**Verified:** `terraform plan` showed exactly 5 resources to add, 0 changed, 0
destroyed, reviewed line-by-line before applying. Post-`apply`, cross-checked
against live GCP state (not just Terraform's own report) via `gcloud artifacts
repositories describe`, `gcloud iam service-accounts describe`, and `gcloud
projects get-iam-policy` — all three match the Terraform config exactly.

---

## Roadmap (remaining phases)
Full detail in [CLAUDE.md](CLAUDE.md).
- **Phase 5** — Terraform: Cloud Run service (`min-instances=0`) + Firestore database resource
- **Phase 6** — GitHub Actions CI (lint + test on PR)
- **Phase 7** — GitHub Actions CD (build, push, deploy on merge to `main`)
- **Phase 8** — GitHub Actions Terraform plan (PR) / apply (merge)
- **Phase 9** — Architecture diagram + final setup instructions
