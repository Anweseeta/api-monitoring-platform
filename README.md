# API Monitoring & Incident Tracking Platform

A full-stack observability app for watching REST APIs: schedule synthetic health checks, collect latency/status metrics, and automatically track outages as incidents with notifications.

## The problem

Services fail silently. A 500 on your payments endpoint at 2am goes unnoticed until customers complain, and by the time someone looks at logs, the timeline of "when did it start, how long was it down, what did latency look like before" is gone.

## The solution

This platform actively polls your APIs on a schedule you control (1 minute – 1 hour), records every check's status code and latency, and:

- **Detects failures** — after N consecutive failures it opens an incident automatically (escalating to `critical` if downtime exceeds 15 minutes)
- **Detects recovery** — after N consecutive successes it resolves the incident automatically
- **Shows degraded health** — successes slower than your latency threshold are flagged `degraded`, not healthy
- **Notifies you** — email (SMTP) and webhook alerts for `incident.created`, `incident.resolved`, `api.down`, `api.recovered`
- **Keeps a record** — every action is written to an activity log; every incident has an event timeline

## Features

- 🔐 JWT auth (register / login / session restore)
- 📡 Monitor CRUD: GET/POST/PUT/PATCH/DELETE/HEAD checks, custom headers, JSON bodies, per-monitor timeout & interval, expected status
- ⏱️ Background scheduler runs checks on each monitor's interval; manual "test now" checks too
- 🚨 Automatic incident lifecycle: open → (investigating/identified/monitoring) → resolved, with dedup (one open incident per API) and auto-resolve
- 📊 Dashboard: health counts, avg latency, 24h uptime, open incidents, response-time & uptime charts, incident activity charts
- 📈 Per-monitor metrics: uptime %, avg/min/max/p50/p95/p99 latency, error rate, status-code distribution, time series
- 🔔 Webhooks + email notifications; SSRF protection on all outbound checks and webhook URLs
- 🧪 Built-in demo endpoints (`/demo/slow`, `/demo/error`, `/demo/random`, `/demo/echo`) for safe experimentation

## Architecture

```
┌──────────────────┐        HTTP/JSON (JWT Bearer)        ┌──────────────────┐
│   React (Vite)   │ ────────────────────────────────────▶ │  FastAPI (py)    │
│   frontend/      │                                       │  backend/        │
│   Axios + router │ ◀──────────────────────────────────── │  REST /api/*     │
└──────────────────┘                                       └────────┬─────────┘
                                                                    │
                                          ┌─────────────────────────┼─────────────────────────┐
                                          ▼                         ▼                         ▼
                                 ┌────────────────┐        ┌────────────────┐        ┌──────────────────┐
                                 │ MongoDB Atlas  │        │  APScheduler   │        │  External APIs   │
                                 │ apis, results, │        │  in-process    │        │  (your monitored │
                                 │ incidents,     │        │  per-interval  │        │   endpoints)     │
                                 │ users, webhooks│        │  check runner  │        │  + webhooks/SMTP │
                                 └────────────────┘        └────────────────┘        └──────────────────┘
```

- **Frontend (React + Vite + Axios + React Router)** — SPA, token in `localStorage` (`access_token`), Axios interceptor attaches `Authorization: Bearer`, 401 → `/login`.
- **Backend (FastAPI)** — all app routes under `/api`, JWT-protected; demo routes at `/demo/*` are unprotected. Success envelope `{ success, data }`, list envelope adds `pagination`, errors `{ success: false, message, error_code }`.
- **MongoDB** — collections: `users`, `apis` (monitors), `checks`, `incidents`, `incident_events`, `webhooks`, `activity_logs`, `settings`.
- **Scheduler** — in-process scheduler dispatches due monitors by `interval`, runs the check with `timeout`, persists the result, updates monitor status/counters, drives the incident state machine, prunes results older than `RESULTS_RETENTION_DAYS`.
- **Notifications** — fired from incident/monitor state transitions; email via SMTP, webhooks via HTTP POST (SSRF-checked).

## Tech stack

| Layer    | Tech |
|----------|------|
| Frontend | React, Vite, React Router, Axios, Recharts (charts) |
| Backend  | Python 3.12, FastAPI, Uvicorn, APScheduler, PyMongo/Motor, PyJWT, Pydantic |
| Database | MongoDB (local or Atlas) |
| Deploy   | Frontend → Vercel, Backend → Render (web service), DB → MongoDB Atlas |

