# Bàn giao eKYC — Tóm tắt

Tài liệu này là **điểm vào** cho team nhận bàn giao. Chi tiết từng bước: [ai_modules/docs/HANDOVER.md](./ai_modules/docs/HANDOVER.md).

---

## Phạm vi hệ thống

| Thành phần | Port | Mô tả |
|------------|------|-------|
| Frontend | 3060 | Next.js — flow eKYC 3 bước |
| Backend | 8000 | FastAPI — queue OCR, gọi AI |
| AI modules | 8001 | OCR CCCD, face match, liveness, risk, **LLM admin review** |
| Lip-sync (SyncNet) | 8002 | Microservice phát hiện môi–audio bất thường |
| PostgreSQL | 5432 | Session, user, eKYC records |
| Redis | 6379 | Queue OCR async |

---

## Bắt đầu nhanh (local thường)

```bash
# 1. Env
cp .env.example .env    # repo root — điền OPENAI_API_KEY, EKYC_INTERNAL_API_KEY

# 2. DB + Redis
cd code && docker compose -f compose.yml -f compose.override.yml up -d db redis

# 3. Lip-sync
docker compose -f compose.ai.yml up -d lipsync-deepfake

# 4. AI (terminal riêng)
cd code/ai_modules && source .venv/bin/activate
pip install -r requirements.txt
uvicorn api.main:app --port 8001 --reload

# 5. Worker OCR (terminal riêng)
python -m worker.ekyc_worker

# 6. Backend (terminal riêng)
cd code/backend && uv sync && bash scripts/prestart.sh   # lần đầu
fastapi dev app/main.py --port 8000

# 7. Frontend (terminal riêng)
cd code/frontend && npm install && npm run dev
```

Mở http://localhost:3060 — login `admin@example.com` / `changethis`.

**Quan trọng:** `.env` phải có `EKYC_LIPSYNC_SERVICE_URL=http://localhost:8002` nếu chạy AI local (không Docker).

---

## Docker full stack

```bash
cd code
export APP_ENV_FILE=../.env
docker compose --env-file ../.env -f compose.yml -f compose.override.yml up --build
```

Chỉ AI + lipsync (nhẹ hơn):

```bash
docker compose --env-file ../.env -f compose.ai.yml up --build
```

---

## Test nhanh (ảnh mẫu `data/Doan`)

```bash
cd code/ai_modules

# OCR CLI
FRONT=../data/Doan/front.jpg BACK=../data/Doan/back.jpg \
  bash scripts/run_document_extract.sh --full

# Lip-sync trực tiếp
curl -s -X POST http://127.0.0.1:8002/api/lip-sync \
  -F "video_file=@../data/Doan/live.mp4" | python3 -m json.tool

# Full eKYC API
curl -s -X POST http://127.0.0.1:8001/api/v1/ekyc/verify \
  -F "front_file=@../data/Doan/front.jpg" \
  -F "back_file=@../data/Doan/back.jpg" \
  -F "video_file=@../data/Doan/live.mp4" \
  -F "document_type=CCCD" | python3 -m json.tool
```

---

## Admin dashboard + LLM gợi ý quyết định

**URL:** http://localhost:3060/admin/ekyc  
**Quyền:** user `is_superuser` hoặc role `ekyc_reviewer` (gán tại `/admin/users`).

| Hành động | API |
|-----------|-----|
| Xem danh sách / chi tiết | `GET /api/v1/ekyc/requests/` |
| **AI review** (LLM gợi ý) | `POST /api/v1/ekyc/requests/{id}/ai-review` |
| Approve | `POST .../approve` |
| Reject | `POST .../reject` |
| Retry pipeline | `POST .../retry` |

LLM đọc OCR + biometric + risk scores → trả `recommendation` (`approve` / `reject` / `manual_review`), `summary_vi`, `risk_flags`, …  
**Admin vẫn quyết định cuối** — LLM chỉ hỗ trợ.

Tự chạy sau worker khi `EKYC_LLM_ADMIN_REVIEW_AUTO=true` → field `ai_admin_review` trong `raw_result`.  
Regen thủ công: nút **AI review** trên modal chi tiết.

```bash
# Test API (cần token admin/reviewer)
curl -s -X POST "http://localhost:8000/api/v1/ekyc/requests/{request_id}/ai-review" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

---

## Dữ liệu mẫu test (không trong git)

Copy từ team lead hoặc dùng ảnh riêng:

| Thư mục | Nội dung |
|---------|----------|
| `code/data/Doan/` | `front.jpg`, `back.jpg`, `live.mp4` |
| `code/data/Test/` | Ảnh CCCD test khác |

`.gitignore` loại `*.jpg`, `*.mp4` — clone repo **không** có sẵn ảnh CCCD.

---

## Env bắt buộc (repo root `.env`)

| Biến | Ghi chú |
|------|---------|
| `OPENAI_API_KEY` | LLM trích xuất CCCD |
| `EKYC_INTERNAL_API_KEY` | Backend ↔ AI (`python -m ekyc_document.setup_keys`) |
| `EKYC_LIPSYNC_SERVICE_URL` | Local: `http://localhost:8002` |
| `EKYC_LLM_ADMIN_REVIEW` | LLM gợi ý admin (`true`) |
| `EKYC_LLM_ADMIN_REVIEW_AUTO` | Tự chạy sau worker (`true`) |
| `POSTGRES_*` | Mặc định `localhost:5432` khi chạy local |

Mẫu đầy đủ: [.env.example](../.env.example)

---

## Regression test

```bash
cd code/ai_modules
pytest tests/test_lipsync_client.py tests/test_video_risk.py \
       tests/test_llm_admin_review.py tests/test_field_polish.py \
       tests/test_face_matching.py -v
```

Chi tiết: [ai_modules/docs/UPGRADE_TEST_GUIDE.md](./ai_modules/docs/UPGRADE_TEST_GUIDE.md)

---

## Tài liệu chi tiết

| File | Nội dung |
|------|----------|
| [ai_modules/docs/HANDOVER.md](./ai_modules/docs/HANDOVER.md) | Runbook đầy đủ |
| [ai_modules/docs/BACKEND_API.md](./ai_modules/docs/BACKEND_API.md) | Contract API |
| [deepfake_lipsync/README.md](./deepfake_lipsync/README.md) | SyncNet microservice |
| [ai_modules/README.md](./ai_modules/README.md) | Module AI — cài đặt nhanh |

---

## Checklist bàn giao (tick)

- [ ] Clone + `cp .env.example .env`
- [ ] `OPENAI_API_KEY` + `EKYC_INTERNAL_API_KEY`
- [ ] `python -m scripts.check_models` → ready
- [ ] `:8001/health` + `:8002/health` OK
- [ ] OCR `data/Doan` — dấu tiếng Việt đúng
- [ ] `/ekyc/verify` — có `risk.lipsync` (không null) khi lipsync bật
- [ ] UI `/ekyc` — 3 bước hoàn tất
- [ ] `/admin/ekyc` — xem hồ sơ, nút **AI review** trả `ai_admin_review`
- [ ] Approve/Reject ghi audit log
- [ ] `pytest` nhóm regression pass (kể cả `test_llm_admin_review`)
