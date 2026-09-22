# Backend image (FastAPI + Uvicorn).
# Copy to backend/Dockerfile to build standalone:
#   cp docs/deployment/backend.Dockerfile backend/Dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Render and most PaaS platforms inject $PORT; default to 8000 for docker runs.
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
