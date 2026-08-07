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
| 3 | Dockerize | ⬜ Not started |
| 4 | Terraform: Artifact Registry + IAM | ⬜ Not started |
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

### Phase 3 — Dockerize (not started)
Planned: multi-stage Docker build (builder stage installs deps, runtime stage copies
only what's needed), `python:3.13-slim` base, non-root user, gunicorn replacing
Flask's dev server, listening on Cloud Run's injected `$PORT`. Will be filled in once built.

---

## Roadmap (remaining phases)
Full detail in [CLAUDE.md](CLAUDE.md).
- **Phase 4** — Terraform: Artifact Registry (with cleanup policy for the 0.5GB free cap) + service account + least-privilege IAM
- **Phase 5** — Terraform: Cloud Run service (`min-instances=0`) + Firestore database resource
- **Phase 6** — GitHub Actions CI (lint + test on PR)
- **Phase 7** — GitHub Actions CD (build, push, deploy on merge to `main`)
- **Phase 8** — GitHub Actions Terraform plan (PR) / apply (merge)
- **Phase 9** — Architecture diagram + final setup instructions
