# Báo cáo công việc Tuần 2 — C2-App-036 (eKYC)

**Dự án:** Hệ thống eKYC (Electronic Know Your Customer)  
**Thời gian báo cáo:** Tuần 2 lần 1 (11/06/2026 – 17/06/2026)   
**Ngày lập báo cáo:** 17/06/2026☺

## 1. Công việc đã hoàn thành

### Hạ tầng & Triển khai

- Deploy ứng dụng lên Google Cloud. Link: http://staging.vintrade.xyz:3060/
- Cấu hình domain cho hệ thống.
- Thiết lập reverse proxy bằng Nginx.
- Xây dựng và triển khai môi trường staging phục vụ kiểm thử.

### Backend

- Xây dựng API eKYC.
- Xử lý upload hồ sơ/ảnh từ người dùng.
- Tích hợp service AI để xử lý dữ liệu eKYC.
- Chuẩn hóa response và trả kết quả dưới dạng JSON.

## 2. Kết quả đạt được

- Hoàn thành môi trường triển khai trên cloud.
- Hệ thống có thể truy cập thông qua domain đã cấu hình.
- API eKYC hoạt động và kết nối thành công với AI service.
- Backend trả kết quả JSON phục vụ tích hợp frontend.

## 3. Kế hoạch tiếp theo

- Thiết lập CI/CD cho môi trường staging và production.
- Thiết kế và tối ưu schema database phục vụ eKYC.
- Xây dựng cơ chế xác thực và phân quyền API (JWT/OAuth2).
- Thiết lập CI/CD cho môi trường staging và production.
- Cấu hình SSL/TLS cho website.
