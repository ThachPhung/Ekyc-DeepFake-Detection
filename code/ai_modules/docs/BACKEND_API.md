# eKYC AI Backend Contract

Tài liệu contract giữa Backend và AI Service cho OCR giấy tờ, video/selfie matching và full eKYC.

## Chạy Service

```bash
cd code/ai_modules
source .venv/bin/activate
uvicorn api.main:app --host 0.0.0.0 --port 8001 --reload
```

Health check:

```bash
curl http://127.0.0.1:8001/health
```

Swagger UI: `http://localhost:8001/docs`

## Lưu Kết Quả JSON

Các endpoint phân tích sẽ tự lưu JSON response vào:

```text
code/data/record/
```

Response trả thêm field:

```json
{
  "result_file": "/absolute/path/to/code/data/record/ekyc-document-20260619-145421-aa948d3e.json"
}
```

`code/data/record/*`, `code/results/` và `results/` đã được gitignore.

## `POST /api/v1/document/analyze`

Phân tích ảnh giấy tờ. Có thể gửi một mặt trước hoặc cả mặt trước/mặt sau.

### Form Fields

| Field | Type | Required | Mô tả |
|---|---:|---:|---|
| `file` | file | Có nếu không gửi `front_file` | Ảnh giấy tờ, tương thích client cũ, được xem là mặt trước |
| `front_file` | file | Có nếu không gửi `file` | Ảnh mặt trước giấy tờ |
| `back_file` | file | Không | Ảnh mặt sau CCCD để trích ngày cấp/nơi cấp |
| `document_type` | string | Không | `CCCD`, `GPLX`, `PASSPORT` |
| `response_format` | string | Không | `compact` hoặc `full`, mặc định `compact` |
| `include_face_crop` | bool | Không | Trả crop mặt base64 trong debug flow nếu cần |

### cURL

Ví dụ terminal đang đứng ở thư mục `code`:

```bash
curl -s -o /dev/null -X POST "http://localhost:8001/api/v1/document/analyze" \
  -F "front_file=@data/Doan/front.jpg" \
  -F "back_file=@data/Doan/back.jpg" \
  -F "document_type=CCCD" \
  -F "response_format=full" && echo "done"
```

Nếu muốn xem JSON trực tiếp trên terminal, bỏ `-s -o /dev/null`.

### Response Chính

```json
{
  "document_type": "CCCD",
  "ocr_confidence": 0.7258,
  "image_quality_score": 0.5486,
  "document_face_detected": true,
  "document_face_confident": false,
  "document_face_confidence": null,
  "warnings": [
    "Ảnh bị mờ (blur). Vui lòng chụp lại rõ nét hơn."
  ],
  "success": true,
  "quality_details": {
    "blur": 0.088,
    "brightness": 1.0,
    "contrast": 0.6148,
    "glare": 1.0,
    "corners": 0.4
  },
  "parsed_fields": {
    "id_number": "**************",
    "full_name": "LƯƠNG QUỐC ĐOÀN",
    "date_of_birth": "********************",
    "sex": "Nam",
    "nationality": "Việt Nam",
    "place_of_origin": "Thanh, Kim Động, Hưng Yên",
    "place_of_residence": "***********************",
    "issue_date": "29/09/2022",
    "issue_place": null,
    "expiry_date": "30/05/2026"
  },
  "face": {
    "detected": true,
    "bbox": [726, 539, 175, 234],
    "confidence": 0.8697,
    "quality_score": 0.5827,
    "confident": true,
    "warnings": []
  },
  "ocr_line_count": 51,
  "result_file": "/absolute/path/to/code/data/record/ekyc-document-20260619-145421-aa948d3e.json"
}
```

Backend nên xét `warnings`, `image_quality_score`, `document_face_confident` và các field OCR quan trọng để yêu cầu user chụp lại hoặc chuyển hồ sơ sang `consider`.

## `POST /api/v1/video/upload`

Test riêng video live và so khớp với ảnh giấy tờ/ảnh chân dung.

