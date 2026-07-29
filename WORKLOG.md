# WORKLOG — C2-App-036 (eKYC)

Ghi chép quyết định kỹ thuật, phân công, brainstorm và tiến độ theo tuần.

---

## Tuần 1 — Lần 1 (06/06/2026 – 10/06/2026)

**Dự án:** Hệ thống eKYC (Electronic Know Your Customer)  
**Mục tiêu tuần:** Khởi tạo nền tảng dự án, hoàn thiện module AI xử lý giấy tờ, chuẩn bị khung Frontend/Backend cho các tuần sau.

---

### 1. Tổng quan tiến độ

| Module | Trạng thái | Ghi chú |
|--------|------------|---------|
| AI Modules (`code/ai_modules/`) | ✅ Hoàn thành | Pipeline quality → OCR → parse → face → lưu PII mã hóa |
| API AI (`code/ai_modules/api/`) | ✅ Hoàn thành | FastAPI, 4 endpoint, contract cho Backend |
| Frontend (`code/frontend/`) | 🟡 Khởi tạo | Next.js App Router, layout cơ bản, placeholder auth/dashboard |
| Backend (`code/backend/`) | ⬜ Chưa triển khai | Chỉ có `.gitkeep` |
| AI Services (`code/ai_services/`) | ⬜ Chưa triển khai | Chỉ có `.gitkeep` |

**Kết quả kiểm thử:** 12/12 unit tests pass (`pytest tests/ -v`).

---

### 2. Phân vai công cụ AI trong tuần 1

Tuần đầu tiên, nhóm áp dụng mô hình **phân tầng AI** — mỗi công cụ đảm nhận một vai trò rõ ràng, tránh trùng lặp và giảm rủi ro “một AI làm hết mọi thứ”.

| Công cụ | Vai trò chính | Mức độ can thiệp |
|---------|---------------|------------------|
| **Gemini** | Khảo sát thị trường, quan sát nhu cầu, bối cảnh sản phẩm | Định hướng — không viết code |
| **ChatGPT** | Workflow, cấu trúc folder, kiến trúc tổng thể, review hướng đi | Chiến lược & thiết kế — không code trực tiếp |
| **Cursor (Auto)** | Hỗ trợ code thực tế trong repo, triển khai module, test, tài liệu | **Vừa phải** — code theo spec đã chốt, có review thủ công |

**Nguyên tắc làm việc:**
1. Gemini và ChatGPT dùng ở giai đoạn **suy nghĩ & quyết định** trước khi code.
2. Cursor dùng khi đã có **hướng rõ ràng** — triển khai, chỉnh sửa, kiểm tra file trong repo.
3. Mọi output quan trọng (cấu trúc folder, contract API, bảo mật PII) đều được **đọc lại và chốt** trước khi merge.

---

### 3. Gemini — Khảo sát thị trường & nhu cầu

**Mục đích:** Hiểu bối cảnh trước khi chọn hướng kỹ thuật và phạm vi tuần 1.

**Nội dung đã khảo sát / quan sát:**

- **Thị trường eKYC tại Việt Nam** đang tăng trưởng mạnh trong fintech, ngân hàng số, ví điện tử và lending — yêu cầu xác minh danh tính nhanh, chính xác, tuân thủ quy định lưu trữ dữ liệu cá nhân.
- **Nhu cầu phổ biến:** upload ảnh CCCD/GPLX/Hộ chiếu → kiểm tra chất lượng ảnh → OCR trích xuất thông tin → phát hiện ảnh chân dung trên giấy tờ → (tuần sau) so khớp với selfie.
- **Điểm đau người dùng:** ảnh mờ, chói sáng, thiếu góc giấy tờ → tỷ lệ từ chối cao; cần **cảnh báo sớm** bằng tiếng Việt thay vì chỉ trả lỗi chung.
- **Yêu cầu bảo mật:** dữ liệu nhạy cảm (họ tên, số CCCD, ngày sinh) không nên trả thẳng qua API công khai — cần tách lưu trữ riêng, mã hóa.
- **Xu hướng kỹ thuật:** OCR tiếng Việt (EasyOCR/PaddleOCR), face detection (InsightFace), pipeline modular để Backend/Frontend tích hợp qua HTTP contract.

