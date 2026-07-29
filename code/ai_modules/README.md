# eKYC Document AI Modules

Module AI xử lý OCR giấy tờ, kiểm tra chất lượng ảnh, trích khuôn mặt giấy tờ, matching video/selfie, speech verification và trả JSON cho backend.

**Bàn giao / runbook đầy đủ:** [docs/HANDOVER.md](./docs/HANDOVER.md)
**Env mẫu:** [`.env.example`](./.env.example) hoặc [`.env.example` repo root](../../.env.example)

Phạm vi hiện tại:

- **YOLO11 layout CCCD** (`cccd_layout_yolov11.pt`) + RapidOCR PP-OCRv6 từng field — production default.
- **Document preprocess** — warp, CLAHE, auto-orient.
- **InsightFace ArcFace** — 5-point align, cosine similarity (buffalo_l / glintr100).
- **MiniFASNet V2 SE** — passive liveness (FP32 hoặc INT8 ONNX).
- **Deepfake ViT ONNX** — phát hiện deepfake theo frame.
- **SyncNet lip-sync** — microservice `:8002`, tín hiệu risk `lipsync` (HTTP client).
- **Streaming speech** — VAD + hybrid ASR (ViStreamASR / faster-whisper + PhoWhisper).
- Evidence-based weighted risk scoring (6 tín hiệu: deepfake, lipsync, identity, replay, camera, voice).

**Bàn giao:** [docs/HANDOVER.md](./docs/HANDOVER.md) · [../BAN_GIAO_EKYC.md](../BAN_GIAO_EKYC.md)

## Cài đặt nhanh

```bash
cd code/ai_modules
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
brew install ffmpeg   # macOS — cần cho speech verification

# Tải ONNX models (MiniFASNet + Deepfake)
python3 -m scripts.download_models --models-dir ../models

# Kiểm tra readiness
python3 -m scripts.check_models
```

## Biến môi trường quan trọng

| Biến | Mặc định | Mô tả |
|------|----------|-------|
| `EKYC_OCR_ENGINE` | `rapidocr_ppocrv6` | OCR engine |
| `EKYC_RAPIDOCR_REC_MODEL` | `vi` | Rec model tiếng Việt (PP-OCRv6) |
| `EKYC_MINIFASNET_ONNX_PATH` | `code/models/minifasnet.onnx` | Passive liveness |
| `EKYC_DEEPFAKE_ONNX_PATH` | `code/models/deepfake_detector.onnx` | Deepfake detector |
| `EKYC_LIPSYNC_SERVICE_URL` | (unset) | SyncNet microservice — local: `http://localhost:8002` |
| `EKYC_LIPSYNC_ENABLED` | `true` | Bật gọi lip-sync (skip nếu thiếu URL) |
| `EKYC_DEEPFAKE_PREPROCESS` | `hf_vit` | Preprocess cho deepfake ONNX |
| `EKYC_PREFER_ONNX` | `true` | Ưu tiên ONNX thay vì HF/heuristic |
| `EKYC_REQUIRE_ONNX_MODELS` | `true` | Health = unhealthy nếu thiếu model |
| `EKYC_ALLOW_HEURISTIC_FALLBACK` | `false` | Cho phép heuristic khi thiếu ONNX |
| `EKYC_USE_YOLO_LAYOUT_PIPELINE` | `true` | YOLO layout CCCD production |
| `EKYC_LLM_EXTRACT` | `true` | Bật LLM tinh chỉnh trích xuất field |
| `EKYC_LLM_MODE` | `always` | `always` hoặc `fallback` (chỉ khi rule yếu) |
| `EKYC_LLM_PROVIDER` | `openai` | Provider: `openai`, `deepseek`, `gemini`, `anthropic` |
| `EKYC_LLM_MODEL` | (theo provider) | Model override — bỏ trống để dùng default |
| API key | (theo provider) | Xem bảng provider bên dưới |

### LLM trích xuất (production)

Pipeline hybrid: **OCR → rule parser → LLM JSON merge**.

Chọn **một** provider qua `EKYC_LLM_PROVIDER`, rồi đặt **API key của provider đó**:

| Provider | `EKYC_LLM_PROVIDER` | API key env | Model mặc định |
|----------|---------------------|-------------|----------------|
| OpenAI | `openai` | `OPENAI_API_KEY` | `gpt-5.4-mini` |
| DeepSeek | `deepseek` | `DEEPSEEK_API_KEY` | `deepseek-chat` |
| Google Gemini | `gemini` | `GEMINI_API_KEY` hoặc `GOOGLE_API_KEY` | `gemini-2.0-flash` |
| Anthropic | `anthropic` | `ANTHROPIC_API_KEY` | `claude-sonnet-4-20250514` |

