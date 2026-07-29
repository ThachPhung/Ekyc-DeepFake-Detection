# Báo cáo công việc Tuần 1 — C2-App-036 (eKYC)

**Dự án:** Hệ thống eKYC (Electronic Know Your Customer)  
**Thời gian báo cáo:** Tuần 1 lần 1 (06/06/2026 – 10/06/2026)  
**Nhánh chính:** `main` (đã merge PR #5 từ `dev`)  
**Ngày lập báo cáo:** 10/06/2026

---

## 1. Tổng quan

Tuần 1 tập trung xây dựng **nền tảng dự án** và hoàn thiện **module AI xử lý giấy tờ eKYC** — phần lõi của luồng xác minh danh tính. Các nhóm Frontend và Backend đã khởi tạo cấu trúc thư mục; phần AI đã triển khai đầy đủ pipeline, API FastAPI, bảo mật PII và bộ test tự động.

### Tiến độ theo module

| Module | Trạng thái | Mô tả ngắn |
|--------|------------|------------|
| **AI Modules** (`code/ai_modules/`) | ✅ Hoàn thành | Pipeline đầy đủ: quality → OCR → parse → face → lưu PII mã hóa |
| **API AI** (`code/ai_modules/api/`) | ✅ Hoàn thành | FastAPI với 4 endpoint, CORS, xác thực nội bộ |
| **Frontend** (`code/frontend/`) | 🟡 Khởi tạo | Next.js App Router, layout cơ bản, placeholder auth/dashboard |
| **Backend** (`code/backend/`) | ⬜ Chưa triển khai | Chỉ có `.gitkeep` |
| **AI Services** (`code/ai_services/`) | ⬜ Chưa triển khai | Chỉ có `.gitkeep` |

---

## 2. Cấu trúc thư mục `code/`

```
code/
├── ai_modules/              # Module AI chính (Python) — HOÀN THÀNH
│   ├── ekyc_document/       # Core pipeline
│   ├── api/                 # FastAPI service
│   ├── docs/                # Tài liệu tích hợp backend
│   ├── tests/               # 12 unit tests
│   ├── requirements.txt
│   └── pyproject.toml
├── frontend/                # Next.js — KHỞI TẠO
│   ├── app/                 # layout, page, globals.css
│   └── features/auth/       # placeholder
├── backend/                 # placeholder
├── ai_services/             # placeholder
├── data/private/            # Lưu PII mã hóa (*.enc, gitignored)
└── models/                  # Cache model ML (gitignored)
```

---

## 3. Công việc đã hoàn thành — AI Modules

### 3.1. Pipeline xử lý giấy tờ (`ekyc_document/`)

Luồng xử lý end-to-end:

```
Ảnh giấy tờ (JPEG/PNG)
    → Quality Check (blur, sáng/tối, contrast, glare, góc giấy tờ)
    → OCR (EasyOCR / PaddleOCR)
    → Rule-based Parsing (CCCD / GPLX / Passport)
    → Face Extraction (InsightFace SCRFD / OpenCV fallback)
    → Lưu PII mã hóa + trả JSON contract
```

#### Các file đã triển khai

| File | Dòng | Chức năng |
|------|------|-----------|
| `pipeline.py` | 166 | Orchestrator chính — điều phối toàn bộ luồng |
| `quality_check.py` | 159 | Đánh giá chất lượng ảnh (5 tiêu chí, cảnh báo tiếng Việt) |
| `ocr.py` | 107 | OCR với EasyOCR (mặc định) hoặc PaddleOCR |
| `parser.py` | 185 | Nhận diện & trích xuất trường CCCD, GPLX, Passport |
| `face_extraction.py` | 94 | Phát hiện ảnh chân dung (InsightFace / OpenCV Haar) |
| `schemas.py` | 111 | Pydantic models — contract JSON cho backend |
| `private_store.py` | 176 | Lưu/đọc PII mã hóa Fernet, chmod 600 |
| `config.py` | 96 | Cấu hình runtime qua biến môi trường |
| `setup_keys.py` | 25 | CLI tạo `EKYC_PRIVATE_STORAGE_KEY` và `EKYC_INTERNAL_API_KEY` |
| `view_record.py` | 52 | CLI giải mã và xem bản ghi PII theo `record_id` |
| `__init__.py` | 6 | Export public API: `DocumentPipeline`, `analyze_document` |

**Tổng:** ~1.320 dòng Python (core + API).

### 3.2. Quality Check — Chi tiết

Đánh giá 5 tiêu chí với trọng số có thể cấu hình:

| Tiêu chí | Trọng số | Phương pháp |
|----------|----------|-------------|
| Blur | 30% | Laplacian variance |
| Brightness | 15% | Mean pixel intensity |
| Contrast | 15% | Standard deviation |
| Glare | 20% | Tỷ lệ pixel sáng > 245 |
| Corners | 20% | Canny edge + contour detection |

Cảnh báo trả về bằng tiếng Việt (ví dụ: *"Ảnh bị mờ"*, *"Phát hiện vùng chói sáng"*, *"Không xác định được khung giấy tờ"*).

### 3.3. OCR

- **Engine mặc định:** EasyOCR (ngôn ngữ `vi`, `en`)
- **Engine thay thế:** PaddleOCR (cấu hình qua `EKYC_OCR_ENGINE=paddleocr`)
- Trả về: danh sách dòng OCR, confidence trung bình, raw text

### 3.4. Parser — Rule-based

Hỗ trợ 3 loại giấy tờ Việt Nam:

| Loại | Từ khóa nhận diện | Trường trích xuất |
|------|-------------------|-------------------|
| **CCCD** | CĂN CƯỚC, CITIZEN IDENTITY | Số CCCD (12 chữ số), họ tên, ngày sinh, giới tính, quốc tịch, quê quán, nơi thường trú, ngày cấp/hết hạn |
| **GPLX** | GIẤY PHÉP LÁI XE, GPLX | Số GPLX, họ tên, ngày sinh, hạng bằng |
| **PASSPORT** | PASSPORT, HỘ CHIẾU | Surname, given names, số passport, quốc tịch, ngày sinh |

### 3.5. Face Extraction

- **Detector mặc định:** InsightFace (`buffalo_l` model, SCRFD)
- **Fallback:** OpenCV Haar Cascade (nhẹ, không cần tải model)
- Trả về: `detected`, `bbox`, `confidence`, tùy chọn `crop_base64`

### 3.6. Bảo mật PII

Thiết kế **tách biệt dữ liệu cá nhân** khỏi response công khai:

1. Response API **không chứa** họ tên, số CCCD, ngày sinh...
2. PII được lưu mã hóa **Fernet** tại `code/data/private/records/{uuid}.enc`
3. File `.enc` có quyền `chmod 600`, thư mục gitignored
4. `EKYC_PRIVATE_STORAGE_KEY` **bắt buộc** — service không khởi động nếu thiếu
5. Đọc PII qua endpoint nội bộ với header `X-Internal-API-Key`

---

## 4. Công việc đã hoàn thành — API FastAPI

**File:** `code/ai_modules/api/main.py` (142 dòng)

| Endpoint | Method | Mô tả |
|----------|--------|-------|
| `/health` | GET | Health check |
| `/api/v1/document/analyze` | POST | Phân tích ảnh giấy tờ (compact/full) |
| `/api/v1/document/analyze/full` | POST | Shortcut trả response đầy đủ |
| `/api/v1/document/records/{record_id}` | GET | Đọc PII nội bộ (yêu cầu API key) |

**Tính năng:**
- Upload multipart (`file`, `document_type`, `response_format`, `include_face_crop`)
- CORS middleware (cấu hình qua `EKYC_CORS_ORIGINS`)
- Validate encryption key khi startup
- Xử lý lỗi HTTP: 400, 403, 404, 422, 500, 503
- Swagger UI tại `http://localhost:8001/docs`

**Response compact (contract tuần 1):**

```json
{
  "document_type": "CCCD",
  "ocr_confidence": 0.91,
  "image_quality_score": 0.82,
  "document_face_detected": true,
  "warnings": [],
  "record_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

---

## 5. Công việc đã hoàn thành — Frontend

**Framework:** Next.js (App Router) + Tailwind CSS v4 + Geist font

| File | Trạng thái | Nội dung |
|------|------------|----------|
| `app/layout.tsx` | ✅ | Root layout, metadata, font Geist Sans/Mono |
| `app/page.tsx` | ✅ | Trang chủ mặc định Next.js (placeholder) |
| `app/globals.css` | ✅ | Tailwind import, dark mode CSS variables |
| `app/login/` | 🟡 | Thư mục placeholder (`.gitkeep`) |
| `app/dashboard/` | 🟡 | Thư mục placeholder (`.gitkeep`) |
| `features/auth/` | 🟡 | Thư mục placeholder (`.gitkeep`) |

**Commit liên quan:** `1dce6d7 build frontend first`, `9b22e19 feature/auth`

Frontend đã khởi tạo cấu trúc thư mục cho auth và dashboard nhưng **chưa triển khai** giao diện eKYC thực tế.

---

## 6. Công việc chưa triển khai

| Module | Ghi chú |
|--------|---------|
| `code/backend/` | Chỉ có `.gitkeep` — chưa có API server, database, tích hợp AI |
| `code/ai_services/` | Chỉ có `.gitkeep` — dự kiến cho các service AI bổ sung |
| Frontend eKYC UI | Chưa có màn hình upload giấy tờ, hiển thị kết quả, luồng xác minh |
| Tích hợp end-to-end | Frontend ↔ Backend ↔ AI Service chưa nối |

---

## 7. Kiểm thử tự động

**Framework:** pytest  
**Kết quả:** ✅ **12/12 tests passed** (0.34s)

| File test | Số test | Nội dung kiểm tra |
|-----------|---------|-------------------|
| `test_parser.py` | 5 | Nhận diện CCCD/GPLX/Passport, trích xuất trường |
| `test_private_store.py` | 5 | Mã hóa/giải mã, quyền file, thiếu key, record không tồn tại |
| `test_quality.py` | 2 | Ảnh tối cảnh báo, ảnh sắc nét > ảnh mờ |

```bash
cd code/ai_modules
source .venv/bin/activate
pytest tests/ -v
# ============================== 12 passed in 0.34s ==============================
```

---

## 8. Tài liệu & Cấu hình

| File | Mô tả |
|------|-------|
| `code/ai_modules/README.md` | Hướng dẫn cài đặt, chạy API, CLI, test |
| `code/ai_modules/docs/BACKEND_API.md` | Contract tích hợp backend (endpoint, payload, biến môi trường) |
| `.env.example` | Template biến môi trường (AI logging + eKYC keys) |
| `requirements.txt` | Dependencies: FastAPI, EasyOCR, InsightFace, OpenCV, cryptography... |
| `pyproject.toml` | Metadata package, cấu hình pytest |

### Biến môi trường eKYC

| Biến | Bắt buộc | Mô tả |
|------|----------|-------|
| `EKYC_PRIVATE_STORAGE_KEY` | ✅ | Fernet key mã hóa PII |
| `EKYC_INTERNAL_API_KEY` | ✅ | API key đọc bản ghi nội bộ |
| `EKYC_OCR_ENGINE` | ❌ | `easyocr` (mặc định) hoặc `paddleocr` |
| `EKYC_FACE_DETECTOR` | ❌ | `insightface` (mặc định) hoặc `opencv` |
| `EKYC_USE_GPU` | ❌ | `false` (mặc định) |
| `EKYC_MIN_QUALITY_SCORE` | ❌ | `0.5` (mặc định) |

---

## 9. Lịch sử Git (milestones tuần 1)

| Ngày | Commit | Mô tả |
|------|--------|-------|
| 29/05 | `42f8720` | Khởi tạo repo từ starter template Cohort 2 |
| 06/06 | `e2c6f62` | Initial commit dự án |
| 09/06 | `9c687e6` | Tạo cấu trúc thư mục `code/` |
| 09/06 | `c1e2c84` | Xây dựng API FastAPI |
| 09/06 | `21e1b89` | Thêm thư mục làm việc |
| 10/06 | `4b94cee` | **Hoàn thành module eKYC document** |
| 10/06 | `70633cd` | Merge nhánh `feature/ai` |
| 10/06 | `1dce6d7` | Khởi tạo frontend Next.js |
| 10/06 | `9b22e19` | Feature auth (cấu trúc thư mục) |
| 10/06 | `dde8e77` | Merge PR #4 frontend |
| 10/06 | `f095341` | Merge PR #5 dev → main |

---

## 10. Hướng dẫn chạy nhanh

### AI Service

```bash
cd code/ai_modules
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m ekyc_document.setup_keys   # copy output vào .env
uvicorn api.main:app --host 0.0.0.0 --port 8001 --reload
```

### CLI phân tích ảnh

```bash
python -m ekyc_document.pipeline path/to/cccd.jpg --type CCCD --full
```

### Frontend (khi có package.json)

```bash
cd code/frontend
npm install && npm run dev
```

---

## 11. Kế hoạch tuần 2 (đề xuất)

1. **Backend:** Triển khai API server, nhận upload từ client, gọi AI service, lưu DB
2. **Frontend:** Màn hình upload giấy tờ, preview ảnh, hiển thị warnings/quality score
3. **Tích hợp:** Nối luồng Frontend → Backend → AI Service end-to-end
4. **eKYC mặt sau:** Mở rộng pipeline cho mặt sau CCCD (nếu cần)
5. **Face matching:** So khớp ảnh chân dung trên giấy tờ với ảnh selfie (tuần sau)

---

## 12. Tổng kết

Tuần 1 đạt được **mục tiêu chính** là xây dựng module AI xử lý giấy tờ eKYC hoàn chỉnh với:

- ✅ Pipeline 5 bước (quality → OCR → parse → face → lưu PII)
- ✅ API FastAPI sẵn sàng tích hợp backend
- ✅ Bảo mật PII (mã hóa Fernet, tách response công khai/riêng tư)
- ✅ 12 unit tests pass
- ✅ Tài liệu API đầy đủ cho nhóm Backend
- 🟡 Frontend/Backend mới ở giai đoạn khởi tạo cấu trúc

**Thành viên nhóm Backend và Frontend** có thể bắt đầu tích hợp ngay với AI service tại `http://localhost:8001` theo contract trong `code/ai_modules/docs/BACKEND_API.md`.
