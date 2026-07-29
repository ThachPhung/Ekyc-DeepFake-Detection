FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app/ai_modules

COPY ai_modules/requirements.txt ./

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        ffmpeg \
        libglib2.0-0 \
        libgl1 \
        libgomp1 \
        libsm6 \
        libxext6 \
        libxrender1 \
    && pip install --upgrade pip \
    && pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y --auto-remove build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY ai_modules/ ./

RUN mkdir -p /app/models /app/data/private /app/data/record /app/uploads

ENV EKYC_MODELS_DIR=/app/models
ENV EKYC_PRIVATE_STORAGE_DIR=/app/data/private
ENV EKYC_MINIFASNET_ONNX_PATH=/app/models/minifasnet.onnx
ENV EKYC_DEEPFAKE_ONNX_PATH=/app/models/deepfake_detector.onnx
ENV EKYC_DEEPFAKE_PREPROCESS=hf_vit
ENV EKYC_OCR_ENGINE=rapidocr_ppocrv6
ENV EKYC_RAPIDOCR_REC_MODEL=vi
ENV EKYC_PREFER_ONNX=true
ENV EKYC_REQUIRE_ONNX_MODELS=true
ENV EKYC_ALLOW_HEURISTIC_FALLBACK=false

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8001"]
