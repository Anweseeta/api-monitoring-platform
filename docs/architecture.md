# Architecture

## Components

```
┌─────────────┐      ┌─────────────┐      ┌─────────────┐
│   React SPA │─────▶│   FastAPI   │─────▶│   MongoDB   │
│  (Vercel)   │◀─────│  (Render)   │◀─────│   (Atlas)   │
└─────────────┘      └──────┬──────┘      └─────────────┘
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
     ┌────────────────┐        ┌────────────────┐
     │   Scheduler    │───────▶│ External APIs  │
     │  (in-process)  │ checks │ (monitored)    │
     └───────┬────────┘        └────────────────┘
             │ state transitions
             ▼
     ┌────────────────┐       ┌──────────────┐
     │ Incident engine│──────▶│Notifications │
     │                │       │SMTP + webhook│
     └────────────────┘       └──────────────┘
```

| Component | Responsibility |
|-----------|----------------|
| React SPA | Auth, monitor/incident/settings CRUD UI, dashboard charts. Stores JWT in `localStorage` (`access_token`); Axios interceptor attaches `Authorization: Bearer <token>`; 401 → redirect `/login`. |
| FastAPI backend | REST API under `/api` (JWT-protected), unprotected demo endpoints under `/demo/*`, health probes at `/health` and `/health/db`. Owns the scheduler, incident engine, SSRF guard, and notification dispatch. |
| MongoDB | System of record: `users`, `apis`, `checks`, `incidents`, `incident_events`, `webhooks`, `activity_logs`, `settings`. See [database-schema.md](database-schema.md). |
| Scheduler | In-process (e.g. APScheduler) background loop. Every tick it finds monitors that are due (`active == true` and `now - last_checked_at >= interval`) and runs a check. |
| Incident engine | Consumes check outcomes per monitor; opens/escalates/resolves incidents per the state machine below. |
| Notifications | On `incident.created`, `incident.resolved`, `api.down`, `api.recovered`: sends SMTP email (if configured) and POSTs the dispatch payload to each active webhook subscribed to the event. |

## Request/response conventions

- All app routes are prefixed `/api`; all are JWT Bearer protected except `/demo/*`, `/health`, `/health/db`, `/api/auth/register`, `/api/auth/login`.
- Success: `{ "success": true, "data": {...} }`. Lists add `"pagination": { "page", "page_size", "total", "pages" }`.
- Error (always this shape, with the appropriate HTTP status): `{ "success": false, "message": "...", "error_code": "..." }`.
- IDs are 24-char hex strings (Mongo ObjectIds); timestamps are ISO-8601 UTC (`2026-09-22T13:00:00Z`).
- Pagination params: `page` (1-based, default 1), `page_size` (default 20, max 100).

## Data flow: a scheduled check

1. Scheduler tick selects due monitors: `active == true`, `last_checked_at` older than `interval` (or never checked).
2. For each monitor, the checker issues the HTTP request:
   - method from `method` ∈ `GET, POST, PUT, PATCH, DELETE, HEAD`
   - `headers` + `body` (body only for POST/PUT/PATCH)
   - `timeout` seconds (1–120); expect `expected_status` (default 200)
3. The target URL is validated by the SSRF guard **before** DNS resolution and the resolved IP is re-checked (see SSRF below).
4. The check result is persisted to `checks` (`status_code`, `response_time_ms`, `success`, `error`, `timed_out`, `response_size_bytes`, `timestamp`).
5. Monitor counters are updated:
   - success → `consecutive_successes += 1`, `consecutive_failures = 0`
   - failure → `consecutive_failures += 1`, `consecutive_successes = 0`
   - `last_checked_at = now`, `updated_at = now`
6. Monitor `status` is recomputed:
   - `paused` if `active == false`
   - `down` if `consecutive_failures >= failure_threshold`
   - `degraded` if last check succeeded but `response_time_ms > degraded_latency_ms` (setting, default 1000ms)
   - `healthy` otherwise
7. The incident engine evaluates thresholds and may open/escalate/resolve incidents and fire notifications.
8. Old results are pruned: `checks` older than `RESULTS_RETENTION_DAYS` (default 30) are deleted by the scheduler.

`POST /api/monitors/{id}/test` performs the same pipeline immediately (steps 2–7) on demand and persists the result.

## Scheduler design

