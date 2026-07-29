# VinTrade AI Frontend

Hướng dẫn này chỉ dùng để chạy frontend Next.js trong thư mục `code/frontend`.

## Yêu cầu

- Node.js đã được cài trên máy.
- npm đã được cài kèm Node.js.
- Backend FastAPI chạy tại:

```text
http://localhost:8000/api/v1
```

## Cài dependencies

Từ thư mục dự án frontend:

```bash
cd code/frontend
npm install
```

Nếu đã có `node_modules` thì có thể bỏ qua bước này.

## Cấu hình môi trường

File `.env.local` cần có:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

Frontend sẽ dùng biến này để gọi REST API backend.

## Chạy frontend ở môi trường dev

```bash
npm run dev
```

Frontend chạy tại:

```text
http://localhost:3060
```

Mở trình duyệt và truy cập:

```text
http://localhost:3060
```

## Các trang chính

- Landing page: `http://localhost:3060`
- Login: `http://localhost:3060/login`
- Register: `http://localhost:3060/register`
- Dashboard: `http://localhost:3060/dashboard`
- eKYC demo: `http://localhost:3060/ekyc`

## Kiểm tra code

Chạy lint:

```bash
npm run lint
```

Build production:

```bash
npm run build
```

Chạy bản production sau khi build:

```bash
npm run start
```

## Lưu ý

- Login/Register hiện gọi backend qua `NEXT_PUBLIC_API_URL`.
- OAuth login buttons build provider links from `NEXT_PUBLIC_API_BASE_URL`.
- Token đăng nhập đang được lưu tạm theo từng tab trong `sessionStorage` với key `vintrade_access_token`.
- Backend cần cho phép CORS origin:

```text
http://localhost:3060
```

- Phần eKYC hiện mới hỗ trợ chọn ảnh và preview ở frontend, chưa gửi ảnh lên API eKYC thật.
