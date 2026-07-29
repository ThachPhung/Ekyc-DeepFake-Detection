# eKYC AI — Hướng dẫn test regression

Chạy trước khi bàn giao hoặc sau khi đổi pipeline OCR / liveness / lip-sync / risk scoring.

Runbook đầy đủ: [HANDOVER.md](./HANDOVER.md)

---

## 1. Chuẩn bị

```bash
cd code/ai_modules
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m scripts.check_models
```

`.env` ở repo root phải có `OPENAI_API_KEY` nếu test LLM integration.

---

## 2. Unit test (không cần Docker)

```bash
cd code/ai_modules
source .venv/bin/activate

# Nhóm khuyến nghị — nhanh, không GPU
pytest tests/test_field_polish.py \
       tests/test_lipsync_client.py \
       tests/test_llm_admin_review.py \
       tests/test_video_risk.py \
       tests/test_face_matching.py \
       tests/test_face_alignment.py \
       tests/test_liveness_stack.py \
       tests/test_onnx_stack.py \
       tests/test_speech.py \
       -v
```

Toàn bộ suite (bỏ integration cần stack):

```bash
pytest tests/ -v --ignore=tests/test_full_ekyc_flow.py
```

Golden OCR (fixture JSON):

```bash
pytest tests/test_extraction_golden.py -q
```

---

## 3. CLI — OCR CCCD

```bash
FRONT=../data/Doan/front.jpg BACK=../data/Doan/back.jpg \
  bash scripts/run_document_extract.sh --full
```

**Pass:** `success: true`, `parsed_fields.full_name` có dấu tiếng Việt, warning LLM nếu bật extract.

---

## 4. CLI — Video liveness

```bash
python -m scripts.run_video_liveness \
  --video ../data/Doan/live.mp4 \
  --doc-face ../data/Doan/front.jpg \
  --challenge blink
```

**Pass:** `decision: match`, `matching_similarity` ≥ 0.6, `passive_liveness_passed: true`.

---

## 5. Lip-sync microservice (:8002)

Cần container đang chạy:

```bash
cd code && docker compose -f compose.ai.yml up -d lipsync-deepfake
curl -s http://127.0.0.1:8002/health   # model_loaded: true
```

```bash
curl -s -X POST http://127.0.0.1:8002/api/lip-sync \
  -F "video_file=@code/data/Doan/live.mp4" | python3 -m json.tool
```

**Pass:** HTTP 200, JSON có `verdict`, `manipulation_probability`, `engine: syncnet_hf`.

---

## 6. API — full eKYC (cần :8001 + lipsync URL)

```bash
# AI local phải có EKYC_LIPSYNC_SERVICE_URL=http://localhost:8002
curl -s -X POST http://127.0.0.1:8001/api/v1/ekyc/verify \
  -F "front_file=@code/data/Doan/front.jpg" \
  -F "back_file=@code/data/Doan/back.jpg" \
  -F "video_file=@code/data/Doan/live.mp4" \
  -F "document_type=CCCD" | python3 -m json.tool
```

**Pass:**

- `success: true`, `decision: match` (hoặc `consider` nếu face vùng xám)
- File `result_file` có `payload.video.risk.lipsync` **không null**
- `payload.front_document.parsed_fields.id_number` khớp CCCD mẫu

Diagnostics probe:

```bash
curl -s -H "X-Internal-API-Key: $EKYC_INTERNAL_API_KEY" \
  http://127.0.0.1:8001/api/v1/diagnostics \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['biometric']['lipsync'])"
```

**Pass:** `probe.reachable: true`

---

## 7. Risk scoring — 6 tín hiệu

Mặc định weights (xem `config.py`):

```text
deepfake:0.25, lipsync:0.15, identity:0.22, replay:0.18, camera:0.10, voice:0.10
```

Unit test mock lipsync fake:

```bash
pytest tests/test_video_risk.py::test_assess_video_risk_includes_lipsync_signal_when_service_returns_fake -v
```

---

## 8. Khi fail

| Test fail | Kiểm tra |
|-----------|----------|
| OCR golden | `test_field_polish.py`, ảnh mờ |
| lipsync client | `test_lipsync_client.py` |
| `risk.lipsync: null` | `EKYC_LIPSYNC_SERVICE_URL`, container :8002 |
| LLM | `/health` → `llm_extract.ready` |
| Face match | buffalo_l trong `code/models/models/buffalo_l/` |

Xem thêm [HANDOVER.md §17](./HANDOVER.md#17-xử-lý-sự-cố).
