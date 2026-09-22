# API CONTRACT — Source of Truth

All subagents MUST build to this contract. Frontend, backend, and tests must match it exactly.
Do not invent routes, rename fields, or change envelopes.

## Base

- Backend base URL from env: frontend uses `VITE_API_URL`, backend demo/health at `/`.
- All app routes are prefixed `/api`. Demo endpoints (spec §26) are **unprotected** at `/demo/*`.
- Auth: JWT Bearer. Login/Register return `{ access_token, token_type: "bearer", user }`.
  Every protected request sends header `Authorization: Bearer <access_token>`.

## Envelopes

Success:
```json
{ "success": true, "data": { ... } }
```
For lists: `{ "success": true, "data": [ ... ], "pagination": { "page": 1, "page_size": 20, "total": 42, "pages": 3 } }`

Error (always this shape, appropriate HTTP status):
```json
{ "success": false, "message": "Monitor not found", "error_code": "MONITOR_NOT_FOUND" }
```

## IDs

- Mongo ObjectIds serialized as 24-char hex strings everywhere (`id`, `api_id`, `user_id`).
- Timestamps are ISO-8601 UTC strings (`2026-09-22T13:00:00Z`).

## Auth

- `POST /api/auth/register` — body `{ name, email, password }` → `201 { success, data: { user, access_token, token_type } }`. user = `{ id, name, email, created_at }`.
- `POST /api/auth/login` — body `{ email, password }` → `200` same shape as register.
- `GET /api/auth/me` — → `200 { success, data: { user } }`.
- Error codes: `USER_EXISTS`, `INVALID_CREDENTIALS`, `UNAUTHORIZED`, `INVALID_TOKEN`.

## Monitors (`apis` collection)

Monitor object:
```json
{
  "id": "...", "user_id": "...", "name": "Payments API", "url": "https://...",
  "method": "GET", "description": "", "interval": 300, "timeout": 10,
  "expected_status": 200, "headers": {"Authorization": "Bearer x"}, "body": null,
  "active": true, "status": "healthy",
  "consecutive_failures": 0, "consecutive_successes": 0,
  "last_checked_at": null, "uptime_24h": 100.0,
  "created_at": "...", "updated_at": "..."
}
```
- `interval` seconds, one of `[60,300,600,900,1800,3600]`. `timeout` 1–120s.
- `method` in `[GET,POST,PUT,PATCH,DELETE,HEAD]`.
- `body`: JSON value or null (only for POST/PUT/PATCH). Stored as object/string.
- `status` ∈ `healthy | degraded | down | paused` (computed by backend).
- `degraded` = success but latency > `degraded_latency_ms` threshold (default 1000ms, in settings).
- Routes:
  - `GET /api/monitors?search=&status=&method=&page=&page_size=` → paginated list
  - `POST /api/monitors` → `201 { success, data: monitor }`
  - `GET /api/monitors/{id}` → monitor + computed `metrics` object (see monitoring)
  - `PUT /api/monitors/{id}` → `200 { success, data: monitor }`
  - `DELETE /api/monitors/{id}` → `200 { success, data: null }`
  - `POST /api/monitors/{id}/test` → `200 { success, data: check_result }` (immediate manual check, also persisted as a check + may trigger incident logic)
  - `POST /api/monitors/{id}/pause` → `200 { success, data: monitor }` (active=false)
  - `POST /api/monitors/{id}/resume` → `200 { success, data: monitor }` (active=true)
- Error codes: `MONITOR_NOT_FOUND`, `VALIDATION_ERROR`, `FORBIDDEN`, `SSRF_BLOCKED`, `TEST_FAILED` (test_failed still returns the result in data).

## Monitoring results

Check result object:
```json
{
  "id": "...", "api_id": "...", "timestamp": "...", "status_code": 200,
  "response_time_ms": 142, "success": true, "error": null,
  "timed_out": false, "response_size_bytes": 512
}
```
- Routes:
  - `GET /api/monitors/{id}/checks?since=&until=&page=&page_size=` → paginated newest-first
  - `GET /api/monitors/{id}/metrics?period=24h|7d|30d` →
    ```json
    { "success": true, "data": {
      "uptime_percent": 99.95, "avg_latency_ms": 120.5, "min_latency_ms": 45,
      "max_latency_ms": 900, "p50_latency_ms": 110, "p95_latency_ms": 300,
      "p99_latency_ms": 500, "total_checks": 100, "successful_checks": 99,
      "failed_checks": 1, "error_rate_percent": 1.0,
      "status_code_distribution": {"2xx": 99, "3xx": 0, "4xx": 0, "5xx": 1, "timeout": 0, "connection_error": 0},
      "response_time_series": [{"timestamp": "...", "avg_ms": 120}], "uptime_series": [{"timestamp": "...", "uptime": 100.0}]
    }}
    ```
  - `GET /api/monitors/{id}/uptime?period=24h|7d|30d` → `{ success, data: { uptime_percent, total_checks, successful_checks } }`
- Retention: results older than `RESULTS_RETENTION_DAYS` (default 30) are pruned by scheduler.

## Incidents