**Kết luận từ khảo sát (ảnh hưởng trực tiếp đến tuần 1):**
- Ưu tiên **luồng mặt trước giấy tờ** + quality check + OCR + parse rule-based cho 3 loại giấy tờ VN.
- Thiết kế API **compact** (không PII) + lưu PII mã hóa riêng — phù hợp thực tế triển khai production.
- Để face matching và mặt sau CCCD cho **tuần 2** trở đi.

---

### 4. ChatGPT — Workflow, cấu trúc folder & định hướng

**Mục đích:** Xây dựng khung làm việc nhóm và kiến trúc repo trước khi viết code.

#### 4.1. Workflow nhóm đề xuất

```
Gemini (nghiên cứu) → ChatGPT (thiết kế & review) → Dev + Cursor (triển khai) → PR & merge
```

- Mỗi feature: brainstorm → chốt spec ngắn → implement → test → document.
- Nhánh Git: `feature/ai`, `feature/frontend`, `feature/backend` → merge vào `dev` → `main`.
- Tài liệu tích hợp (`BACKEND_API.md`) viết song song với API để nhóm Backend không phụ thuộc hỏi trực tiếp.

#### 4.2. Cấu trúc folder `code/` (đã chốt)

ChatGPT đề xuất tách rõ trách nhiệm từng thư mục:

```
code/
├── ai_modules/       # Pipeline AI + FastAPI (nhóm AI/CV)
├── frontend/         # Next.js (nhóm Frontend)
├── backend/          # API server tích hợp (nhóm Backend)
├── ai_services/      # Service AI bổ sung (tương lai)
├── data/private/     # PII mã hóa — gitignored
└── models/           # Cache model ML — gitignored
```

**Lý do tách `ai_modules` và `api`:**
- Core pipeline có thể gọi trực tiếp (CLI, test) hoặc qua HTTP.
- Backend chỉ cần biết contract REST, không import Python AI trực tiếp.

#### 4.3. Hướng kỹ thuật đã xem xét (brainstorm)

| Chủ đề | Phương án A | Phương án B | Quyết định |
|--------|-------------|-------------|------------|
| OCR | EasyOCR | PaddleOCR | EasyOCR mặc định; PaddleOCR qua env (linh hoạt) |
| Face detection | InsightFace | OpenCV Haar | InsightFace chính; OpenCV fallback khi thiếu model |
| Parse giấy tờ | Rule-based regex | LLM extract | Rule-based tuần 1 (ổn định, không tốn API); LLM xem xét sau |
| Lưu PII | Trả trong JSON | Mã hóa riêng `.enc` | **Mã hóa Fernet** + `record_id` tham chiếu |
| API response | Full fields | Compact + internal endpoint | Compact public + `GET /records/{id}` nội bộ |

#### 4.4. Vai trò review của ChatGPT

- Review pipeline 5 bước có hợp lý với MVP tuần 1 không.
- Gợi ý naming biến môi trường (`EKYC_*`) thống nhất.
- Nhắc thêm: startup validate key, CORS, timeout khi Backend gọi AI.
- Đề xuất `WORKLOG.md` và `Report_week1.md` để ghi lại quyết định & tiến độ.

---

### 5. Cursor (Auto) — Hỗ trợ code mức độ vừa phải

**Mục đích:** Triển khai code trong repo sau khi đã có spec từ ChatGPT và context thị trường từ Gemini — **không để AI tự thiết kế toàn bộ mà không kiểm soát**.

#### 5.1. Cách sử dụng (mức vừa phải)

