# Báo cáo công việc Tuần 2 — C2-App-036 (TrustID AI / eKYC)

**Dự án:** Hệ thống eKYC xác minh danh tính và phát hiện giả mạo  
**Thời gian báo cáo:** 14/06/2026 – 19/06/2026  
**Ngày lập báo cáo:** 19/06/2026

---

## 1. Tổng quan

Tuần 2 tập trung hoàn thiện luồng eKYC thực tế gồm OCR hai mặt CCCD, kiểm tra khuôn mặt trên giấy tờ, phân tích video live, face matching và chuẩn hóa API để backend/frontend dễ tích hợp.

Hệ thống AI service hiện có thể chạy local hoặc bằng Docker, nhận ảnh mặt trước, mặt sau và video, sau đó trả kết quả JSON và tự lưu file kết quả phục vụ kiểm thử.

---

## 2. Công việc đã hoàn thành

### AI Service

- Sửa lỗi conflict trong module AI để service FastAPI chạy ổn định.
- Hoàn thiện API phân tích giấy tờ hai mặt qua `/api/v1/document/analyze`.
- Bổ sung API phân tích video live qua `/api/v1/video/upload`.
- Bổ sung API full eKYC qua `/api/v1/ekyc/verify`, gồm:
  - OCR mặt trước/mặt sau CCCD.
  - Kiểm tra chất lượng ảnh giấy tờ.
  - Phát hiện khuôn mặt trên giấy tờ.
  - Phân tích video live.
  - Face matching giữa ảnh giấy tờ và video.
  - Trả quyết định tổng hợp `match`, `consider`, `failed`.

### Lưu kết quả kiểm thử

- Mỗi lần gọi API phân tích, hệ thống tự lưu JSON response vào `code/data/record/`.
- Response có thêm `result_file` để biết file kết quả đã lưu ở đâu.
- Thêm gitignore cho `results/`, `code/results/`, `code/data/record/*` để tránh commit dữ liệu test.

### Docker & triển khai

- Bổ sung `code/compose.ai.yml` để chạy riêng AI service bằng một lệnh Docker Compose.
- Cập nhật `code/ai_modules/Dockerfile` để tạo sẵn thư mục model, private data và record.
- Cấu hình sẵn các biến môi trường cần thiết cho Docker:
  - `EKYC_MODELS_DIR`
  - `EKYC_PRIVATE_STORAGE_DIR`
  - `EKYC_MINIFASNET_ONNX_PATH`
- Pin `torch` và `torchvision` trong `requirements.txt` để hạn chế Docker kéo dependency quá nặng không cần thiết.

### Tài liệu

- Cập nhật `code/ai_modules/README.md` với hướng dẫn:
  - Cài đặt local.
  - Chạy service.
  - Test ảnh mặt trước/mặt sau.
  - Test video.
  - Test full eKYC.
  - Chạy bằng Docker.
- Viết lại `code/ai_modules/docs/BACKEND_API.md` để mô tả contract backend đầy đủ và rõ ràng hơn.

---

## 3. Kết quả đạt được

- AI service chạy được trên port `8001`.
- Có thể test OCR CCCD hai mặt và nhận JSON kết quả.
- Có thể test video live và nhận điểm matching/liveness.
- Full eKYC trả được quyết định tổng hợp:
  - `match`: dữ liệu đạt.
  - `consider`: cần xem xét lại do ảnh/video chưa đủ tin cậy.
  - `failed`: không đạt điều kiện xác minh.
- Kết quả test được lưu tự động, không cần copy JSON từ terminal.
- Người khác có thể pull code và chạy AI service bằng Docker Compose.

---

## 4. Vấn đề còn tồn tại

- Model `minifasnet.onnx` chưa được đưa vào git vì là file binary/model; nếu không có model, hệ thống dùng `heuristic_fallback` cho passive liveness.
- Chất lượng OCR và quyết định tổng hợp phụ thuộc nhiều vào chất lượng ảnh CCCD đầu vào.
- Docker build lần đầu có thể lâu do EasyOCR, Torch và InsightFace khá nặng.

---

## 5. Kế hoạch tiếp theo

- Tối ưu Docker image để giảm thời gian build và dung lượng.
- Chuẩn hóa thêm bộ ảnh/video test mẫu cho nhóm backend/frontend.
- Tích hợp full eKYC API vào backend flow chính.
- Bổ sung xử lý lỗi rõ hơn cho frontend khi ảnh mờ, thiếu góc hoặc video không đạt.
- Kiểm thử thêm nhiều trường hợp: ảnh mờ, ảnh sai giấy tờ, video không có mặt, video không khớp người.