## Prerequisites

- **Python 3.12+**
- **Node.js 24+** (npm bundled)
- **MongoDB** — either a local `mongod` or a free [MongoDB Atlas](https://www.mongodb.com/cloud/atlas) cluster
- Git

## Quick start

### 1. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example .env            # then edit .env (see Env vars below)
uvicorn app.main:app --reload --port 8000
```

The API is now at `http://localhost:8000` — interactive docs at `http://localhost:8000/docs` (Swagger UI) and `http://localhost:8000/redoc`.

### 2. Frontend

```bash
cd frontend
npm install
cp ../.env.example .env           # or set VITE_API_URL directly; see Env vars
npm run dev                       # http://localhost:5173
```

### 3. Seed demo data (optional)

```bash
cd backend
source .venv/bin/activate
python scripts/seed.py
```

This creates the demo account (see below) plus a few sample monitors so the dashboard isn't empty.

## Environment variables

Copy `.env.example` to `.env` in the project root and tune the values. Both sides read their values from it (the frontend via Vite's `VITE_` prefix).

| Variable | Side | Default | Description |
|----------|------|---------|-------------|
| `MONGODB_URI` | backend | `mongodb://localhost:27017` | MongoDB connection string (Atlas: `mongodb+srv://...`) |
| `DATABASE_NAME` | backend | `api_monitoring` | Database name |
| `JWT_SECRET` | backend | — | **Required.** Secret for signing JWTs (generate with `openssl rand -hex 32`) |
| `JWT_ALGORITHM` | backend | `HS256` | JWT signing algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | backend | `60` | Token lifetime |
| `FRONTEND_URL` | backend | `http://localhost:5173` | Allowed CORS origin |
| `SMTP_HOST` / `SMTP_PORT` | backend | — | SMTP server for email alerts |
| `SMTP_USERNAME` / `SMTP_PASSWORD` | backend | — | SMTP credentials |
| `SMTP_FROM` | backend | — | From address for alert emails |
| `MONITOR_DEFAULT_INTERVAL` | backend | `300` | Default check interval (s) for new monitors |
| `MONITOR_DEFAULT_TIMEOUT` | backend | `10` | Default HTTP timeout (s) |
| `FAILURE_THRESHOLD` | backend | `3` | Consecutive failures before an incident opens |
| `RECOVERY_THRESHOLD` | backend | `2` | Consecutive successes before auto-resolve |
| `MONITOR_ALLOW_LOOPBACK` | backend | `true` | Allow monitoring `localhost`/loopback targets |
| `BACKEND_PUBLIC_URL` | backend | — | Public URL of the API (used in emails/webhooks) |
| `RESULTS_RETENTION_DAYS` | backend | `30` | Scheduler prunes check results older than this |
| `DEGRADED_LATENCY_MS` | backend | `1000` | Success slower than this is marked `degraded` |
| `INCIDENT_ESCALATION_MINUTES` | backend | `15` | Escalate open `high` incidents to `critical` after this many minutes |
| `ENVIRONMENT` | backend | `development` | `production` enables fail-fast guards (refuses default/weak `JWT_SECRET`) |
| `VITE_API_URL` | frontend | `http://localhost:8000` | Base URL the SPA calls (e.g. `https://api.example.com`) |

## Run commands

| Task | Command (run in `backend/`) |
|------|----------------------------|
| Start API (dev) | `uvicorn app.main:app --reload --port 8000` |
| Start API (prod) | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Seed demo data | `python scripts/seed.py` |
| Run tests | `pytest` |

| Task | Command (run in `frontend/`) |
|------|-----------------------------|
| Install deps | `npm install` |
| Dev server | `npm run dev` |
| Production build | `npm run build` |
| Preview build | `npm run preview` |

## MongoDB Atlas setup

1. Create a free cluster at [cloud.mongodb.com](https://cloud.mongodb.com).
2. **Database Access** → add a database user (readWrite on your DB).
3. **Network Access** → add `0.0.0.0/0` (or your server's IP) to the IP allowlist.
4. **Connect** → Drivers → copy the `mongodb+srv://...` URI and set it as `MONGODB_URI` in `.env`.
5. The backend creates the collections and indexes it needs on first run.

Local alternative: run `mongod --dbpath <data-dir>` and keep the default `mongodb://localhost:27017`.

## Demo account

> ⚠️ **Demo/development only — change or disable in production.** This account is created by `python scripts/seed.py` for local demos; it must not exist in a production deployment.

```
Email:    demo@example.com
Password: DemoPass123!
```

The seed script also provisions a few monitors pointing at the built-in `/demo/*` endpoints (healthy, slow, flaky, erroring) so you can watch the incident state machine work.

## API docs

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- Human-readable reference: [`docs/api-documentation.md`](docs/api-documentation.md)
- The canonical contract is [`API_CONTRACT.md`](API_CONTRACT.md)

Health probes: `GET /health` → `{ "status": "healthy" }`, `GET /health/db` → `{ "status": "healthy", "db": "connected" }`.

## Tests

```bash
cd backend
source .venv/bin/activate
pytest
```

## Deployment

| Component | Where | Config |
|-----------|-------|--------|
| Frontend | Vercel | [`frontend/vercel.json`](frontend/vercel.json) handles SPA rewrites; set **Root Directory** to `frontend` in the dashboard; set `VITE_API_URL` to your Render backend URL |
| Backend | Render | Blueprint in [`render.yaml`](render.yaml): web service, `rootDir: backend`, build `pip install -r requirements.txt`, start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`, health check `/health`; set `MONGODB_URI` (mark as secret, `sync: false`), `JWT_SECRET`, `FRONTEND_URL` |
| Database | MongoDB Atlas | Free tier is enough to start; use the connection string as `MONGODB_URI` |
| Docker | anywhere | [`docs/deployment/docker-compose.yml`](docs/deployment/docker-compose.yml) + `backend.Dockerfile` / `frontend.Dockerfile` in the same folder; copy each Dockerfile next to its code before building standalone |

Full step-by-step guide: [`DEPLOYMENT.md`](DEPLOYMENT.md) (Atlas → Render → Vercel). Deeper reference: [`docs/deployment.md`](docs/deployment.md).

## Screenshots

_Screenshots go here._

- `docs/screenshots/dashboard.png` — Dashboard overview
- `docs/screenshots/monitor-detail.png` — Monitor detail with latency charts
- `docs/screenshots/incident-detail.png` — Incident detail with event timeline
- `docs/screenshots/monitors-list.png` — Monitors list

## Project structure

```
api-monitoring-platform/
├── API_CONTRACT.md            # canonical API contract (source of truth)
├── README.md                  # this file
├── .env.example               # documented env template (backend + frontend)
├── .gitignore
├── render.yaml                # Render blueprint for the backend
├── vercel.json                # in frontend/ — SPA rewrites for Vercel
├── docs/
│   ├── architecture.md        # components, data flow, scheduler, incidents, SSRF
│   ├── api-documentation.md   # human-readable endpoint reference
│   ├── database-schema.md     # collections, fields, indexes
│   ├── deployment.md          # Vercel + Render + Atlas step-by-step
│   └── deployment/
│       ├── docker-compose.yml # local full-stack via Docker
│       ├── backend.Dockerfile # copy to backend/Dockerfile
│       └── frontend.Dockerfile# copy to frontend/Dockerfile
├── backend/                   # FastAPI app (built by backend agent)
│   ├── app/
│   │   ├── main.py            # app factory, /health, /api, /demo routes
│   │   ├── api/               # route modules (auth, monitors, incidents, ...)
│   │   ├── core/              # config, security (JWT), db
│   │   ├── models/            # Pydantic schemas
│   │   ├── services/          # checker, scheduler, incident engine, notifications
│   │   └── utils/             # ssrf guard, etc.
│   ├── scripts/
│   │   └── seed.py            # demo account + sample monitors
│   ├── tests/                 # pytest suite
│   └── requirements.txt
└── frontend/                  # React + Vite SPA (built by frontend agent)
    ├── src/
    │   ├── pages/             # Login, Dashboard, Monitors, Incidents, Activity, Settings
    │   ├── components/
    │   ├── api/               # Axios client + interceptor
    │   └── context/           # AuthContext
    ├── index.html
    ├── package.json
    └── vite.config.ts
```

## Further reading

- [`docs/architecture.md`](docs/architecture.md) — how the pieces fit together
- [`docs/database-schema.md`](docs/database-schema.md) — collections and indexes
- [`API_CONTRACT.md`](API_CONTRACT.md) — the contract everything is built against

## License

MIT