Alias: `POST /video/upload`

### Form Fields

| Field | Type | Required | Mô tả |
|---|---:|---:|---|
| `file` | file | Có | Video live, hỗ trợ `.mp4`, `.mov`, `.webm`, `.avi`, `.mkv` |
| `doc_face` | file | Có | Ảnh giấy tờ hoặc ảnh chân dung dùng làm đối chiếu |
| `challenge` | string | Không | `turn_left`, `turn_right`, `look_up`, `look_down`, `blink`; bỏ trống thì mặc định `blink` |
| `expected_text` | string | Không | Câu user phải đọc trong video; nếu gửi thì bật speech verification |
| `best_frame_progress` | string | Không | Vị trí `0..1` trong timeline video — best frame do MediaPipe client chọn (ưu tiên) |
| `best_frame_index` | string | Không | Chỉ số frame client (tuỳ chọn, dùng khi không gửi `best_frame_progress`) |
| `client_frame_scores` | string | Không | JSON array điểm blur/pose/eye từ MediaPipe Face Mesh trên web |

### cURL

```bash
curl -s -o /dev/null -X POST "http://localhost:8001/api/v1/video/upload" \
  -F "doc_face=@data/Doan/front.jpg" \
  -F "file=@data/Doan/live.mp4" \
  -F "expected_text=Tôi xác nhận danh tính của mình" && echo "done"
```

## `GET /api/v1/voice/challenge`

Sinh câu random để frontend hiển thị cho user đọc khi quay video.

Query:

| Field | Type | Required | Mô tả |
|---|---:|---:|---|
| `seed` | int | Không | Seed tuỳ chọn để tái tạo cùng một câu |

Response:

```json
{
  "expected_text": "Tôi xác nhận danh tính của mình mã xác nhận không hai ba bốn năm sáu bảy",
  "numeric_code": "23456789",
  "instruction": "Vui lòng đọc to và rõ câu trên khi quay video."
}
```

## `POST /api/v1/voice/verify`

Kiểm tra speech độc lập trên video hoặc audio.

| Field | Type | Required | Mô tả |
|---|---:|---:|---|
| `file` | file | Có | Video hoặc audio chứa giọng nói |
| `expected_text` | string | Có | Câu challenge user phải đọc |

Response compact gồm thêm `voice_passed`, `voice_wer`, `voice_decision`.

## `WS /api/v1/voice/stream`

Streaming speech-to-text cho frontend (MediaPipe video capture). Client gửi chunk PCM 16kHz mono; server trả partial/final transcript JSON.

Query (optional): `expected_text` — dùng để refine WER khi kết thúc stream.

Yêu cầu CORS: `EKYC_CORS_ORIGINS` phải chứa origin frontend (vd. `http://localhost:3060`).

## `POST /api/v1/selfie/upload`

Selfie matching với ảnh giấy tờ.

| Field | Type | Required | Mô tả |
|---|---:|---:|---|
| `file` | file | Có | Ảnh selfie |
| `doc_face` | file | Có | Ảnh giấy tờ/ảnh chân dung để matching |

### cURL (video upload cũ, không speech)

```bash
curl -s -o /dev/null -X POST "http://localhost:8001/api/v1/video/upload" \
  -F "doc_face=@data/Doan/front.jpg" \
  -F "file=@data/Doan/live.mp4" && echo "done"
```

### Response Chính

```json
{
  "success": true,
  "decision": "match",
  "frames_analyzed": 24,
  "face_frames": 24,
  "best_frame_index": 35,
  "best_live_face": {
    "detected": true,
    "face_count": 1,
    "bbox": [120, 80, 180, 220],
    "confidence": 0.98,
    "embedding_model": "insightface/buffalo_l",
    "embedding_ready": true,
    "portrait_ok": true
  },
  "quality_score": 0.82,
  "passive_liveness": {
    "score": 0.77,
    "passed": true,
    "method": "heuristic_sequence",
    "warnings": []
  },
  "active_liveness": [
    { "challenge": "turn_left", "passed": true, "confidence": 0.72 }
  ],
  "matching": {
    "similarity": 0.62,
    "decision": "match",
    "thresholds": { "match": 0.45, "consider": 0.30 },
    "reason": "Độ tương đồng khuôn mặt đạt ngưỡng match."
  },
  "warnings": [],
  "result_file": "/absolute/path/to/code/data/record/ekyc-video-20260619-150000-aa948d3e.json"
}
```

