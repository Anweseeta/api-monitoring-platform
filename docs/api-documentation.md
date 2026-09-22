# API Documentation

Human-readable reference for every endpoint. This mirrors [`API_CONTRACT.md`](../API_CONTRACT.md), which is the source of truth — if anything disagrees, the contract wins.

**Base URL:** all app routes are prefixed `/api`. **Auth:** `Authorization: Bearer <access_token>` on every protected route (all of them except the ones marked "public").

**Envelopes:**

- Success: `{ "success": true, "data": {...} }`
- List: `{ "success": true, "data": [...], "pagination": { "page": 1, "page_size": 20, "total": 42, "pages": 3 } }`
- Error: `{ "success": false, "message": "Monitor not found", "error_code": "MONITOR_NOT_FOUND" }`

---

## Auth — public

### `POST /api/auth/register`
Create an account and get a token.

```jsonc
// request
{ "name": "Ada Lovelace", "email": "ada@example.com", "password": "s3cret!" }
// 201 response
{ "success": true, "data": {
    "user": { "id": "...", "name": "Ada Lovelace", "email": "ada@example.com", "created_at": "..." },
    "access_token": "<jwt>", "token_type": "bearer" } }
```
Errors: `USER_EXISTS` (409), `VALIDATION_ERROR` (422).

### `POST /api/auth/login`
```jsonc
// request
{ "email": "ada@example.com", "password": "s3cret!" }
// 200 response — same shape as register
```
Errors: `INVALID_CREDENTIALS` (401).

### `GET /api/auth/me` 🔒
Returns the current user: `200 { "success": true, "data": { "user": {...} } }`. Errors: `UNAUTHORIZED` (401), `INVALID_TOKEN` (401).

---

## Monitors 🔒 — the `apis` collection

Monitor object: `{ id, user_id, name, url, method, description, interval, timeout, expected_status, headers, body, active, status, consecutive_failures, consecutive_successes, last_checked_at, uptime_24h, created_at, updated_at }`.

- `interval` ∈ `[60, 300, 600, 900, 1800, 3600]` (seconds); `timeout` 1–120s; `method` ∈ `[GET, POST, PUT, PATCH, DELETE, HEAD]`; `body` only for POST/PUT/PATCH.
- `status` ∈ `healthy | degraded | down | paused` (computed by backend).

### `GET /api/monitors?search=&status=&method=&page=&page_size=`
Paginated monitor list, filterable by name/URL search, status, and method.

### `POST /api/monitors` → 201
```jsonc
// request
{ "name": "Payments API", "url": "https://api.example.com/health", "method": "GET",
  "interval": 300, "timeout": 10, "expected_status": 200,
  "headers": { "Authorization": "Bearer x" }, "body": null, "description": "Prod health endpoint" }
// 201 response
{ "success": true, "data": { /* monitor */ } }
```
Errors: `VALIDATION_ERROR` (422), `SSRF_BLOCKED` (400 — e.g. private IP target).

### `GET /api/monitors/{id}`
Monitor plus a computed `metrics` object (same shape as `/metrics?period=24h`).

### `PUT /api/monitors/{id}`
Update any subset of fields → `200 { success, data: monitor }`.

### `DELETE /api/monitors/{id}`
→ `200 { "success": true, "data": null }`. Errors: `MONITOR_NOT_FOUND` (404).

### `POST /api/monitors/{id}/test`
Runs an immediate manual check (same pipeline as the scheduler, persisted as a check result, can trigger incident logic).
→ `200 { success, data: check_result }`. If the check itself failed, error code `TEST_FAILED` is returned **with the result still in `data`**.

### `POST /api/monitors/{id}/pause` → sets `active=false`; `POST /api/monitors/{id}/resume` → sets `active=true`.
Both → `200 { success, data: monitor }`.

---

## Monitoring results 🔒

Check result object: `{ id, api_id, timestamp, status_code, response_time_ms, success, error, timed_out, response_size_bytes }`.

### `GET /api/monitors/{id}/checks?since=&until=&page=&page_size=`
Paginated check history, newest first. `since`/`until` are ISO-8601 timestamps.

### `GET /api/monitors/{id}/metrics?period=24h|7d|30d`
```jsonc
{ "success": true, "data": {
    "uptime_percent": 99.95, "avg_latency_ms": 120.5, "min_latency_ms": 45,
    "max_latency_ms": 900, "p50_latency_ms": 110, "p95_latency_ms": 300,
    "p99_latency_ms": 500, "total_checks": 100, "successful_checks": 99,
    "failed_checks": 1, "error_rate_percent": 1.0,
    "status_code_distribution": { "2xx": 99, "3xx": 0, "4xx": 0, "5xx": 1, "timeout": 0, "connection_error": 0 },
    "response_time_series": [{ "timestamp": "...", "avg_ms": 120 }],
    "uptime_series": [{ "timestamp": "...", "uptime": 100.0 }] } }
```

### `GET /api/monitors/{id}/uptime?period=24h|7d|30d`
→ `{ success, data: { uptime_percent, total_checks, successful_checks } }`.

Results older than `RESULTS_RETENTION_DAYS` (default 30) are pruned by the scheduler.

---

## Incidents 🔒

Incident object: `{ id, api_id, user_id, title, description, status, severity, started_at, detected_at, resolved_at, duration_seconds, root_cause, resolution_notes, created_by, updated_at }`.

- `status` ∈ `open | investigating | identified | monitoring | resolved`
- `severity` ∈ `low | medium | high | critical`

### `GET /api/incidents?status=&severity=&api_id=&from=&to=&search=&page=&page_size=`
Paginated list. Also returns `summary: { total, open, resolved, critical, avg_resolution_seconds }`.