| Hành vi | Mô tả |
|---------|--------|
| ✅ Có prompt rõ ràng | Ví dụ: “implement quality check với 5 tiêu chí”, “viết FastAPI endpoint analyze” |
| ✅ Code trong phạm vi file/module | Cursor đọc repo, sửa đúng file liên quan, không lan man |
| ✅ Chạy test & kiểm tra | `pytest tests/ -v` — 12 tests pass |
| ✅ Sinh tài liệu kỹ thuật | `BACKEND_API.md`, `README.md`, `Report_week1.md` |
| ⚠️ Review thủ công | Đọc lại logic parser, bảo mật PII, contract API trước merge |
| ❌ Không “auto-pilot” | Không giao một prompt mơ hồ “làm hết eKYC” mà không chia task |

#### 5.2. Công việc Cursor đã hỗ trợ triển khai

**Module `ekyc_document/` (~1.320 dòng Python):**

| File | Nội dung |
|------|----------|
| `quality_check.py` | Blur, brightness, contrast, glare, corners — cảnh báo tiếng Việt |
| `ocr.py` | EasyOCR / PaddleOCR, lazy init |
| `parser.py` | Nhận diện CCCD, GPLX, Passport; trích xuất trường rule-based |
| `face_extraction.py` | InsightFace + OpenCV fallback |
| `private_store.py` | Fernet encrypt, chmod 600, không ghi JSON plaintext |
| `pipeline.py` | Orchestrator end-to-end |
| `schemas.py` | Pydantic — `to_backend_json()` không lộ PII |
| `config.py` | Load `.env`, resolve path |
| `setup_keys.py`, `view_record.py` | CLI tiện ích vận hành |

**API `api/main.py`:**
- `POST /api/v1/document/analyze` (compact / full)
- `GET /api/v1/document/records/{record_id}` (API key nội bộ)
- `GET /health`
- Startup validate `EKYC_PRIVATE_STORAGE_KEY`

**Tests:** `test_parser.py`, `test_quality.py`, `test_private_store.py` — 12 cases.

**Cấu hình:** `requirements.txt`, `pyproject.toml`, cập nhật `.env.example`, `.gitignore` (private data, models).

#### 5.3. Giới hạn đã chủ động giữ (không nhờ Cursor làm hết)

- **Frontend eKYC UI** — chỉ scaffold Next.js, chưa làm màn upload/result (để nhóm Frontend hoặc tuần sau).
- **Backend server** — chưa implement; chỉ document contract cho tích hợp.
- **Face matching selfie** — ngoài phạm vi tuần 1.
- **Parser phức tạp / edge case OCR xấu** — cần dữ liệu thật để tinh chỉnh thủ công sau.

#### 5.4. Đánh giá hiệu quả Cursor tuần 1

**Ưu điểm:**
- Tốc độ triển khai module Python cao khi đã có spec rõ.
- Đồng bộ naming, import, cấu trúc file theo convention một chỗ.
- Tự chạy test, phát hiện lỗi cấu hình sớm.

**Cần lưu ý:**
- Luôn đọc lại phần bảo mật (PII, API key) — AI có thể đúng pattern nhưng cần xác nhận ý đồ.
- Prompt càng cụ thể (input/output, ràng buộc) thì output càng ít phải sửa tay.

---

### 6. Quyết định kỹ thuật chính

#### 6.1. Pipeline tuần 1

```
Ảnh JPEG/PNG → Quality Check → OCR → Rule-based Parse → Face Extract → Lưu PII (.enc) → JSON compact
```

#### 6.2. Contract API (compact — không PII)

```json
{
  "document_type": "CCCD",
  "ocr_confidence": 0.91,
  "image_quality_score": 0.82,
  "document_face_detected": true,
  "warnings": [],
  "record_id": "uuid"
}
```

#### 6.3. Bảo mật PII

- Fernet encryption, file `code/data/private/records/*.enc`
- `EKYC_PRIVATE_STORAGE_KEY` bắt buộc khi khởi động service
- `EKYC_INTERNAL_API_KEY` cho endpoint đọc PII nội bộ
- Gitignore `code/data/private/*`

