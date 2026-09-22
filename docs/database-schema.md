# Database Schema

MongoDB database (default name `api_monitoring`). All `_id`s are ObjectIds, serialized to the API as 24-char hex strings in the `id` field. All timestamps are ISO-8601 UTC strings on the wire; stored as BSON datetimes.

## Collections

### `users`

| Field | Type | Description |
|---|---|---|
| `_id` | ObjectId | |
| `name` | string | Display name |
| `email` | string, **unique** | Login email |
| `password_hash` | string | bcrypt hash — never returned by the API |
| `notification_prefs` | object | e.g. `{ email_enabled, webhook_enabled }` (surfaced via settings) |
| `created_at` / `updated_at` | datetime | |

Indexes: unique on `email`.

### `apis` (monitors)

| Field | Type | Description |
|---|---|---|
| `_id` | ObjectId | |
| `user_id` | ObjectId → `users` | Owner; all queries scoped by this |
| `name` | string | e.g. "Payments API" |
| `url` | string | Target URL (SSRF-validated) |
| `method` | string | `GET\|POST\|PUT\|PATCH\|DELETE\|HEAD` |
| `description` | string | |
| `interval` | int | Seconds; one of `60, 300, 600, 900, 1800, 3600` |
| `timeout` | int | Seconds, 1–120 |
| `expected_status` | int | Default 200 |
| `headers` | object | Custom request headers |
| `body` | object/string/null | Request body (POST/PUT/PATCH only) |
| `active` | bool | `false` = paused |
| `status` | string | `healthy\|degraded\|down\|paused` (computed by backend) |
| `consecutive_failures` / `consecutive_successes` | int | Rolling counters driving incidents |
| `last_checked_at` | datetime/null | |
| `uptime_24h` | float | Cached 24h uptime % |
| `created_at` / `updated_at` | datetime | |

Indexes: `user_id`, `(user_id, status)`, `(active, last_checked_at)` (scheduler due-query), text or compound on `name` for `search=`.

### `checks`

One document per executed check (scheduler + manual `/test`).

| Field | Type | Description |
|---|---|---|
| `_id` | ObjectId | |
| `api_id` | ObjectId → `apis` | |
| `timestamp` | datetime | When the check ran |
| `status_code` | int/null | HTTP status; null on connection error/timeout |
| `response_time_ms` | float | Measured latency |
| `success` | bool | Status matched `expected_status` within `timeout` |
| `error` | string/null | e.g. `"timeout"`, `"connection_error"`, `"ssrf_blocked"` |
| `timed_out` | bool | |
| `response_size_bytes` | int | |

Indexes: `(api_id, timestamp desc)` (history + metrics queries), `timestamp` (TTL-style pruning by `RESULTS_RETENTION_DAYS`).

### `incidents`

| Field | Type | Description |
|---|---|---|
| `_id` | ObjectId | |
| `api_id` | ObjectId → `apis` | |
| `user_id` | ObjectId → `users` | |
| `title` / `description` | string | |
| `status` | string | `open\|investigating\|identified\|monitoring\|resolved` |
| `severity` | string | `low\|medium\|high\|critical` |
| `started_at` / `detected_at` | datetime | |
| `resolved_at` | datetime/null | Stamped on resolve |
| `duration_seconds` | int/null | `resolved_at - started_at` |
| `root_cause` / `resolution_notes` | string | |
| `created_by` | string | `"system"` (auto) or `"user"` (manual) |
| `created_at` / `updated_at` | datetime | |

Indexes: `user_id`, `api_id`, `(api_id, status)` (dedup: find the open incident), `(user_id, status)`, `created_at` (range filters `from`/`to`).

### `incident_events`

Timeline entries for incidents.

| Field | Type | Description |
|---|---|---|
| `_id` | ObjectId | |
| `incident_id` | ObjectId → `incidents` | |
| `timestamp` | datetime | |
| `event_type` | string | `detected\|created\|updated\|resolved\|note\|auto_resolved\|escalated` |
| `message` | string | |

Indexes: `(incident_id, timestamp)`.

### `webhooks`

| Field | Type | Description |
|---|---|---|
| `_id` | ObjectId | |
| `user_id` | ObjectId → `users` | |
| `name` | string | |
| `url` | string | SSRF-validated delivery target |
| `events` | string[] | Subset of `incident.created\|incident.resolved\|api.down\|api.recovered` |
| `active` | bool | |
| `created_at` | datetime | |

Indexes: `user_id`.

### `activity_logs`

Append-only audit log.

| Field | Type | Description |
|---|---|---|
| `_id` | ObjectId | |
| `user_id` | ObjectId → `users` | |
| `action` | string | e.g. `api.created`, `incident.auto_resolved` (full list in [api-documentation.md](api-documentation.md)) |
| `resource_type` | string | e.g. `api`, `incident`, `webhook`, `user`, `settings` |
| `resource_id` | string/null | Hex id of the affected resource |
| `resource_name` | string/null | Human-readable name at log time |
| `timestamp` | datetime | |
| `ip` / `user_agent` | string/null | From the originating request |

Indexes: `(user_id, timestamp desc)`, `(user_id, action)`, `(user_id, resource_type)`.

### `settings`

One document per user (upsert on first access).

| Field | Type | Description |
|---|---|---|
| `_id` | ObjectId | |
| `user_id` | ObjectId → `users`, **unique** | |
| `default_timeout` | int | Default 10 |
| `default_interval` | int | Default 300 |
| `failure_threshold` | int | Default 3 |
| `recovery_threshold` | int | Default 2 |
| `degraded_latency_ms` | int | Default 1000 |
| `results_retention_days` | int | Default 30 |
| `notifications` | object | `{ email_enabled, webhook_enabled }` |
| `profile` | object | `{ name, email }` — email is read-only |
| `updated_at` | datetime | |

Indexes: unique on `user_id`.

## Relationships

```
users 1───* apis 1───* checks
  │            │
  │            └──1───* incidents 1───* incident_events
  │                        (≤1 open per api_id)
  ├───* webhooks
  ├───* activity_logs
  └───1 settings
```

All cross-collection reads are scoped to the authenticated user's `user_id`. Deleting a monitor should cascade-delete (or orphan-mark) its `checks`, `incidents`, and `incident_events`.
