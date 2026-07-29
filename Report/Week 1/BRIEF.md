# PROJECT BRIEF — AI eKYC DEEPFAKE DETECTION

---

## 1. Thông tin chung

* **Team:** C2-Team-036
* **Tên dự án đề xuất:** TrustID AI — Hệ thống eKYC phát hiện giả mạo khuôn mặt và giọng nói
* **Thời gian thực hiện:** 4 tuần
* **Quy mô nhóm:** 3 thành viên
* **Loại sản phẩm:** Web application / Proof of Concept
* **Đối tượng triển khai:** Sàn giao dịch, nền tảng tài chính, ứng dụng cần xác minh danh tính từ xa

---

## 2. Bối cảnh bài toán

Nhiều nền tảng hiện nay cho phép người dùng xác minh danh tính trực tuyến bằng cách tải giấy tờ tùy thân và quay video selfie. Tuy nhiên, quy trình này đang đối mặt với các hình thức tấn công tinh vi:

* Ảnh chụp lại từ màn hình hoặc giấy in.
* Video replay (phát lại video cũ).
* **Deepfake khuôn mặt** và **Face swap**.
* Giọng nói tổng hợp (AI Voice) hoặc phát lại bản ghi âm.
* Giấy tờ bị chỉnh sửa kỹ thuật số hoặc ảnh giấy tờ có chất lượng thấp.
* Sử dụng khuôn mặt người thực hiện không trùng khớp với ảnh trên giấy tờ.

> **Hệ quả:** Các phương pháp xác thực đơn giản chỉ kiểm tra ảnh giấy tờ hoặc so khớp khuôn mặt thông thường đã không còn đủ an toàn để phát hiện những hình thức gian lận công nghệ cao này.

---

## 3. Vấn đề cần giải quyết

Doanh nghiệp cần một hệ thống AI toàn diện hỗ trợ:

1. **Thu thập dữ liệu đa phương thức:** Giấy tờ tùy thân, video selfie và giọng nói của người dùng.
2. **Kiểm soát chất lượng đầu vào:** Kiểm tra chất lượng tài liệu trước khi đưa vào pipeline xử lý.
3. **Trích xuất thông tin tự động:** Sử dụng OCR để đọc dữ liệu trên giấy tờ.
4. **Xác minh sinh trắc học:** So sánh khuôn mặt trên giấy tờ với khuôn mặt trong video.
5. **Kiểm tra thực thể sống (Liveness):** Xác định người dùng có phải người thật đang tương tác trực tiếp hay không.
6. **Phát hiện Deepfake:** Nhận diện dấu hiệu video replay, deepfake khuôn mặt hoặc giọng nói tổng hợp.
7. **Đánh giá rủi ro:** Tổng hợp kết quả thành điểm số (Risk Score) và đưa ra cảnh báo trực quan cho người kiểm duyệt.

---

## 4. Người dùng mục tiêu

### 4.1. End User (Người dùng cuối)
*Là người cần thực hiện xác minh danh tính để đăng ký hoặc sử dụng dịch vụ.*
* **Nhu cầu:** Quy trình xác minh dễ hiểu, có hướng dẫn rõ ràng khi tải giấy tờ/quay video, nhận kết quả nhanh và biết rõ lý do nếu hồ sơ bị từ chối.

### 4.2. Risk/Operation Officer (Nhân viên kiểm duyệt)
*Là nhân viên của sàn giao dịch hoặc doanh nghiệp phụ trách kiểm tra hồ sơ eKYC.*
* **Nhu cầu:** Giao diện trực quan để xem danh sách phiên xác minh, thông tin OCR, kết quả face matching, liveness, deepfake và nhận cảnh báo rủi ro để đưa ra quyết định duyệt/từ chối chính xác.

### 4.3. System Administrator (Quản trị viên)
*Là người quản lý hệ thống kỹ thuật.*
* **Nhu cầu:** Theo dõi tình trạng dịch vụ, số lượng hồ sơ, quản lý ngưỡng cảnh báo (threshold) và kiểm tra log xử lý khi có lỗi xảy ra.

---

## 5. Giải pháp đề xuất

**TrustID AI** là một hệ thống web hỗ trợ quy trình eKYC toàn trình gồm hai phân hệ chính:

### Phía người dùng (Frontend Client)
1. Khởi tạo phiên eKYC.
2. Chọn loại giấy tờ (CCCD, Hộ chiếu, Bằng lái xe) và tải ảnh mặt trước/mặt sau.
3. Nhận phản hồi thời gian thực về chất lượng ảnh (Mờ, lóa, thiếu góc).
4. Quay video selfie và đọc đoạn văn bản ngẫu nhiên do hệ thống cung cấp để xác thực giọng nói.
5. Gửi hồ sơ và chờ nhận trạng thái xử lý.

