FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY deepfake_lipsync/requirements.txt ./requirements.txt
COPY deepfake_lipsync/scripts/download_weights.py ./scripts/download_weights.py

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir huggingface_hub \
    && python scripts/download_weights.py \
    && pip install --no-cache-dir -r requirements.txt

COPY deepfake_lipsync/app ./app

ENV DEVICE=cpu
ENV WEIGHTS_DIR=/app/weights
ENV S3FD_WEIGHTS=/app/weights/sfd_face.pth
ENV SYNCNET_WEIGHTS=/app/weights/syncnet_v2.model
ENV HF_WEIGHTS_REPO=lithiumice/syncnet
ENV SYNCNET_MIN_TRACK=30

EXPOSE 8002

HEALTHCHECK --interval=30s --timeout=15s --start-period=120s --retries=3 \
    CMD curl -f http://localhost:8002/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
