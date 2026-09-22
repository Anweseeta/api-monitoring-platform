# Backend — API Monitoring & Incident Tracking Platform

FastAPI + Motor (async MongoDB) backend. Implements `API_CONTRACT.md` exactly:
`/api/*` routes, `{success, data, pagination}` envelopes, the error envelope
`{"success": false, "message", "error_code"}`, Bearer JWT auth, ObjectId hex ids,
ISO-8601 UTC timestamps, lowercase incident status/severity wire values.

## Layout

```
backend/
  app/
    main.py            # app factory, CORS, error-envelope handlers, lifespan
    api/               # routers: auth, monitors, incidents, dashboard, activity,
                       #          settings, webhooks (+ demo/health endpoints)
    core/              # config (pydantic-settings), security (JWT/bcrypt), deps
    models/            # serializers: Mongo docs -> contract wire dicts
    schemas/           # request validation (pydantic v2)
    services/          # monitor, incident (dedup), metrics, activity,
                       #          notification (SMTP + webhooks), settings
    monitoring/        # engine.py (centralized AsyncIOScheduler) + ssrf.py
    database/          # motor client, index definitions
    utils/             # pagination, time helpers
  scripts/seed.py      # demo data seeder
  tests/               # pytest suite (uses apimonitor_test database)
  requirements.txt  .env.example  pytest.ini  README.md
```

## Setup

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env   # then edit JWT_SECRET etc.
```

### MongoDB

```bash
sudo mkdir -p /data/db
sudo mongod --fork --logpath /tmp/mongod.log --dbpath /data/db
```

Defaults: `MONGODB_URI=mongodb://localhost:27017`, `DATABASE_NAME=apimonitor`.

> Production: set `MONITOR_ALLOW_LOOPBACK=false` so monitor checks can't hit
> loopback/private IPs (it's `true` by default so the bundled `/demo/*`
> endpoints work out of the box). Always set a real `JWT_SECRET`.

## Run

```bash
cd backend
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Seed demo data **before** starting the server (so the scheduler picks up the
demo monitors), or restart the server after seeding:

```bash
cd backend
BACKEND_PUBLIC_URL=http://localhost:8000 .venv/bin/python scripts/seed.py
```

Seeded **DEMO ONLY** credentials: `demo@example.com` / `DemoPass123!`

## Test

```bash
cd backend
.venv/bin/pytest -q
```

Tests use the `apimonitor_test` database (set via env in `tests/conftest.py`)
and spin up the real `/demo/*` endpoints on `127.0.0.1:8123` in-process.

## Monitoring engine notes

- One `AsyncIOScheduler`; one interval job per active monitor (`monitor:<id>`).
- Jobs are (re)scheduled on create/update/pause/resume/delete.
- `check()` honors method/url/headers/body/timeout, measures latency, records
  the check, updates consecutive counters; `failure_threshold` (default 3)
  auto-creates an incident (dedup: one open incident per api);
  `recovery_threshold` (default 2) auto-resolves; high → critical escalation
  after `INCIDENT_ESCALATION_MINUTES` (default 15) of downtime.
- Results older than each user's `results_retention_days` (default 30) are
  pruned by a scheduled job.
- SSRF guard (`monitoring/ssrf.py`): resolves the hostname and blocks
  private/reserved/link-local/multicast/loopback (unless allowed) and cloud
  metadata IPs; only `http(s)` and ports 1–65535.
- Auth headers are never logged; `/demo/echo` redacts them (`headers_redacted`).