### Phía doanh nghiệp (Admin Dashboard)
1. Quản lý và duyệt danh sách các phiên eKYC.
2. Xem kết quả OCR chi tiết và ảnh chân dung trích xuất từ giấy tờ.
3. Kiểm tra các chỉ số chuyên sâu:
   * **Face matching score** (Độ trùng khớp khuôn mặt).
   * **Liveness status** (Trạng thái thực thể sống).
   * **Face Deepfake score** (Tỷ lệ nghi ngờ giả mạo khuôn mặt).
   * **Voice Spoofing score** (Tỷ lệ nghi ngờ giọng nói tổng hợp/replay).
4. Xem **Điểm rủi ro tổng hợp** và lý do cảnh báo chi tiết.
5. Thực hiện hành động: Duyệt, Từ chối hoặc Yêu cầu xác minh lại.

---

## 6. Phạm vi MVP trong 4 tuần

| Trong phạm vi (In-Scope) | Ngoài phạm vi (Out-of-Scope) |
| :--- | :--- |
| • Web app hoàn chỉnh luồng eKYC cho người dùng và dashboard cho admin. | • Tích hợp trực tiếp với hệ thống core banking thật. |
| • Hỗ trợ upload CCCD, hộ chiếu hoặc bằng lái xe. | • Xác thực giấy tờ với cơ sở dữ liệu quốc gia (C06). |
| • **Document Quality Check:** Blur, độ sáng, độ tương phản, glare, kiểm tra sự hiện diện của giấy tờ. | • Chứng nhận tuân thủ pháp lý cho hệ thống tài chính/ngân hàng. |
| • OCR thông tin cơ bản & Trích xuất ảnh chân dung. | • Huấn luyện lại các foundation model từ đầu (scratch). |
| • Quay/upload video selfie, tự động tách frame và audio. | • Đảm bảo chống được 100% các loại deepfake ngoài thực tế. |
| • Face matching, Liveness detection cơ bản. | • Phát triển ứng dụng Mobile App Native (iOS/Android). |
| • Deepfake video & Voice spoofing detection bằng pretrained model/rule-based. | • Tối ưu hệ thống chịu tải lớn ở quy mô Production (High Availability). |
| • Tính điểm rủi ro tổng hợp và lưu trạng thái phiên. | • Tự động đưa ra quyết định pháp lý hoặc tài chính cuối cùng mà không qua người duyệt. |

> ⚠️ **Lưu ý:** Sản phẩm được xác định là **MVP/Proof of Concept**, không tuyên bố là hệ thống eKYC đạt chuẩn production banking.

---

## 7. Giá trị sản phẩm

* **Đối với doanh nghiệp:**
  * Giảm thiểu đáng kể thời gian và chi phí kiểm tra hồ sơ thủ công.
  * Tối ưu nhân sự nhờ cơ chế phân loại, tập trung vào các hồ sơ có mức rủi ro cao.
  * Tăng cường lá chắn bảo mật, phát hiện sớm các hình thức gian lận công nghệ cao.
  * Cung cấp bằng chứng số liệu rõ ràng để hỗ trợ quyết định kiểm duyệt.
* **Đối với người dùng:**
  * Trải nghiệm mượt mà với quy trình xác minh rõ ràng, minh bạch.
  * Tiết kiệm thời gian nhờ tính năng phản hồi chất lượng ảnh/video ngay lập tức, tránh việc bị từ chối hồ sơ nhiều lần mà không rõ nguyên nhân.

---

## 8. Chỉ số thành công của MVP

* [ ] Hoàn thành đầy đủ luồng eKYC từ bước upload dữ liệu phía người dùng đến dashboard trả kết quả phía admin.
* [ ] Mô hình OCR trích xuất chính xác các trường thông tin cốt lõi trên tập dữ liệu thử nghiệm.
* [ ] Face matching trả về điểm tương đồng (`similarity score`) ổn định.
* [ ] Hệ thống nhận diện thành công các case thử nghiệm: Ảnh mờ/lóa, khuôn mặt không khớp, video phát lại (replay), và video deepfake mẫu.
* [ ] Toàn bộ hồ sơ được phân loại trạng thái rõ ràng: `Pending`, `Processing`, `Passed`, `Review Required`, `Rejected`.
* [ ] Thời gian xử lý (Latency) cho một hồ sơ thử nghiệm mục tiêu **dưới 60 giây** (tùy thuộc vào cấu hình tài nguyên máy chủ).
* [ ] Có báo cáo đánh giá (Evaluation Report) kết quả thử nghiệm chi tiết trên tập dữ liệu nội bộ.

