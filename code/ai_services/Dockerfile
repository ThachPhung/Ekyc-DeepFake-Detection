FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        libglib2.0-0 \
        libgl1 \
        libgomp1 \
        libsm6 \
        libxext6 \
        libxrender1 \
    && rm -rf /var/lib/apt/lists/*

COPY ai_modules/requirements.txt ./ai_modules/
RUN pip install --upgrade pip \
    && pip install -r ai_modules/requirements.txt

COPY ai_modules/ ./ai_modules/
COPY ai_services/ ./ai_services/

RUN mkdir -p /app/models /app/data/private

ENV EKYC_MODELS_DIR=/app/models
ENV EKYC_PRIVATE_STORAGE_DIR=/app/data/private
ENV PYTHONPATH=/app/ai_modules:/app/ai_services

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

CMD ["uvicorn", "api.main:app", "--app-dir", "/app/ai_modules", "--host", "0.0.0.0", "--port", "8001"]