### `POST /api/incidents` → 201
```jsonc
// request
{ "api_id": "...", "title": "Payments API is down", "description": "...", "severity": "high" }
// creates a manual incident: status=open, created_by="user"
```

### `GET /api/incidents/{id}`
→ `{ success, data: { incident, api, events } }` — incident, its monitor, and the event timeline.

### `PUT /api/incidents/{id}`
Update any of `{ status, severity, root_cause, resolution_notes }`. Setting `status: "resolved"` stamps `resolved_at`.

### `DELETE /api/incidents/{id}` → 200.

### `POST /api/incidents/{id}/resolve`
```jsonc
// request (body optional)
{ "resolution_notes": "Restarted the payment service pod." }
```

Errors: `INCIDENT_NOT_FOUND` (404), `API_NOT_FOUND` (404), `FORBIDDEN` (403), `VALIDATION_ERROR` (422).

Auto behavior: incident auto-opens after `FAILURE_THRESHOLD` (default 3) consecutive failures (`severity: high`, escalates to `critical` after 15 min downtime), and auto-resolves after `RECOVERY_THRESHOLD` (default 2) consecutive successes. One open incident per API — further failures append to `incident_events`.

---

## Dashboard 🔒

### `GET /api/dashboard/summary`
```jsonc
{ "success": true, "data": {
    "total_apis": 12, "healthy_apis": 9, "degraded_apis": 1, "down_apis": 1, "paused_apis": 1,
    "avg_response_time_ms": 214.5, "overall_uptime_24h": 99.2, "open_incidents": 2,
    "recent_incidents": [/* 5 */], "recent_activity": [/* 8 */],
    "health_overview": { "healthy": 9, "degraded": 1, "down": 1, "paused": 1 } } }
```

### `GET /api/dashboard/uptime?period=24h|7d|30d`
→ `{ success, data: { points: [{ timestamp, uptime }] } }`

### `GET /api/dashboard/latency?period=24h|7d|30d`
→ `{ success, data: { points: [{ timestamp, avg_ms }] } }`

### `GET /api/dashboard/incidents?period=24h|7d|30d`
→ `{ success, data: { points: [{ timestamp, created, resolved }] } }`

---

## Activity logs 🔒

### `GET /api/activity?resource_type=&action=&page=&page_size=`
Paginated log entries: `{ id, user_id, action, resource_type, resource_id, resource_name, timestamp, ip, user_agent }`.

Recorded actions: `user.registered`, `user.logged_in`, `api.created`, `api.updated`, `api.deleted`, `api.paused`, `api.resumed`, `api.tested`, `incident.created`, `incident.updated`, `incident.resolved`, `incident.auto_created`, `incident.auto_resolved`, `settings.updated`, `webhook.created`, `webhook.deleted`.

---

## Settings 🔒

### `GET /api/settings`
```jsonc
{ "success": true, "data": {
    "default_timeout": 10, "default_interval": 300,
    "failure_threshold": 3, "recovery_threshold": 2,
    "degraded_latency_ms": 1000, "results_retention_days": 30,
    "notifications": { "email_enabled": true, "webhook_enabled": true },
    "profile": { "name": "Ada Lovelace", "email": "ada@example.com" } } }
```

### `PUT /api/settings`
Body: any subset of the above. `notifications.*` and `profile.name` are persisted; `profile.email` is read-only.

---

## Webhooks 🔒

### `GET /api/webhooks`
List: `{ id, name, url, events, active, created_at }`.

### `POST /api/webhooks` → 201
```jsonc
{ "name": "Slack alerts", "url": "https://hooks.example.com/xyz",
  "events": ["incident.created", "incident.resolved"], "active": true }
```
`events` ∈ `incident.created | incident.resolved | api.down | api.recovered`.

### `DELETE /api/webhooks/{id}` → 200.

Dispatch payload sent to the webhook URL:
```jsonc
{ "event": "incident.created", "api": "Payments API", "api_id": "...",
  "severity": "high", "status": "open", "timestamp": "...", "incident_id": "..." }
```
Errors: `WEBHOOK_NOT_FOUND` (404), `VALIDATION_ERROR` (422). Webhook URLs are SSRF-checked like monitor targets.

---

## Demo endpoints — public (unprotected)

Handy targets for trying the platform without pointing it at a real API (loopback must be allowed: `MONITOR_ALLOW_LOOPBACK=true`).

| Method & path | Behavior |
|---|---|
| `GET /demo/health` | `200 { "status": "healthy" }` |
| `GET /demo/slow` | waits ~3s → `200 { "status": "ok", "delay_ms": 3000 }` (great for testing `degraded` status) |
| `GET /demo/error` | `500 { "status": "error" }` (triggers failure counting) |
| `GET /demo/random` | randomly 200 or 500 |
| `POST /demo/echo` | echoes `{ received: <json body>, method, headers_redacted }` |

## Health probes — public

| Method & path | Response |
|---|---|
| `GET /health` | `{ "status": "healthy" }` (Render health check) |
| `GET /health/db` | `{ "status": "healthy", "db": "connected" }` |

## Error codes (complete)

`USER_EXISTS`, `INVALID_CREDENTIALS`, `UNAUTHORIZED`, `INVALID_TOKEN`, `MONITOR_NOT_FOUND`, `INCIDENT_NOT_FOUND`, `API_NOT_FOUND`, `WEBHOOK_NOT_FOUND`, `VALIDATION_ERROR`, `FORBIDDEN`, `SSRF_BLOCKED`, `TEST_FAILED`.

Interactive docs (auto-generated from the code): `/docs` (Swagger UI), `/redoc` (ReDoc).