Incident object:
```json
{
  "id": "...", "api_id": "...", "user_id": "...", "title": "Payments API is down",
  "description": "Consecutive failures detected...", "status": "open",
  "severity": "high", "started_at": "...", "detected_at": "...", "resolved_at": null,
  "duration_seconds": null, "root_cause": "", "resolution_notes": "",
  "created_by": "system", "updated_at": "..."
}
```
- `status` ∈ `open | investigating | identified | monitoring | resolved` (lowercase wire values)
- `severity` ∈ `low | medium | high | critical`
- Auto-create: after `failure_threshold` (default 3) consecutive failures, severity `high`; escalate to `critical` if downtime exceeds 15 minutes.
- Auto-resolve: after `recovery_threshold` (default 2) consecutive successes.
- Dedup: exactly ONE open incident per api_id; further failures append to `incident_events`, recovery resolves it.
- Incident event: `{ id, incident_id, timestamp, event_type, message }` — event_type ∈ `detected | created | updated | resolved | note | auto_resolved | escalated`.
- Routes:
  - `GET /api/incidents?status=&severity=&api_id=&from=&to=&search=&page=&page_size=` → paginated + `summary: { total, open, resolved, critical, avg_resolution_seconds }`
  - `POST /api/incidents` — body `{ api_id, title, description?, severity? }` (manual create, status=open, created_by=user)
  - `GET /api/incidents/{id}` → `{ success, data: { incident, api, events } }`
  - `PUT /api/incidents/{id}` — body `{ status?, severity?, root_cause?, resolution_notes? }` (setting status=resolved stamps resolved_at)
  - `DELETE /api/incidents/{id}` → 200
  - `POST /api/incidents/{id}/resolve` — body `{ resolution_notes? }`
- Error codes: `INCIDENT_NOT_FOUND`, `API_NOT_FOUND`, `FORBIDDEN`, `VALIDATION_ERROR`.

## Dashboard

- `GET /api/dashboard/summary` → `{ success, data: { total_apis, healthy_apis, degraded_apis, down_apis, paused_apis, avg_response_time_ms, overall_uptime_24h, open_incidents, recent_incidents: [...5], recent_activity: [...8], health_overview: { healthy, degraded, down, paused } } }`
- `GET /api/dashboard/uptime?period=24h|7d|30d` → `{ success, data: { points: [{ timestamp, uptime }] } }`
- `GET /api/dashboard/latency?period=24h|7d|30d` → `{ success, data: { points: [{ timestamp, avg_ms }] } }`
- `GET /api/dashboard/incidents?period=24h|7d|30d` → `{ success, data: { points: [{ timestamp, created, resolved }] } }`

## Activity logs

- `GET /api/activity?resource_type=&action=&page=&page_size=` → paginated
- Log entry: `{ id, user_id, action, resource_type, resource_id, resource_name, timestamp, ip, user_agent }`
- Actions recorded: `user.registered, user.logged_in, api.created, api.updated, api.deleted, api.paused, api.resumed, api.tested, incident.created, incident.updated, incident.resolved, incident.auto_created, incident.auto_resolved, settings.updated, webhook.created, webhook.deleted`

## Settings

- `GET /api/settings` → `{ success, data: { default_timeout, default_interval, failure_threshold, recovery_threshold, degraded_latency_ms, results_retention_days, notifications: { email_enabled, webhook_enabled }, profile: { name, email } } }`
- `PUT /api/settings` — body any subset; `notifications.*` and `profile.name` persisted; `profile.email` read-only.
- User doc also holds `notification_prefs`; webhooks are separate collection.

## Webhooks

- `GET /api/webhooks` → list `{ id, name, url, events: [...], active, created_at }`
- `POST /api/webhooks` — body `{ name, url, events, active? }`
- `DELETE /api/webhooks/{id}`
- events ∈ `incident.created | incident.resolved | api.down | api.recovered`
- Dispatch payload: `{ "event": "incident.created", "api": "Payments API", "api_id": "...", "severity": "high", "status": "open", "timestamp": "...", "incident_id": "..." }`
- Errors: `WEBHOOK_NOT_FOUND`, `VALIDATION_ERROR`.

## Demo endpoints (unprotected)

- `GET /demo/health` → `200 { "status": "healthy" }`
- `GET /demo/slow` → waits ~3s, returns `200 { "status": "ok", "delay_ms": 3000 }`
- `GET /demo/error` → `500 { "status": "error" }`
- `GET /demo/random` → randomly 200 or 500
- `POST /demo/echo` → echoes `{ received: <json body>, method, headers_redacted }`
- Also `GET /health` → `{ "status": "healthy" }`, `GET /health/db` → `{ "status": "healthy", "db": "connected" }`

## SSRF protection (backend)

- Block requests to private/reserved/loopback ranges and cloud metadata IPs (169.254.169.254, 100.100.100.200, fd00::/8) by resolving the hostname and checking `ipaddress`.
- Allow loopback ONLY when env `MONITOR_ALLOW_LOOPBACK=true` (default true for demo; document switching off in production).
- Block non-http(s) schemes and ports outside 1–65535.

## Frontend page → API map

- `/login` → login/register; `/dashboard` → dashboard/*; `/monitors` list → GET monitors; `/monitors/new`, `/monitors/:id`, `/monitors/:id/edit` → monitor CRUD + test/pause/resume + checks + metrics; `/incidents`, `/incidents/:id` → incidents; `/activity` → activity; `/settings` → settings + webhooks.
- Auth state: localStorage `access_token`; Axios interceptor attaches Bearer; 401 → redirect to `/login`.

## Pagination params

- `page` (1-based, default 1), `page_size` (default 20, max 100).
