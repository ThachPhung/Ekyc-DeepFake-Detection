# Bàn giao eKYC AI Module — Runbook đầy đủ

> **Mục tiêu:** Người clone repo làm **đúng y hệt** môi trường dev hiện tại — YOLO11 layout CCCD, OCR RapidOCR từng field, LLM merge, InsightFace ArcFace, MiniFASNet liveness, SyncNet lip-sync, streaming speech.

**Production default:** `EKYC_USE_YOLO_LAYOUT_PIPELINE=true` + `cccd_layout_yolov11.pt` (trong git). RapidOCR-only vẫn dùng được khi tắt YOLO.

**Đọc file này trước.** Tóm tắt nhanh: [../../BAN_GIAO_EKYC.md](../../BAN_GIAO_EKYC.md). Contract API: [BACKEND_API.md](./BACKEND_API.md). Test regression: [UPGRADE_TEST_GUIDE.md](./UPGRADE_TEST_GUIDE.md).

---

## Mục lục

1. [Cấu trúc repo](#1-cấu-trúc-repo)
2. [Clone & file cần có sau clone](#2-clone--file-cần-có-sau-clone)
3. [Cài đặt từng bước (local — giống dev)](#3-cài-đặt-từng-bước-local--giống-dev)
4. [Cấu hình `.env` — copy y nguyên mẫu](#4-cấu-hình-env--copy-y-nguyên-mẫu)
5. [Models ONNX & InsightFace](#5-models-onnx--insightface)
6. [Chạy AI service](#6-chạy-ai-service)
6b. [Chạy local thường (test UI — không Docker full)](#6b-chạy-local-thường-test-ui--không-docker-full)
7. [Trích xuất CCCD từ terminal (CLI)](#7-trích-xuất-cccd-từ-terminal-cli)
8. [Xác nhận LLM đang chạy](#8-xác-nhận-llm-đang-chạy)
9. [Pipeline xử lý ảnh CCCD](#9-pipeline-xử-lý-ảnh-cccd)
10. [Kết nối Backend](#10-kết-nối-backend)
10b. [Admin dashboard & LLM gợi ý quyết định](#10b-admin-dashboard--llm-gợi-ý-quyết-định)
11. [Chạy Docker](#11-chạy-docker)
12. [Test API bằng cURL](#12-test-api-bằng-curl)
13. [Output JSON — không đổi schema](#13-output-json--không-đổi-schema)
14. [Unit test](#14-unit-test)
15. [Git — commit cái gì](#15-git--commit-cái-gì)
16. [Checklist bàn giao](#16-checklist-bàn-giao)
17. [Xử lý sự cố](#17-xử-lý-sự-cố)

---

## 1. Cấu trúc repo

```text
C2-App-036/
├── .env.example              ← Mẫu env FULL (backend + AI) — copy → .env ở đây
├── .env                      ← KHÔNG commit (API key thật)
│
└── code/
    ├── models/               ← ONNX + YOLO trong git
    │   ├── minifasnet.onnx
    │   ├── deepfake_detector.onnx
    │   ├── cccd_layout_yolov11.pt
    │   ├── MODEL_MANIFEST.txt
    │   └── models/buffalo_l/ ← InsightFace (~325MB) — KHÔNG trong git, tự tải
    │
    ├── data/
    │   ├── Test/             ← Ảnh test CCCD (jpg/png gitignore — xem mục 2)
    │   ├── Doan/             ← Ảnh mẫu front/back/video
    │   ├── private/          ← PII nội bộ (gitignore)
    │   └── record/           ← JSON kết quả API (gitignore nội dung)
    │
    ├── compose.ai.yml        ← Docker AI + lipsync (:8001 + :8002)
    ├── compose.yml           ← Full stack (backend, frontend, AI, lipsync, worker)
    ├── deepfake_lipsync/     ← Microservice SyncNet lip-sync (:8002)
    │
    └── ai_modules/           ← **Module AI — làm việc ở đây**
        ├── .env.example      ← Pointer tới .env repo root
        ├── .venv/
        ├── api/main.py         ← FastAPI :8001
        ├── ekyc_document/
        │   ├── pipeline.py, parser.py, llm_extract.py
        │   ├── yolo_layout_pipeline.py, field_polish.py
        │   ├── face_matching/   ← ArcFace + 5pt align
        │   ├── liveness/        ← MiniFASNet crop + frame select
        │   ├── lipsync_client.py ← HTTP client → SyncNet :8002
        │   ├── ocr_stack/       ← DBNet, VietOCR, layout (optional)
        │   └── speech/          ← VAD, streaming ASR, verifier
        ├── scripts/
        │   ├── run_document_extract.sh
        │   ├── run_video_liveness.py
        │   ├── check_models.py, download_models.py
        │   └── quantize_minifasnet.py
        ├── tests/              ← pytest (commit trong git)
        └── docs/
            ├── HANDOVER.md
            ├── BACKEND_API.md
            └── UPGRADE_TEST_GUIDE.md
```

---

## 2. Clone & file cần có sau clone

```bash
git clone <repo-url> C2-App-036
cd C2-App-036
```

### Có sẵn trong git (không cần tải thêm)

| Path | Mô tả |
|------|--------|
| `code/models/minifasnet.onnx` | Passive liveness (~2MB) |
| `code/models/deepfake_detector.onnx` | Deepfake ViT Q4 (~55MB) |
| `.env.example` | Mẫu cấu hình |
| `code/ai_modules/` | Toàn bộ source AI |

### Không có trong git — tự sinh khi chạy

| Path | Cách có |
|------|---------|
| `code/models/models/buffalo_l/` | Lần đầu chạy face detect / InsightFace (~325MB, tải mạng) |
| `code/ai_modules/.venv/` | `python3 -m venv .venv` |
| `.env` | `cp .env.example .env` + điền key |
| `code/data/Test/*.png` | Ảnh test **bị gitignore** — lấy từ team lead hoặc tự chụp CCCD |

> **Lưu ý ảnh test:** `.gitignore` ignore `*.jpg`, `*.png`, `*.mp4`. Repo push lên **không kèm ảnh CCCD**. Team nhận bàn giao cần copy thư mục `code/data/Test/` và `code/data/Doan/` từ người bàn giao (Drive/USB) hoặc dùng ảnh riêng.

---

## 3. Cài đặt từng bước (local — giống dev)

Chạy **lần lượt**, không bỏ bước:

### Bước 1 — Env

```bash
cd C2-App-036
cp .env.example .env
```

Chỉ cần **một** file `.env` ở **repo root**. AI service tự đọc (cũng đọc `code/ai_modules/.env` nếu có, nhưng **khuyến nghị chỉ dùng root**).

### Bước 2 — Tạo API key nội bộ

```bash
cd code/ai_modules
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python -m ekyc_document.setup_keys
```

Copy dòng `EKYC_INTERNAL_API_KEY=...` vào `.env` ở repo root.

### Bước 3 — Điền LLM API key

Mở `.env` (repo root), điền **một** provider:

```bash
EKYC_LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...your-key...
EKYC_LLM_MODEL=gpt-4o-mini
```

(Gemini: `EKYC_LLM_PROVIDER=gemini` + `GEMINI_API_KEY=AIza...`)

### Bước 4 — Kiểm tra ONNX (đã có trong repo)

```bash
cd code/ai_modules
source .venv/bin/activate
python -m scripts.check_models
```

Kết quả mong đợi: `"ready": true`, không có `missing_models` (trừ khi chưa tải buffalo_l — OK cho OCR-only).

Nếu thiếu file `.onnx`:

```bash
python -m scripts.download_models --models-dir ../models
```

### Bước 5 — (Tuỳ chọn) ffmpeg cho speech

```bash
brew install ffmpeg    # macOS
```

---

## 4. Cấu hình `.env` — copy y nguyên mẫu

File đầy đủ: [`.env.example`](../../../.env.example) (repo root).

### Block bắt buộc cho AI (production giống dev hiện tại)

Dán vào `.env` và **chỉ sửa các dòng có `...`**:

```bash
# --- YOLO layout (production default) ---
EKYC_USE_YOLO_LAYOUT_PIPELINE=true
EKYC_YOLO_LAYOUT_MODEL=code/models/cccd_layout_yolov11.pt
EKYC_DOCUMENT_WARP=true

# --- Backend ↔ AI ---
EKYC_AI_SERVICE_URL=http://localhost:8001
EKYC_AI_REQUEST_TIMEOUT_SECONDS=120
EKYC_INTERNAL_API_KEY=...paste-from-setup_keys...
EKYC_CORS_ORIGINS=http://localhost:3060,http://localhost:8000

# --- ONNX (file trong repo) ---
EKYC_MODELS_DIR=code/models
EKYC_MINIFASNET_ONNX_PATH=code/models/minifasnet.onnx
EKYC_DEEPFAKE_ONNX_PATH=code/models/deepfake_detector.onnx
EKYC_DEEPFAKE_PREPROCESS=hf_vit
EKYC_INSIGHTFACE_MODEL=buffalo_l
EKYC_FACE_DETECTOR=insightface
EKYC_PREFER_ONNX=true
EKYC_REQUIRE_ONNX_MODELS=true
EKYC_ALLOW_HEURISTIC_FALLBACK=false

# --- OCR ---
EKYC_OCR_ENGINE=rapidocr_ppocrv6
EKYC_RAPIDOCR_REC_MODEL=vi
EKYC_RAPIDOCR_LANG=vi
EKYC_OCR_PREPROCESS=true

# --- Auto-orient ảnh dọc ---
EKYC_AUTO_ORIENT=true
EKYC_AUTO_ORIENT_PORTRAIT_RATIO=1.05
EKYC_AUTO_ORIENT_PROBE_MAX_SIDE=1600

# --- LLM ---
EKYC_LLM_EXTRACT=true
EKYC_LLM_MODE=always
EKYC_LLM_PROVIDER=openai
EKYC_LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=...your-key...
```

### Biến đọc từ `.env` — bảng tham chiếu nhanh

| Nhóm | Biến chính | Giá trị dev |
|------|------------|-------------|
| OCR | `EKYC_OCR_ENGINE` | `rapidocr_ppocrv6` |
| OCR | `EKYC_RAPIDOCR_REC_MODEL` | `vi` |
| Orient | `EKYC_AUTO_ORIENT` | `true` |
| LLM | `EKYC_LLM_EXTRACT` / `MODE` | `true` / `always` |
| LLM | `EKYC_LLM_PROVIDER` | `openai` |
| ONNX | `EKYC_REQUIRE_ONNX_MODELS` | `true` |
| ONNX | `EKYC_MINIFASNET_ONNX_PATH` | `code/models/minifasnet.onnx` |
| ONNX | `EKYC_DEEPFAKE_ONNX_PATH` | `code/models/deepfake_detector.onnx` |

Các biến còn lại (video risk, speech, face threshold…): xem `.env.example`, **giữ nguyên default** trừ khi tune production.

### File `.env.example` trong `ai_modules/`

Là **bản rút gọn** chỉ biến AI. **Ưu tiên dùng `.env.example` ở repo root** (có thêm backend, Redis, Postgres). Hai file **không giống hệt** — đừng nhầm.

---

## 5. Models ONNX & InsightFace

| File | Trong git? | Size | Dùng cho |
|------|------------|------|----------|
| `code/models/minifasnet.onnx` | **Có** | ~2 MB | Video liveness |
| `code/models/deepfake_detector.onnx` | **Có** | ~55 MB | Deepfake detection |
| `code/models/cccd_layout_yolov11.pt` | **Có** | ~6 MB | YOLO layout CCCD |
| `code/models/models/buffalo_l/` | **Không** | ~325 MB | Face detect trên CCCD |

Path trong `.env` **luôn relative repo root** (`code/models/...`), kể cả khi chạy lệnh trong `code/ai_modules/`.

Docker map: `./models` → `/app/models`, env container:

```text
EKYC_MINIFASNET_ONNX_PATH=/app/models/minifasnet.onnx
EKYC_DEEPFAKE_ONNX_PATH=/app/models/deepfake_detector.onnx
```

---

## 6. Chạy AI service

```bash
cd code/ai_modules
source .venv/bin/activate
uvicorn api.main:app --host 0.0.0.0 --port 8001 --reload
```

Giữ terminal này mở. Service: **http://localhost:8001**

### Health check (bắt buộc sau khi start)

```bash
curl -s http://127.0.0.1:8001/health | python3 -m json.tool
```

**Pass khi:**

```json
{
  "status": "ok",
  "ocr_engine": "rapidocr_ppocrv6",
  "llm_extract": {
    "enabled": true,
    "mode": "always",
    "provider": "openai",
    "ready": true
  }
}
```

- `status: "degraded"` — thiếu ONNX hoặc speech; OCR vẫn chạy được
- `llm_extract.ready: false` — thiếu/sai `OPENAI_API_KEY` (hoặc provider khác)

Swagger UI: http://localhost:8001/docs

> **Lip-sync:** Nếu chạy uvicorn local, cần `EKYC_LIPSYNC_SERVICE_URL=http://localhost:8002` trong `.env` **và** container lipsync đang chạy. Không có URL → lipsync bị skip (`lipsync: null` trong JSON).

---

## 6b. Chạy local thường (test UI — không Docker full)

Cách nhanh nhất để test UI/UX: **chỉ Docker cho DB + Redis**, còn lại chạy trực tiếp trên máy.

### Terminal 1 — DB + Redis

```bash
cd code
export APP_ENV_FILE=../.env
docker compose -f compose.yml -f compose.override.yml up -d db redis
```

### Terminal 2 — Lip-sync SyncNet (:8002)

```bash
cd code
docker compose -f compose.ai.yml up -d lipsync-deepfake
curl -s http://127.0.0.1:8002/health | python3 -m json.tool   # model_loaded: true
```

### Terminal 3 — AI service (:8001)

```bash
cd code/ai_modules
source .venv/bin/activate
# .env root phải có EKYC_LIPSYNC_SERVICE_URL=http://localhost:8002
uvicorn api.main:app --host 0.0.0.0 --port 8001 --reload
```

### Terminal 4 — AI worker (bắt buộc cho upload CCCD qua UI)

```bash
cd code/ai_modules
source .venv/bin/activate
python -m worker.ekyc_worker
```

### Terminal 5 — Backend (:8000)

```bash
cd code/backend
source .venv/bin/activate
# Lần đầu: bash scripts/prestart.sh
fastapi dev app/main.py --port 8000
```

### Terminal 6 — Frontend (:3060)

```bash
cd code/frontend
npm install && npm run dev
```

Mở **http://localhost:3060** → login `admin@example.com` / `changethis` → `/ekyc`.

| Thành phần | Bắt buộc? |
|------------|-----------|
| db + redis | Có |
| lipsync :8002 | Có nếu test lip-sync trong video risk |
| AI :8001 + worker | Có cho eKYC đầy đủ |
| backend + frontend | Có cho UI |

---

## 7. Trích xuất CCCD từ terminal (CLI)

**Cách dev đang test hàng ngày** — không cần bật API server:

```bash
cd code/ai_modules
source .venv/bin/activate

# Mặc định script: FRONT=../data/Test/image7.png, BACK=../data/Doan/back.jpg
bash scripts/run_document_extract.sh
```

### Đổi ảnh test

```bash
FRONT=../data/Test/image4.png bash scripts/run_document_extract.sh
FRONT=../data/Test/image1.png BACK=../data/Doan/back.jpg bash scripts/run_document_extract.sh
```

### Xem đầy đủ (warnings, LLM, timings)

```bash
bash scripts/run_document_extract.sh --full
```

Trong `--full` output, kiểm tra:

- `warnings` có `Trích xuất LLM (openai/gpt-4o-mini) đã tinh chỉnh fields.`
- `timings_ms.llm_extract` > 0 (vài giây)
- `timings_ms.orient` > 0 nếu ảnh dọc

### Pipeline trực tiếp (tương đương script)

```bash
python -m ekyc_document.pipeline ../data/Test/image1.png \
  --back ../data/Doan/back.jpg \
  --type CCCD \
  --fields-only \
  --no-face \
  --no-save
```

Flags thường dùng:

| Flag | Ý nghĩa |
|------|---------|
| `--fields-only` | Chỉ in `parsed_fields` JSON |
| `--full` | JSON debug đầy đủ |
| `--no-face` | Không cần InsightFace (OCR + LLM only) |
| `--no-save` | Không ghi PII vào `data/private` |

---

## 8. Xác nhận LLM đang chạy

| Dấu hiệu | Ý nghĩa |
|----------|---------|
| `/health` → `llm_extract.ready: true` | Key + provider OK |
| Warning `Trích xuất LLM ...` | LLM đã gọi và merge |
| `full_name` chuẩn hóa (vd. `Vũ Hà Dương`) | LLM đã sửa |
| `timings_ms.llm_extract` ~ 2000–5000 ms | Gọi API thật |

**LLM không chạy khi:**

- `EKYC_LLM_EXTRACT=false`
- Thiếu API key → warning `LLM extract bỏ qua: ...`
- `--fields-only` che warnings — dùng `--full` để thấy

**Merge rule:** LLM quyết định — field LLM hợp lệ **luôn ghi đè** rule parser.

---

## 9. Pipeline xử lý ảnh CCCD

```text
Ảnh upload
    ↓
EXIF orientation (nếu có)
    ↓
Auto-orient nếu ảnh dọc (EKYC_AUTO_ORIENT=true)
    ↓
Quality check (blur, glare, góc thẻ...)
    ↓
OCR RapidOCR PP-OCRv6 (rec model vi)
    ↓
Rule parser (layout tên ngắn/dài, quê quán, thường trú...)
    ↓
LLM JSON extract (EKYC_LLM_MODE=always)
    ↓
Merge: ưu tiên LLM nếu hợp lệ
    ↓
parsed_fields JSON
```

Hai mặt (front + back): OCR/parser từng mặt → merge field mặt sau (ngày cấp, nơi cấp) → **một lần LLM** trên OCR gộp.

---

## 10. Kết nối Backend

### Sơ đồ

```text
Frontend (:3060)
    → Backend FastAPI (:8000)
        → AI Service (:8001)  POST /api/v1/document/analyze
        → PostgreSQL
        → Redis (queue OCR async)
```

### `.env` backend (repo root)

```bash
EKYC_AI_SERVICE_URL=http://localhost:8001
EKYC_INTERNAL_API_KEY=<cùng key AI service>
EKYC_AI_REQUEST_TIMEOUT_SECONDS=120
```

Docker full stack (`code/compose.yml`):

```bash
EKYC_AI_SERVICE_URL=http://ai-modules:8001
```

### Header backend gửi sang AI

```http
X-Internal-API-Key: <EKYC_INTERNAL_API_KEY>
```

Code backend: `code/backend/app/services/ekyc_ai_client.py`

### Endpoint AI backend hay gọi

| Method | Path | Mục đích |
|--------|------|----------|
| POST | `/api/v1/document/analyze` | OCR + LLM CCCD |
| POST | `/api/v1/ekyc/verify` | Full: 2 mặt + video |
| POST | `/api/v1/video/upload` | Video liveness |
| GET | `/health` | Probe |

Backend dùng `response_format=compact` — schema **không đổi** (mục 13).

---

## 11. Chạy Docker

### Chỉ AI + lip-sync (nhẹ — dev AI)

```bash
cd code
mkdir -p models data/private data/record

# .env ở repo root phải có EKYC_INTERNAL_API_KEY + OPENAI_API_KEY
docker compose --env-file ../.env -f compose.ai.yml up --build
```

| URL | Service |
|-----|---------|
| http://localhost:8001 | AI modules |
| http://localhost:8002 | SyncNet lip-sync |

Compose **tự inject** `EKYC_LIPSYNC_SERVICE_URL=http://lipsync-deepfake:8002` và env ONNX (`/app/models/...`).

### Full stack (backend + frontend + AI + worker + lipsync)

```bash
cd code
export APP_ENV_FILE=../.env
docker compose --env-file ../.env -f compose.yml -f compose.override.yml up --build
```

Lần build đầu image `lipsync-deepfake` tải weights Hugging Face (`lithiumice/syncnet`) — có thể mất **2–3 phút**. Healthcheck `start_period: 180s`.

Compose **tự inject** env ONNX (`/app/models/...`) và LLM từ `.env` root khi chạy kèm `--env-file ../.env`.

---

## 12. Test API bằng cURL

Terminal đứng ở `code/`:

```bash
# OCR 2 mặt — full debug
curl -X POST "http://localhost:8001/api/v1/document/analyze" \
  -F "front_file=@data/Test/image1.png" \
  -F "back_file=@data/Doan/back.jpg" \
  -F "document_type=CCCD" \
  -F "response_format=full"

# Compact (giống backend production)
curl -X POST "http://localhost:8001/api/v1/document/analyze" \
  -F "front_file=@data/Test/image1.png" \
  -F "back_file=@data/Doan/back.jpg" \
  -F "document_type=CCCD" \
  -F "response_format=compact"
```

JSON lưu tại `code/data/record/` — field `result_file` trong response.

### Full eKYC (2 mặt + video)

Response HTTP là **bản tóm tắt** (`success`, `decision`, `risk_score`, `decision_reasons`, `top_reasons`). Chi tiết đầy đủ (OCR fields, matching, liveness, risk evidence) nằm trong file JSON tại `result_file` (thường `code/data/private/records/{record_id}.json`).

```bash
cd code/ai_modules
curl -s -X POST "http://127.0.0.1:8001/api/v1/ekyc/verify" \
  -F "front_file=@../data/Doan/front.jpg" \
  -F "back_file=@../data/Doan/back.jpg" \
  -F "video_file=@../data/Doan/live.mp4" \
  -F "document_type=CCCD" \
  | python -m json.tool | tee ../data/record/verify-response.json

# Xem chi tiết (kiểm tra payload.video.risk.lipsync)
python -m json.tool "$(python -c "import json;print(json.load(open('../data/record/verify-response.json'))['result_file'])")" | less
```

Kết quả `decision: consider` + `face_match_review` nghĩa là **cần review thủ công** (face similarity vùng xám), không phải lỗi pipeline.

### Lip-sync trực tiếp (SyncNet :8002)

```bash
curl -s -X POST "http://127.0.0.1:8002/api/lip-sync" \
  -F "video_file=@code/data/Doan/live.mp4" \
  | python3 -m json.tool
```

Probe từ AI diagnostics (cần internal key):

```bash
curl -s -H "X-Internal-API-Key: $EKYC_INTERNAL_API_KEY" \
  http://127.0.0.1:8001/api/v1/diagnostics \
  | python3 -c "import json,sys; print(json.dumps(json.load(sys.stdin)['biometric']['lipsync'], indent=2))"
```

### Video liveness only (CLI, không cần API)

```bash
python3 -m scripts.run_video_liveness \
  --video ../data/Thach/live.mp4 \
  --doc-face ../data/Thach/front_cccd.png
```

---

## 13. Output JSON — không đổi schema

Backend **không cần sửa code** parse response.

### `response_format=compact` (mặc định)

```json
{
  "document_type": "CCCD",
  "ocr_confidence": 0.85,
  "image_quality_score": 0.72,
  "document_face_detected": true,
  "document_face_confident": false,
  "document_face_confidence": null,
  "parsed_fields": {
    "id_number": "...",
    "full_name": "...",
    "date_of_birth": "...",
    "sex": "...",
    "nationality": "...",
    "place_of_origin": "...",
    "place_of_residence": "...",
    "issue_date": "...",
    "issue_place": "...",
    "expiry_date": "...",
    "license_class": null,
    "passport_number": null,
    "surname": null,
    "given_names": null,
    "extra": {}
  },
  "warnings": [],
  "record_id": "...",
  "result_file": "..."
}
```

Chỉ **giá trị** trong `parsed_fields` chính xác hơn; **cấu trúc giữ nguyên**.

---

## 13b. OCR stack YOLO + DBNet + VietOCR

Pipeline mới (bật bằng `EKYC_OCR_ENGINE=vietocr_stack`):

| Stage | Model | Mục đích |
|-------|-------|----------|
| 1 | **YOLOv8-Pose** (`cccd_pose_yolov8.pt`) | 4 góc CCCD → perspective warp |
| 2 | **YOLO11 layout** (`cccd_layout_yolov11.pt`) | Khoanh vùng field + portrait + 4 góc |
| 3 | **DBNet** (PaddleOCR DB++) | Phát hiện từng dòng text trong từng field |
| 4 | **VietOCR** (`vgg_transformer`) | Nhận dạng ký tự tiếng Việt |

Fallback khi thiếu weight:

- Pose: contour 4 góc (OpenCV)
- Layout: OCR full-page
- DBNet: RapidOCR det
- VietOCR: fallback `EKYC_OCR_FALLBACK_ENGINE` (RapidOCR)

Cài thêm:

```bash
pip install ultralytics vietocr
# DBNet backend
pip install paddleocr paddlepaddle
```

`.env` tối thiểu:

```env
EKYC_OCR_ENGINE=vietocr_stack
EKYC_DOCUMENT_WARP=true
EKYC_DBNET_BACKEND=paddle
EKYC_VIETOCR_CONFIG=vgg_transformer
# EKYC_YOLO_POSE_MODEL=code/models/cccd_pose_yolov8.pt
# EKYC_YOLO_LAYOUT_MODEL=code/models/cccd_layout_yolov11.pt
```

Warp vẫn chạy với `rapidocr_ppocrv6` khi `EKYC_DOCUMENT_WARP=true` (contour nếu chưa có YOLO pose).

---

## 13c. Video liveness — MediaPipe (web) + MiniFASNet (server)

### Luồng

1. **Frontend** (`code/frontend/`): MediaPipe Face Landmarker (WASM) chấm **blur**, **pose**, **eye openness** trong lúc quay video 5s.
2. Client chọn **best frame** theo `progress` (0..1) trong timeline video.
3. Upload `POST /api/v1/video/upload` kèm:
   - `best_frame_progress` (ưu tiên)
   - `client_frame_scores` — JSON array `{ frame_index, score, blur, pose, eye_openness, progress }`
4. **Server** map progress → frame server, chạy **MiniFASNet V2 SE** anti-spoofing trên **full frame** (không chỉ crop).

### Env server

```env
EKYC_MINIFASNET_ONNX_PATH=code/models/minifasnet.onnx
# Tuỳ chọn INT8 (~600KB), ưu tiên nếu file tồn tại:
# EKYC_MINIFASNET_INT8_ONNX_PATH=code/models/minifasnet_v2se_int8.onnx
EKYC_MIN_LIVENESS_SCORE=0.65
EKYC_MINIFASNET_CROP_SCALE=2.7
```

### Env frontend

```env
NEXT_PUBLIC_AI_SERVICE_URL=http://localhost:8001
```

Component: `components/ekyc/VideoLivenessCapture.tsx`
Hook: `hooks/useFaceMeshCapture.ts`
Scoring: `lib/faceMeshQuality.ts`

---

## 13d. Face matching — InsightFace ArcFace

So khớp 1:1 giữa mặt trên CCCD và mặt trong video/selfie qua embedding ArcFace (cosine similarity).

| Model | Profile | Ghi chú |
|---|---|---|
| `buffalo_l` | speed | Mặc định — nhanh, ~325MB |
| `glintr100` | accuracy | GlintR100 — độ chính xác cao hơn |

Env:

```env
EKYC_INSIGHTFACE_MODEL=buffalo_l
EKYC_FACE_MATCH_THRESHOLD=0.45
EKYC_FACE_CONSIDER_THRESHOLD=0.30
```

Module: `ekyc_document/face_matching/arcface.py`

---

## 13e. Speech liveness — streaming ASR

Voice challenge: user đọc câu + mã số. Engine mặc định **hybrid streaming** (ViStreamASR nếu cài được, fallback faster-whisper chunked 640ms + PhoWhisper refine).

```env
EKYC_SPEECH_ENGINE=vistream_phowhisper
EKYC_SPEECH_CHUNK_SIZE_MS=640
EKYC_PHOWHISPER_MODEL=vinai/PhoWhisper-small
EKYC_VOICE_WER_PASS_THRESHOLD=0.25
```

WebSocket realtime (frontend): `WS /api/v1/voice/stream` — xem [BACKEND_API.md](./BACKEND_API.md).

Fallback batch-only: `EKYC_SPEECH_ENGINE=phowhisper` hoặc `faster-whisper`

---

## 13f. Lip-sync deepfake (SyncNet microservice)

Phát hiện **môi không khớp audio** (Wav2Lip / deepfake lip-sync) qua microservice riêng trên **port 8002**.

### Kiến trúc

```text
Frontend / Backend
    → AI modules (:8001)  POST /api/v1/video/upload | /ekyc/verify
        → HTTP POST /api/lip-sync
            → lipsync-deepfake (:8002)  SyncNet + HF weights
```

- **Frame deepfake** (ONNX ViT trong `ai-modules`) và **lip-sync** (SyncNet `:8002`) là **hai tín hiệu risk riêng**.
- Lip-sync **chỉ chạy** khi `EKYC_LIPSYNC_ENABLED=true` **và** `EKYC_LIPSYNC_SERVICE_URL` được set.
- Không có URL → skip (`method: lipsync_disabled`), field `risk.lipsync` = `null`.

### Env (AI modules)

| Biến | Local | Docker |
|------|-------|--------|
| `EKYC_LIPSYNC_SERVICE_URL` | `http://localhost:8002` | `http://lipsync-deepfake:8002` (auto) |
| `EKYC_LIPSYNC_ENABLED` | `true` | `true` |
| `EKYC_LIPSYNC_SUSPICIOUS_THRESHOLD` | `0.65` | `0.65` |
| `EKYC_LIPSYNC_TIMEOUT_SECONDS` | `120` | `120` |

### Env (container lipsync — qua compose)

| Biến host | Container | Mặc định |
|-----------|-----------|----------|
| `EKYC_LIPSYNC_DEVICE` | `DEVICE` | `cpu` |
| `EKYC_LIPSYNC_HF_REPO` | `HF_WEIGHTS_REPO` | `lithiumice/syncnet` |
| `EKYC_LIPSYNC_MIN_TRACK` | `SYNCNET_MIN_TRACK` | `30` |

Weights: `syncnet_v2.model` + `sfd_face.pth` từ [lithiumice/syncnet](https://huggingface.co/lithiumice/syncnet). **Không** dùng `lipsync_expert.pth` (Wav2Lip — architecture khác).

Chi tiết kỹ thuật: [deepfake_lipsync/README.md](../../../deepfake_lipsync/README.md)

### Risk weights (6 tín hiệu)

Mặc định (`config.py`):

```text
deepfake:0.25, lipsync:0.15, identity:0.22, replay:0.18, camera:0.10, voice:0.10
```

Lip-sync trigger → `reason_code: lipsync_deepfake` trong `video.risk`; **không auto-block** nếu tổng `risk_score` < `EKYC_VIDEO_RISK_BLOCK_THRESHOLD` (0.72).

### Output JSON (`video.risk.lipsync`)

```json
{
  "score": 0.9668,
  "manipulation_probability": 0.9668,
  "authenticity_confidence": 0.0332,
  "verdict": "fake",
  "is_fake": true,
  "passed": false,
  "skipped": false,
  "method": "syncnet_lipsync",
  "detail": "SyncNet offset=11 frames, min_dist=6.934, confidence=0.398"
}
```

### Lưu ý vận hành

- Video eKYC **chỉ blink** (không nói) có thể bị SyncNet báo `fake` (false positive) — cân nhắc tune `SYNCNET_MIN_TRACK` hoặc chỉ weight lipsync khi có voice challenge.
- Request lipsync ~**30 giây**/video trên CPU — timeout mặc định 120s.
- Service unreachable → `lipsync_unavailable` (skip, có warning), pipeline vẫn trả kết quả.

---

## 13g. LLM gợi ý admin review (hỗ trợ quyết định)

Sau khi pipeline AI xử lý xong, LLM có thể **tóm tắt hồ sơ** và gợi ý admin approve/reject/review thủ công. **Không** thay quyết định cuối của con người.

### Kiến trúc

```text
Worker / Backend
    → POST /api/v1/admin/review-assist (AI :8001, internal key)
        → LLM (cùng provider OCR: OpenAI / DeepSeek / …)
    → lưu raw_result.ai_admin_review
Frontend /admin/ekyc
    → hiển thị panel "Gợi ý LLM cho admin"
    → nút "AI review" → POST /ekyc/requests/{id}/ai-review
```

### Env

| Biến | Mặc định | Mô tả |
|------|----------|-------|
| `EKYC_LLM_ADMIN_REVIEW` | `true` | Bật tính năng |
| `EKYC_LLM_ADMIN_REVIEW_AUTO` | `true` | Worker tự gọi sau job eKYC unified |
| `OPENAI_API_KEY` (hoặc provider khác) | — | Dùng chung với OCR LLM |
| `EKYC_INTERNAL_API_KEY` | — | Backend gọi AI `:8001` |

### Output (`ai_admin_review`)

```json
{
  "recommendation": "manual_review",
  "confidence": 0.82,
  "summary_vi": "Face match vùng xám, cần admin xem lại video.",
  "key_findings": ["..."],
  "risk_flags": ["face_match_review"],
  "supporting_evidence": ["..."],
  "suggested_admin_action": "...",
  "caveats": ["Lipsync có thể false positive với video chỉ blink"]
}
```

Module: `ekyc_document/llm_admin_review.py`  
Test: `pytest tests/test_llm_admin_review.py -v`

---

## 10b. Admin dashboard & LLM gợi ý quyết định

### Truy cập

- URL: http://localhost:3060/admin/ekyc
- Role: `ekyc_reviewer` hoặc superuser (`admin@example.com` mặc định)
- Gán reviewer: `/admin/users` → role **eKYC Reviewer**

### Luồng admin

1. Lọc hồ sơ `MANUAL_REVIEW` / `FAILED` / theo face decision
2. Mở **Verification Detail** — xem ảnh CCCD, video, OCR, video risk JSON
3. Đọc panel **Gợi ý LLM** (auto nếu `EKYC_LLM_ADMIN_REVIEW_AUTO=true`) hoặc bấm **AI review**
4. **Approve** / **Reject** (reject bắt buộc lý do) — ghi audit log

### API backend (prefix `/api/v1/ekyc/requests`)

| Method | Path | Mô tả |
|--------|------|-------|
| GET | `/` | Danh sách (admin) |
| GET | `/{id}/admin-detail` | Chi tiết + `ai_admin_review` |
| POST | `/{id}/ai-review` | Gọi LLM, lưu gợi ý |
| POST | `/{id}/approve` | Duyệt |
| POST | `/{id}/reject` | Từ chối |
| POST | `/{id}/retry` | Chạy lại AI worker |
| GET | `/{id}/files/{front\|back\|liveness}` | Tải media |

Chi tiết contract: [BACKEND_API.md](./BACKEND_API.md), frontend PII: [EKYC_PII_FRONTEND_GUIDE.md](../../frontend/EKYC_PII_FRONTEND_GUIDE.md)

---

## 14. Unit test

Chi tiết đầy đủ: **[UPGRADE_TEST_GUIDE.md](./UPGRADE_TEST_GUIDE.md)**.

```bash
cd code/ai_modules
source .venv/bin/activate

# Nhóm regression upgrade (khuyến nghị trước bàn giao)
pytest tests/test_face_matching.py tests/test_face_alignment.py \
       tests/test_lipsync_client.py tests/test_video_risk.py \
       tests/test_liveness_stack.py tests/test_onnx_stack.py \
       tests/test_speech.py tests/test_speech_streaming.py \
       tests/test_field_polish.py tests/test_llm_admin_review.py -v

# Toàn bộ suite (bỏ integration cần stack đầy đủ)
pytest tests/ -v --ignore=tests/test_full_ekyc_flow.py

python -m scripts.check_models
```

Regression OCR golden (fixture JSON, không cần ảnh):

```bash
pytest tests/test_extraction_golden.py -q
```

---

## 15. Git — commit cái gì

| Commit | Không commit |
|--------|--------------|
| `.env.example`, `code/ai_modules/.env.example` | `.env`, `code/ai_modules/.env` |
| `code/models/*.onnx`, `*.pt`, `MODEL_MANIFEST.txt` | `code/models/models/buffalo_l/` |
| Source `code/ai_modules/` **và** `code/ai_modules/tests/` | `code/data/private/*`, `code/data/record/*` |
| `docs/HANDOVER.md`, `UPGRADE_TEST_GUIDE.md` | Ảnh/video test (`*.jpg`, `*.png`, `*.mp4`) |

---

## 16. Checklist bàn giao

Người nhận tick từng mục:

- [ ] Clone repo
- [ ] `cp .env.example .env` (repo root)
- [ ] `python -m ekyc_document.setup_keys` → dán `EKYC_INTERNAL_API_KEY`
- [ ] Điền `OPENAI_API_KEY` (hoặc provider LLM khác)
- [ ] `cd code/ai_modules && python3 -m venv .venv && pip install -r requirements.txt`
- [ ] `python -m scripts.check_models` → ready
- [ ] Copy ảnh test vào `code/data/Test/` (từ team lead)
- [ ] `bash scripts/run_document_extract.sh --full` → có warning LLM
- [ ] `uvicorn api.main:app --port 8001` → `/health` ok, `llm_extract.ready: true`
- [ ] `docker compose -f compose.ai.yml up -d lipsync-deepfake` → `:8002/health` `model_loaded: true`
- [ ] `.env`: `EKYC_LIPSYNC_SERVICE_URL=http://localhost:8002` (local uvicorn)
- [ ] cURL `POST /api/v1/document/analyze` thành công
- [ ] cURL `POST /api/lip-sync` hoặc `/ekyc/verify` → có `risk.lipsync` (khi lipsync bật)
- [ ] `/admin/ekyc` → AI review → có `ai_admin_review.recommendation`
- [ ] Approve/Reject một hồ sơ test → audit log OK
- [ ] `pytest` nhóm upgrade pass (mục 14)
- [ ] `run_video_liveness` hoặc cURL `/ekyc/verify` thành công
- [ ] Backend `.env`: `EKYC_AI_SERVICE_URL` + cùng internal key

---

## 17. Xử lý sự cố

| Triệu chứng | Nguyên nhân | Cách xử lý |
|-------------|-------------|------------|
| `llm_extract.ready: false` | Thiếu/sai API key | `EKYC_LLM_PROVIDER` + key đúng provider |
| Output không có LLM warning | Key lỗi hoặc `--fields-only` | Chạy `--full`; xem `/health` |
| Tên/địa chỉ sai | Ảnh mờ | Chụp lại; bật `EKYC_AUTO_ORIENT=true` |
| `Cannot read image` | Thiếu file ảnh test | Copy `code/data/Test/` từ team lead |
| Health `unhealthy` | Thiếu `.onnx` | `git pull` hoặc `download_models` |
| `403 API key nội bộ` | Backend key ≠ AI | Đồng bộ `EKYC_INTERNAL_API_KEY` |
| Face lỗi / insightface | Chưa có buffalo_l | Chạy lần đầu có mạng; hoặc `--no-face` |
| Speech lỗi | Thiếu ffmpeg | `brew install ffmpeg` |
| `risk.lipsync: null` | Thiếu URL hoặc lipsync chưa chạy | Set `EKYC_LIPSYNC_SERVICE_URL`; `docker compose -f compose.ai.yml up lipsync-deepfake` |
| Lip-sync 503 | Weights chưa tải | Rebuild image: `docker compose -f compose.ai.yml build lipsync-deepfake` |
| Lip-sync timeout | Video dài / CPU chậm | Tăng `EKYC_LIPSYNC_TIMEOUT_SECONDS` |
| `ai_admin_review` null | LLM tắt hoặc chưa bấm AI review | `EKYC_LLM_ADMIN_REVIEW=true`; bấm AI review hoặc bật AUTO |
| AI review 502 | Backend thiếu `EKYC_INTERNAL_API_KEY` hoặc AI :8001 down | Đồng bộ internal key; check `/health` |
| `.env.example` bị ignore | Gitignore cũ | Pull mới nhất; rule `!.env.example` |

---

## Tài liệu liên quan

- [README.md](../README.md)
- [BACKEND_API.md](./BACKEND_API.md)
- [UPGRADE_TEST_GUIDE.md](./UPGRADE_TEST_GUIDE.md)
- [deepfake_lipsync/README.md](../../../deepfake_lipsync/README.md) — SyncNet microservice
- [BAN_GIAO_EKYC.md](../../BAN_GIAO_EKYC.md) — tóm tắt bàn giao