Ví dụ **OpenAI**:

```bash
export EKYC_LLM_EXTRACT=true
export EKYC_LLM_MODE=always
export EKYC_LLM_PROVIDER=openai
export OPENAI_API_KEY=sk-...
```

Ví dụ **DeepSeek**:

```bash
export EKYC_LLM_PROVIDER=deepseek
export DEEPSEEK_API_KEY=sk-...
# export EKYC_LLM_MODEL=deepseek-chat   # optional
```

Ví dụ **Gemini**:

```bash
export EKYC_LLM_PROVIDER=gemini
export GEMINI_API_KEY=AIza...
# export EKYC_LLM_MODEL=gemini-2.0-flash
```

Ví dụ **Anthropic**:

```bash
export EKYC_LLM_PROVIDER=anthropic
export ANTHROPIC_API_KEY=sk-ant-...
```

Override endpoint (Ollama, proxy…):

```bash
export EKYC_LLM_PROVIDER=openai
export EKYC_LLM_BASE_URL=http://localhost:11434/v1
export OPENAI_API_KEY=ollama
export EKYC_LLM_MODEL=llama3.1
```

- `always`: luôn gọi LLM sau parser (~$0.001/ảnh với gpt-5.4-mini / gemini flash).
- `fallback`: chỉ gọi khi rule yếu.
- Tắt: `EKYC_LLM_EXTRACT=false`.

Kiểm tra: `GET /health` → `llm_extract.providers` + `llm_extract.ready`.


```bash
export EKYC_REQUIRE_ONNX_MODELS=true
export EKYC_ALLOW_HEURISTIC_FALLBACK=false
```

## Cấu trúc

```
ai_modules/
├── ekyc_document/
│   ├── pipeline.py, parser.py, llm_extract.py, yolo_layout_pipeline.py
│   ├── quality_check.py, face_extraction.py, biometric.py
│   ├── face_matching/    # ArcFace, 5pt alignment, embedder
│   ├── liveness/         # MiniFASNet crop, frame selection
│   ├── ocr_stack/        # DBNet, VietOCR, layout (optional stack)
│   └── speech/           # VAD, streaming ASR, verifier
├── api/main.py           # FastAPI :8001
├── scripts/              # CLI: extract, video liveness, check_models
├── tests/                # pytest (commit trong git)
└── docs/
    ├── HANDOVER.md
    ├── BACKEND_API.md
    └── UPGRADE_TEST_GUIDE.md
```

## Cài Đặt

```bash
cd code/ai_modules
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Tạo API key nội bộ nếu backend cần đọc record riêng
python -m ekyc_document.setup_keys
```

Lần đầu chạy, RapidOCR và InsightFace sẽ tự tải model vào cache/`code/models/`.

## Chạy Service

```bash
cd code/ai_modules
uvicorn api.main:app --host 0.0.0.0 --port 8001 --reload
```

Kiểm tra service:

```bash
curl http://127.0.0.1:8001/health
```

Swagger UI: `http://localhost:8001/docs`

Diagnostics nội bộ, cần `EKYC_INTERNAL_API_KEY`:

```bash
curl -H "X-Internal-API-Key: dev-key" http://127.0.0.1:8001/api/v1/diagnostics
```

## Chạy Bằng Docker

Cách này phù hợp khi đưa sang máy khác: không cần tạo virtualenv thủ công, chỉ cần Docker và các thư mục dữ liệu/model.

Cách nhanh nhất, chạy một container AI service bằng Docker Compose:

```bash
cd code
mkdir -p models data/private data/record
docker compose -f compose.ai.yml up --build
```

Service sẽ chạy tại:

```text
http://localhost:8001
```

Kiểm tra:

```bash
curl http://127.0.0.1:8001/health
```

Nếu muốn build và chạy bằng `docker run` thủ công, build image từ thư mục `code`:

```bash
cd code
docker build -f ai_modules/Dockerfile -t ekyc-ai .
```

Chạy container:

```bash
mkdir -p models data/private data/record

docker run --rm -p 8001:8001 \
  -v "$PWD/models:/app/models" \
  -v "$PWD/data/private:/app/data/private" \
  -v "$PWD/data/record:/app/data/record" \
  -e EKYC_INTERNAL_API_KEY=dev-key \
  -e EKYC_MINIFASNET_ONNX_PATH=/app/models/minifasnet.onnx \
  ekyc-ai
```

