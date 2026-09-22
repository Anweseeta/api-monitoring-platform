# Deployment Guide

Step-by-step: **MongoDB Atlas → Render → Vercel**. Nothing here deploys automatically — each step is a manual action in the provider's dashboard.

## 0. Prerequisites

- A GitHub account; this repo pushed to a GitHub repository
- A [MongoDB Atlas](https://cloud.mongodb.com) account (free M0 tier is enough to start)
- A [Render](https://render.com) account
- A [Vercel](https://vercel.com) account
- `openssl` (for generating the JWT secret)

## 1. MongoDB Atlas (database)

1. Create a free cluster (M0) at [cloud.mongodb.com](https://cloud.mongodb.com).
2. **Database Access** → **Add New Database User** → username + password, built-in role **readWrite** on your database (e.g. `api_monitoring`). Save the password somewhere safe.
3. **Network Access** → **Add IP Address** → `0.0.0.0/0` (Atlas + Render IPs change; restrict later if you prefer).
4. **Database** → your cluster → **Connect** → **Drivers** → **Python** → copy the connection string. It looks like:
   `mongodb+srv://<user>:<password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority`
5. Replace `<user>` and `<password>` with the database user from step 2. Keep this string secret — it is the value of `MONGODB_URI`.

The backend creates all collections and indexes on first boot; nothing to provision manually.

## 2. Render (backend)

1. In Render: **New → Blueprint**, point it at your GitHub repo. Render reads [`render.yaml`](render.yaml).
2. The blueprint creates the `api-monitoring-backend` web service:
   - Build: `pip install -r requirements.txt` (in `backend/`)
   - Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - Health check: `GET /health`
3. Set the secret env vars in the Render dashboard (marked `sync: false` in the blueprint):
   - `MONGODB_URI` — the Atlas connection string from step 1
   - `JWT_SECRET` — the blueprint generates a random one (`generateValue: true`); keep it, or replace with your own from `openssl rand -hex 32`
   - `FRONTEND_URL` — your Vercel URL from step 3 (e.g. `https://your-app.vercel.app`); you can add this after the frontend is deployed, then redeploy the backend
4. Confirm `ENVIRONMENT=production` is set (the blueprint sets it). With it, the backend **refuses to boot** if `JWT_SECRET` is the default or shorter than 32 chars, and blocks loopback monitor targets (`MONITOR_ALLOW_LOOPBACK=false`).
5. Deploy. Verify `https://<your-service>.onrender.com/health` returns `{"status":"healthy"}`.

> Render free-tier services sleep when idle — the first request (and the scheduler tick) wakes it; the in-process scheduler resumes on wake.

## 3. Vercel (frontend)

1. In Vercel: **Add New → Project**, import the same GitHub repo.
2. Set **Root Directory** to `frontend` (Framework preset: Vite auto-detected). [`frontend/vercel.json`](frontend/vercel.json) handles the SPA fallback rewrite.
3. **Environment Variables** → add:
   - `VITE_API_URL` = `https://<your-service>.onrender.com` — your Render backend URL, **no trailing slash**
   
   ⚠️ Vite bakes `VITE_*` values into the bundle **at build time** — set it *before* deploying; redeploy if you change it.
4. Deploy. Open the site, register an account, and create a monitor.

## 4. Wire-up checklist

- [ ] Atlas: database user exists, `0.0.0.0/0` (or Render IPs) allowlisted, `MONGODB_URI` copied
- [ ] Render: `MONGODB_URI` (secret), `JWT_SECRET` (≥32 chars), `FRONTEND_URL` = Vercel URL, `ENVIRONMENT=production`
- [ ] Render `/health` and `/health/db` both return healthy
- [ ] Vercel: `VITE_API_URL` = Render backend URL, no trailing slash, set before build
- [ ] Frontend loads, login works (proves CORS + API URL are right), a monitor check runs

## 5. Post-deploy notes

- **Do not run `scripts/seed.py` against production** — the demo account (`demo@example.com` / `DemoPass123!`) is for local demos only.
- **Email alerts** are optional: set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM` in Render to enable them.
- **Rotate secrets**: regenerate `JWT_SECRET` in the Render dashboard to invalidate all existing sessions/tokens.
- **Logs**: Render dashboard → your service → Logs. The API also writes an activity log visible in the app.
- **Backups**: Atlas M0 includes basic backups; upgrade the cluster tier for point-in-time restore.

## 6. Local development (recap)

```bash
cp .env.example .env          # edit values (MongoDB URI, JWT secret, ...)
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000   # http://localhost:8000/docs

cd frontend && npm install && npm run dev    # http://localhost:5173
```

Optional demo data: `cd backend && source .venv/bin/activate && python scripts/seed.py`
