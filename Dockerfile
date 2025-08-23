# Simple dev Dockerfile used by both api and worker
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
# Install curl and ffmpeg for audio normalization/transcription
RUN apt-get update && apt-get install -y --no-install-recommends curl ffmpeg \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
# Copy full repo (backend and any static/assets if present)
COPY . .

# If you copied a Flutter Web build to backend/static, it will be served by FastAPI
# (This is optional; the app will still run without it.)

EXPOSE 8000
# Simple healthcheck: /health
HEALTHCHECK --interval=30s --timeout=5s --retries=5 CMD curl -fsS http://127.0.0.1:8000/health || exit 1
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