#### 6.4. Stack & dependencies chính

- Python 3.10+, FastAPI, Uvicorn
- OpenCV, EasyOCR, InsightFace, ONNX Runtime
- cryptography (Fernet), pydantic, pytest

---

### 7. Git & milestone

| Ngày | Commit / PR | Mô tả |
|------|-------------|-------|
| 06/06 | `e2c6f62` | Initial commit dự án |
| 09/06 | `c1e2c84` | Build API FastAPI |
| 10/06 | `4b94cee` | Hoàn thành module eKYC document |
| 10/06 | `70633cd` | Merge `feature/ai` |
| 10/06 | `1dce6d7`, `9b22e19` | Khởi tạo frontend, feature/auth |
| 10/06 | PR #4, #5 | Merge frontend & dev → `main` |

---

### 8. Phân công & trạng thái nhóm (tuần 1)

| Hạng mục | Phụ trách (định hướng) | Trạng thái |
|----------|------------------------|------------|
| Module AI + API | Nhóm AI/CV + Cursor | ✅ Xong |
| Tài liệu tích hợp Backend | AI module + ChatGPT review | ✅ `BACKEND_API.md` |
| Frontend scaffold | Nhóm Frontend | 🟡 Layout cơ bản |
| Backend tích hợp | Nhóm Backend | ⬜ Tuần 2 |
| Khảo sát thị trường | Gemini | ✅ Đã làm đầu tuần |
| Workflow & kiến trúc repo | ChatGPT | ✅ Đã chốt cấu trúc |

---

### 9. Vấn đề / rủi ro đã ghi nhận

| Vấn đề | Mức độ | Hướng xử lý |
|--------|--------|-------------|
| Parser rule-based sai với OCR nhiễu | Trung bình | Thu thập ảnh thật, bổ sung rule / cân nhắc LLM tuần sau |
| Model EasyOCR/InsightFace tải lần đầu nặng | Thấp | Cache tại `code/models/`, document trong README |
| Backend chưa có → chưa test E2E | Cao (tuần 2) | Backend gọi `POST /analyze` theo `BACKEND_API.md` |
| Frontend chưa có UI upload | Trung bình | Tuần 2 sau khi có API Backend |

---

### 10. Kế hoạch tuần 2 (đề xuất)

1. **Backend:** API upload, proxy sang AI service, lưu `record_id` + metadata DB.
2. **Frontend:** Màn hình chụp/upload giấy tờ, hiển thị warnings & quality score.
3. **Tích hợp E2E:** Client → Backend → AI Service.
4. **Tinh chỉnh parser** với ảnh CCCD/GPLX thật.
5. **Face matching** (ảnh trên giấy tờ vs selfie) — nếu còn capacity.

---

### 11. Tóm tắt tuần 1 — Lần 1

Tuần đầu xây dựng **nền móng kỹ thuật** cho dự án eKYC với mô hình AI phân tầng rõ ràng:

- **Gemini** giúp đặt sản phẩm vào bối cảnh thị trường và nhu cầu thực tế (quality check, bảo mật PII, luồng giấy tờ VN).
- **ChatGPT** giúp thiết kế workflow nhóm, cấu trúc folder, so sánh phương án kỹ thuật và review hướng đi trước khi code.
- **Cursor** hỗ trợ **ở mức vừa phải** — triển khai module AI, API, test và tài liệu trong repo theo spec đã chốt, có kiểm tra thủ công.

**Deliverable chính:** Module AI eKYC document hoàn chỉnh, sẵn sàng cho Backend tích hợp qua `http://localhost:8001` và tài liệu `code/ai_modules/docs/BACKEND_API.md`.

*Báo cáo chi tiết kỹ thuật file-by-file: xem thêm `Report_week1.md`.*

---

*Cập nhật lần cuối: 10/06/2026*