## `POST /api/v1/ekyc/verify`

Luồng full eKYC cho backend: gửi mặt trước, mặt sau và video trong một request.

### Form Fields

| Field | Type | Required | Mô tả |
|---|---:|---:|---|
| `front_file` | file | Có | Ảnh mặt trước giấy tờ |
| `back_file` | file | Có | Ảnh mặt sau giấy tờ |
| `video_file` | file | Có | Video live |
| `document_type` | string | Không | Mặc định `CCCD` |
| `challenge` | string | Không | Active liveness challenge |
| `expected_text` | string | Không | Câu user phải đọc trong video |

### cURL

```bash
curl -s -o /dev/null -X POST "http://localhost:8001/api/v1/ekyc/verify" \
  -F "front_file=@data/Doan/front.jpg" \
  -F "back_file=@data/Doan/back.jpg" \
  -F "video_file=@data/Doan/live.mp4" \
  -F "document_type=CCCD" && echo "done"
```

### Response HTTP (compact)

API trả **bản tóm tắt**; payload đầy đủ (OCR, video, risk, `ai_summary`) được lưu vào file tại `result_file`.

```json
{
  "success": false,
  "decision": "consider",
  "record_id": "4a7c9a1a-63a8-4828-9fe1-ac016991dba4",
  "result_file": "/path/to/code/data/private/records/4a7c9a1a-....json",
  "risk_score": 0.12,
  "reason_codes": [],
  "decision_reasons": ["face_match_review"],
  "top_reasons": [],
  "message": "Kết quả chi tiết đã được lưu vào data/private/records."
}
```

- `success: true` chỉ khi `decision == "match"`.
- `decision_reasons` ví dụ: `face_match_review`, `voice_review`, `face_mismatch`.
- Mở `result_file` → field `payload` chứa `front_document`, `video`, `similarity`, `ai_summary`, `timings_ms`.

### Decision Logic

| Decision | Ý nghĩa |
|---|---|
| `match` | Có mặt trên giấy tờ, mặt giấy tờ đủ tin cậy, video match và liveness đạt |
| `consider` | Có tín hiệu chưa chắc chắn như mặt giấy tờ không đủ rõ hoặc video nằm vùng xem xét |
| `failed` | Không phát hiện mặt giấy tờ, video fail, không có mặt trong video, hoặc similarity quá thấp |

## `GET /api/v1/document/records/{record_id}`

Endpoint nội bộ để đọc PII record nếu bật lưu private record.

Header bắt buộc:

```text
X-Internal-API-Key: <EKYC_INTERNAL_API_KEY>
```

File private record nằm ở:

```text
code/data/private/records/{record_id}.json
```

## Mã Lỗi HTTP

| Code | Ý nghĩa |
|---:|---|
| `400` | Thiếu file, file rỗng hoặc sai loại file |
| `422` | Không đọc/parse được input |
| `500` | Lỗi pipeline AI |

## Biến Môi Trường

