# Deployment Guide

Three pieces: **MongoDB Atlas** (database) → **Render** (backend) → **Vercel** (frontend). A Docker Compose option for local runs is at the end.

## 1. MongoDB Atlas (database)

1. Create a free cluster at [cloud.mongodb.com](https://cloud.mongodb.com) (M0 is fine to start).
2. **Database Access** → *Add New Database User* → username/password, role **Read and write to any database**.
3. **Network Access** → *Add IP Address* → `0.0.0.0/0` (Render uses dynamic IPs; restrict to Render's IP ranges later if you want).
4. **Database** → *Connect* → *Drivers* → copy the connection string. It looks like:
   ```
   mongodb+srv://<user>:<password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
   ```
   URL-encode special characters in the password (`@` → `%40`, etc.).
5. Keep this string handy — it's `MONGODB_URI` for Render.

## 2. Render (backend)

### Option A — Blueprint (recommended)

1. Push the repo to GitHub.
2. In Render: **New → Blueprint**, point it at the repo. Render reads [`render.yaml`](../render.yaml).
3. After the first deploy, go to the service → **Environment** and set the `sync: false` values:
   - `MONGODB_URI` — your Atlas string from step 1 (stored as a secret)
   - `FRONTEND_URL` — your Vercel URL, e.g. `https://api-monitoring.vercel.app`
   - (Optional) `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM` for email alerts
4. The blueprint already sets production-safe defaults: `MONITOR_ALLOW_LOOPBACK=false`, `JWT_SECRET` auto-generated, `healthCheckPath: /health`.

What the blueprint does:

| Setting | Value |
|---|---|
| Type | Web service, Python runtime |
| Root directory | `backend` |
| Build | `pip install -r requirements.txt` |
| Start | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` (note: Render injects `$PORT` — never hardcode 8000) |
| Health check | `GET /health` |

### Option B — Manual web service

Same values as above, entered by hand: root directory `backend`, build/start commands as above, health check path `/health`.

### Verify

- `https://<your-service>.onrender.com/health` → `{ "status": "healthy" }`
- `https://<your-service>.onrender.com/health/db` → `{ "status": "healthy", "db": "connected" }`
- `https://<your-service>.onrender.com/docs` → Swagger UI

Note: Render free-tier services sleep when idle — the first request (and the scheduler tick) can be slow to wake up. The in-process scheduler resumes automatically on wake.

## 3. Vercel (frontend)

1. In Vercel: **Add New → Project**, import the repo.
2. Set **Root Directory** to `frontend` (Framework preset: Vite is auto-detected). The [`vercel.json`](../frontend/vercel.json) in that directory handles SPA rewrites.
3. **Environment Variables** → add:
   - `VITE_API_URL` = `https://<your-service>.onrender.com` (your Render backend URL — **no trailing slash**)
   
   ⚠️ Vite bakes `VITE_*` vars into the bundle **at build time** — set the variable *before* deploying, and redeploy if you change it.
4. Deploy. The `rewrites` rule in `vercel.json` sends all routes to `index.html` so `/monitors/abc` etc. work on refresh and deep links.

## 4. Wire the two together (checklist)

- [ ] Backend `FRONTEND_URL` == Vercel frontend origin (CORS).
- [ ] Frontend `VITE_API_URL` == Render backend URL.
- [ ] Atlas network access allows Render (`0.0.0.0/0` or Render IP ranges).
- [ ] `MONITOR_ALLOW_LOOPBACK=false` in production (it's `true` only for local demo).
- [ ] `JWT_SECRET` is a long random value (Render's `generateValue` handles this in the blueprint).
- [ ] `/health` and `/health/db` return healthy on Render.
- [ ] Register a user in the deployed frontend and create a monitor — check `/health/db` and the dashboard to confirm end-to-end.

## 5. Local Docker run (optional)

For a full local stack without installing Python/Node/Mongo:

```bash
cp docs/deployment/backend.Dockerfile  backend/Dockerfile
cp docs/deployment/frontend.Dockerfile frontend/Dockerfile
cp .env.example .env   # edit values as needed
docker compose -f docs/deployment/docker-compose.yml up --build
```

- Frontend: http://localhost (nginx serving the production build)
- Backend: http://localhost:8000 (`/docs`, `/health`)
- MongoDB: localhost:27017 (data in the `mongo-data` volume)

## Production hardening notes

- **Demo account**: the seed script's `demo@example.com` / `DemoPass123!` account is for **demo/development only**. Never run `scripts/seed.py` against production, or delete the demo user afterwards.
- **Secrets**: `MONGODB_URI`, `JWT_SECRET`, `SMTP_PASSWORD` belong in the platform's secret store (Render env vars marked secret, Vercel encrypted env vars) — never in git.
- **CORS**: keep `FRONTEND_URL` restricted to exactly your frontend origin.
- **SSRF**: production must have `MONITOR_ALLOW_LOOPBACK=false` so monitors can't probe the host's loopback/metadata endpoints.
- **Backups**: enable Atlas continuous backups (or scheduled snapshots) before going live.
- **Retention**: tune `RESULTS_RETENTION_DAYS` to your storage budget; checks is the highest-volume collection.
- **Scaling**: the scheduler is in-process — run exactly one backend instance, or gate the scheduler behind leader election before scaling out.