- **In-process**, not a separate worker: the scheduler lives inside the FastAPI process (started on app startup, shut down on app shutdown). This keeps the deployment to a single Render web service with no extra infrastructure.
- **Interval model**: each monitor carries its own `interval` ∈ `[60, 300, 600, 900, 1800, 3600]` seconds. The scheduler runs on a short tick (e.g. every 30–60s) and dispatches monitors whose `interval` has elapsed since `last_checked_at`.
- **Concurrency**: checks for different monitors run concurrently (async/threads); a slow target never blocks other monitors.
- **Idempotency / overlap**: a monitor is only dispatched if no check is currently in flight for it; a stuck check is bounded by `timeout`.
- **Retention**: a periodic cleanup job deletes `checks` older than `RESULTS_RETENTION_DAYS`.
- **Single-instance caveat**: with one web-service instance there is exactly one scheduler. If the deployment is ever scaled to multiple instances, only one may run the scheduler (leader election or a single-instance constraint) to avoid duplicate checks and duplicate incidents.

## Incident state machine

Wire status values (lowercase): `open → investigating → identified → monitoring → resolved`.

```
                    failure_threshold consecutive failures
   (no open incident) ───────────────────────────────────▶ OPEN (severity: high)
                                                                     │
                                                                     │ downtime > 15 min
                                                                     ▼
                                                                OPEN (severity: critical)
                                                                event: escalated
                                                                     │
        ┌──────────────────── recovery_threshold ─────────────────────┘
        │               consecutive successes → AUTO-RESOLVED
        │               (event: auto_resolved, resolved_at stamped)
        │
        │  manual transitions via PUT /api/incidents/{id}
        │  or POST /api/incidents/{id}/resolve
        ▼
   investigating ⇄ identified ⇄ monitoring ──▶ resolved
        (setting status=resolved stamps resolved_at; resolution_notes optional)
```

Rules:

- **Dedup**: exactly ONE open incident per `api_id`. While one is open, further failures append `incident_events` (event types `detected`/`updated`/`escalated`/`note`) instead of creating a new incident.
- **Auto-create**: `FAILURE_THRESHOLD` (default 3) consecutive failures → incident with `severity: high`, `created_by: "system"`, `status: open`. Fires `incident.created` and `api.down` notifications.
- **Escalation**: if the open incident's downtime exceeds 15 minutes → `severity: critical`, event `escalated`.
- **Auto-resolve**: `RECOVERY_THRESHOLD` (default 2) consecutive successes while an incident is open → `status: resolved`, `resolved_at` stamped, event `auto_resolved`. Fires `incident.resolved` and `api.recovered` notifications.
- **Manual**: `POST /api/incidents` creates a user incident (`created_by: "user"`, status `open`). `PUT /api/incidents/{id}` can move status between states; setting `resolved` stamps `resolved_at`.
- **Incident events** (`incident_events` collection): `{ incident_id, timestamp, event_type, message }`, event types `detected | created | updated | resolved | note | auto_resolved | escalated` — the timeline shown on the incident detail page.

## SSRF protection

All outbound HTTP — monitor checks **and** webhook deliveries — pass through the SSRF guard:

1. **Scheme allowlist**: only `http` and `https`; anything else is rejected (`SSRF_BLOCKED`).
2. **Port validation**: port must be 1–65535.
3. **DNS → IP check**: the hostname is resolved and every resulting IP is checked with `ipaddress` against:
   - private ranges, loopback (`127.0.0.0/8`, `::1`), link-local, and other reserved ranges
   - cloud metadata endpoints: `169.254.169.254` (AWS/GCP/Azure), `100.100.100.200` (Alibaba), `fd00::/8`
4. **Loopback toggle**: loopback targets are allowed **only** when `MONITOR_ALLOW_LOOPBACK=true` (default `true` so the `/demo/*` endpoints and local targets work out of the box; **set to `false` in production** — see `render.yaml`).
5. Failed validation returns the check as failed with error code `SSRF_BLOCKED` (and for monitor creation, a `400`/`422` validation error) — the request is never sent.

## Notifications

- **Triggers** (events): `incident.created`, `incident.resolved`, `api.down`, `api.recovered`.
- **Email**: via SMTP (`SMTP_HOST/PORT/USERNAME/PASSWORD/FROM`). Sent to the user's email when `notifications.email_enabled` is true in settings.
- **Webhooks**: user-defined (`/api/webhooks`), each with `events[]` subscription and `active` flag. Dispatch POSTs:
  ```json
  { "event": "incident.created", "api": "Payments API", "api_id": "...",
    "severity": "high", "status": "open", "timestamp": "...", "incident_id": "..." }
  ```
  Webhook URLs go through the same SSRF guard as monitor targets.

## Security notes

- Passwords are hashed (bcrypt or equivalent); never stored or returned in plaintext.
- JWTs are signed with `JWT_SECRET` (HS256, 60-minute default expiry). Protect the secret like a password.
- Every data access is scoped to the authenticated `user_id` (monitors, incidents, webhooks, settings, activity) — cross-user access returns `FORBIDDEN`.
- Demo endpoints (`/demo/*`) are intentionally unprotected; they return synthetic responses only and expose no user data.