| Biến | Mặc định | Mô tả |
|---|---|---|
| `EKYC_OCR_ENGINE` | `rapidocr_ppocrv6` | OCR engine (`rapidocr_ppocrv6`, `vietocr_stack`, …) |
| `EKYC_FACE_DETECTOR` | `insightface` | Face detector, có fallback `opencv` |
| `EKYC_INSIGHTFACE_MODEL` | `buffalo_l` | Pack InsightFace: `buffalo_l` (nhanh) hoặc `glintr100` (chính xác cao) |
| `EKYC_INSIGHTFACE_PROFILE` | rỗng | Shortcut: `speed` → buffalo_l, `accuracy` → glintr100 |
| `EKYC_FACE_MATCH_THRESHOLD` | `0.45` | Ngưỡng ArcFace match 1:1 |
| `EKYC_FACE_CONSIDER_THRESHOLD` | `0.30` | Ngưỡng consider (vùng xám) |
| `EKYC_MODELS_DIR` | `code/models` | Thư mục cache model |
| `EKYC_USE_GPU` | `false` | Bật GPU nếu môi trường hỗ trợ |
| `EKYC_MIN_QUALITY_SCORE` | `0.5` | Ngưỡng chất lượng ảnh giấy tờ |
| `EKYC_MIN_DOCUMENT_FACE_CONFIDENCE` | `0.55` | Ngưỡng tin cậy mặt trên giấy tờ |
| `EKYC_PRIVATE_STORAGE_DIR` | `code/data/private` | Thư mục private record |
| `EKYC_INTERNAL_API_KEY` | rỗng | API key nội bộ đọc private record |
| `EKYC_MIN_FACE_QUALITY_SCORE` | `0.55` | Ngưỡng quality khuôn mặt |
| `EKYC_MIN_LIVENESS_SCORE` | `0.65` | Ngưỡng passive liveness |
| `EKYC_MINIFASNET_INT8_ONNX_PATH` | rỗng | MiniFASNet V2 SE INT8 (~600KB), ưu tiên hơn FP32 |
| `EKYC_DEEPFAKE_PREPROCESS` | `hf_vit` | Preprocess cho ViT deepfake ONNX |
| `EKYC_PREFER_ONNX` | `true` | Ưu tiên ONNX |
| `EKYC_REQUIRE_ONNX_MODELS` | `true` | Health unhealthy nếu thiếu ONNX |
| `EKYC_ALLOW_HEURISTIC_FALLBACK` | `false` | Heuristic khi thiếu model |
| `EKYC_USE_YOLO_LAYOUT_PIPELINE` | `true` | YOLO11 layout CCCD |
| `EKYC_YOLO_LAYOUT_MODEL` | `code/models/cccd_layout_yolov11.pt` | Weight layout |
| `EKYC_RAPIDOCR_REC_MODEL` | `vi` | Rec model tiếng Việt PP-OCRv6 |
| `EKYC_SPEECH_ENABLED` | `true` | Bật/tắt speech verification |
| `EKYC_SPEECH_ENGINE` | `vistream_phowhisper` | Hybrid streaming; fallback `phowhisper`, `faster-whisper` |
| `EKYC_SPEECH_CHUNK_SIZE_MS` | `640` | Chunk streaming ASR |
| `EKYC_PHOWHISPER_MODEL` | `vinai/PhoWhisper-small` | Model PhoWhisper (244M params) |
| `EKYC_WHISPER_MODEL_SIZE` | `small` | Model faster-whisper khi dùng engine fallback |
| `EKYC_VOICE_WER_PASS_THRESHOLD` | `0.25` | WER tối đa để pass speech challenge |
| `EKYC_VOICE_WER_CONSIDER_THRESHOLD` | `0.40` | WER tối đa để consider |
| `EKYC_MIN_AUDIO_RMS` | `0.008` | Ngưỡng phát hiện tiếng nói |
| `EKYC_MIN_AUDIO_DURATION_MS` | `800` | Độ dài audio tối thiểu |

## Gợi Ý Backend Tích Hợp

Backend upload file từ client sang AI Service bằng multipart form.

Với flow OCR giấy tờ, backend gọi `/api/v1/document/analyze`, đọc `parsed_fields`, `warnings`, `document_face_confident` và `result_file`.

Với flow full eKYC, backend gọi `/api/v1/ekyc/verify`, lưu `decision`, `similarity`, `front_document`, `video.matching` và `warnings` vào hồ sơ kiểm duyệt.

Không trả `result_file` hoặc private PII path trực tiếp ra client production nếu không cần debug.