Kiểm tra container:

Nếu có model anti-spoofing, copy vào:

```text
code/models/minifasnet.onnx
```

Nếu chưa có `minifasnet.onnx`, service vẫn chạy và video liveness sẽ dùng `heuristic_fallback`; response sẽ có warning `Chưa cấu hình EKYC_MINIFASNET_ONNX_PATH`.

Kết quả JSON trong Docker được lưu ra máy host tại:

```text
code/data/record/
```

## Chạy Test Bằng cURL

Các ví dụ dưới đây giả sử terminal đang đứng ở thư mục `code`.

Test ảnh mặt trước và mặt sau, tự lưu JSON và chỉ in `done`:

```bash
curl -s -o /dev/null -X POST "http://localhost:8001/api/v1/document/analyze" \
  -F "front_file=@data/Doan/front.jpg" \
  -F "back_file=@data/Doan/back.jpg" \
  -F "document_type=CCCD" \
  -F "response_format=full" && echo "done"
```

Test riêng video với ảnh giấy tờ làm ảnh đối chiếu:

```bash
curl -s -o /dev/null -X POST "http://localhost:8001/api/v1/video/upload" \
  -F "doc_face=@data/Doan/front.jpg" \
  -F "file=@data/Doan/live.mp4" && echo "done"
```

Test full eKYC gồm ảnh trước, ảnh sau và video:

```bash
curl -s -o /dev/null -X POST "http://localhost:8001/api/v1/ekyc/verify" \
  -F "front_file=@data/Doan/front.jpg" \
  -F "back_file=@data/Doan/back.jpg" \
  -F "video_file=@data/Doan/live.mp4" \
  -F "document_type=CCCD" && echo "done"
```

Nếu terminal đang đứng ở repo root `C2-App-036`, đổi path thành `code/data/...`.
Nếu terminal đang đứng ở `code/ai_modules`, đổi path thành `../data/...`.

Xem hướng dẫn chi tiết: [docs/HANDOVER.md](./docs/HANDOVER.md) và [docs/UPGRADE_TEST_GUIDE.md](./docs/UPGRADE_TEST_GUIDE.md)

## File Kết Quả

Mỗi lần gọi các endpoint phân tích, service tự lưu JSON response vào:

```text
code/data/record/
```

Response cũng có field `result_file` trỏ tới file vừa lưu. Thư mục `code/data/record/*` và `results/` đã được gitignore.

PII riêng tư nếu bật record nội bộ sẽ nằm ở:

```text
code/data/private/records/
```

## CLI Nội Bộ

```bash
cd code/ai_modules
python -m ekyc_document.pipeline path/to/image.jpg --type CCCD --full
```

## Unit test

Xem [docs/UPGRADE_TEST_GUIDE.md](./docs/UPGRADE_TEST_GUIDE.md).

```bash
cd code/ai_modules
source .venv/bin/activate
pytest tests/test_face_matching.py tests/test_face_alignment.py \
       tests/test_lipsync_client.py \
       tests/test_liveness_stack.py tests/test_onnx_stack.py \
       tests/test_speech.py tests/test_speech_streaming.py \
       tests/test_video_risk.py -v
```

## Risk Scoring Và Threshold

Risk score video dùng weighted formula:

```text
risk_score = deepfake×0.25 + lipsync×0.15 + identity×0.22 + replay×0.18 + camera×0.10 + voice×0.10
```

Weights được normalize tự động (bỏ tín hiệu skip, ví dụ voice khi không có speech challenge):

```bash
EKYC_VIDEO_RISK_WEIGHTS="deepfake:0.25,lipsync:0.15,identity:0.22,replay:0.18,camera:0.10,voice:0.10"
```

Các env latency/accuracy chính:

```bash
EKYC_ADAPTIVE_VIDEO_SAMPLING=true
EKYC_TARGET_VIDEO_SAMPLES=36
EKYC_MAX_VIDEO_FRAMES=90
EKYC_VIDEO_FRAME_STRIDE=5
EKYC_VIDEO_RISK_REVIEW_THRESHOLD=0.45
EKYC_VIDEO_RISK_BLOCK_THRESHOLD=0.72
```

Chi tiết contract backend: [docs/BACKEND_API.md](./docs/BACKEND_API.md)