---

## 9. Deliverables (Sản phẩm bàn giao)

1. **Source code** hoàn chỉnh trên GitHub (gồm Backend, Frontend, AI Services).
2. **Web application** đã được triển khai môi trường Staging/Demo trực tuyến.
3. Tài liệu dự án: **Project Brief** & **Product Requirements Document (PRD)**.
4. Thiết kế **Wireframe** và **UI Flow** của hệ thống.
5. Sơ đồ **Kiến trúc hệ thống** (System Architecture).
6. Tài liệu hướng dẫn tích hợp **API documentation**.
7. Bộ dữ liệu kiểm thử mẫu (**Test dataset**).
8. Báo cáo đánh giá chất lượng mô hình (**Model Evaluation Report**).
9. **Video demo** toàn bộ luồng hoạt động của hệ thống eKYC.
10. File nhật ký dự án công khai: `JOURNAL.md` và `WORKLOG.md` được cập nhật liên tục.
11. **Slide thuyết trình** tổng kết dự án cuối kỳ.

---

## 10. Phân chia vai trò sơ bộ

### 🧑‍💻 AI/CV Lead
* Phụ trách pipeline xử lý ảnh: Document quality check, OCR & parsing, Face extraction, Face matching, Liveness detection.
* Phụ trách pipeline xử lý video/audio: Deepfake detection, Voice spoofing detection.
* Thiết kế thuật toán tính toán điểm rủi ro tổng hợp (Risk scoring).
* Đánh giá chất lượng model và viết tài liệu kỹ thuật AI.

### ⚙️ Backend Developer
* Xây dựng hệ thống API bằng **FastAPI**.
* Thiết kế Database (SQL/NoSQL) và cấu hình Object storage để lưu trữ file tài sản.
* Phát triển API upload, quản lý trạng thái phiên eKYC và tích hợp các service AI.
* Triển khai hệ thống Authentication cơ bản, đóng gói ứng dụng bằng **Docker** và cấu hình Deployment.

### 🎨 Frontend Developer
* Phát triển giao diện phía người dùng: Luồng upload giấy tờ, tích hợp camera quay video selfie và hiển thị hướng dẫn trực quan.
* Phát triển trang kết quả cho người dùng và **Dashboard kiểm duyệt** cho admin.
* Tích hợp API backend, đảm bảo giao diện đáp ứng (**Responsive UI**) và tối ưu trải nghiệm người dùng (UX).

---

## 11. Rủi ro chính và Giải pháp giảm thiểu

| Rủi ro xác định | Giải pháp giảm thiểu |
| :--- | :--- |
| **Thiếu hụt dữ liệu:** Khan hiếm dữ liệu deepfake tiếng Việt và dữ liệu CCCD thực tế để test. | Triển khai trên tập dữ liệu công khai (Public dataset) kết hợp tự thu thập tập test nội bộ quy mô nhỏ có kiểm soát. |
| **Độ tổng quát của Model:** Pretrained model có thể hoạt động kém trên dữ liệu thực tế tại Việt Nam. | Xác định rõ giới hạn MVP, tập trung tối ưu ngưỡng phân hoạch (Threshold classification) dựa trên tập dữ liệu thử nghiệm hiện có. |
| **Hiệu năng hệ thống:** Xử lý video và deepfake tốn nhiều tài nguyên, dễ gây nghẽn/chậm nếu chạy trên CPU. | Tối ưu hóa pipeline (giảm sampling rate của frame video), thiết lập hàng đợi xử lý (Queue) và đặt mục tiêu thời gian xử lý thực tế (~60s). |
| **Nhiễu môi trường:** Face anti-spoofing và Voice deepfake dễ bị sai lệch do ánh sáng kém hoặc micro nhiễu. | Thêm bộ lọc kiểm tra chất lượng môi trường đầu vào (Quality Check) và đưa ra cảnh báo yêu cầu người dùng thực hiện lại nếu không đạt chuẩn. |
| **Bảo mật dữ liệu:** Dữ liệu sinh trắc học và thông tin cá nhân (PII) có nguy cơ rò rỉ. | Tuân thủ nguyên tắc không lưu trữ dữ liệu nhạy cảm lâu hơn mức cần thiết, áp dụng mã hóa cơ bản cho dữ liệu lưu trữ. |

---