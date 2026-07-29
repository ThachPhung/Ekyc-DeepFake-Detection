# Báo cáo backend sẵn sàng kết nối frontend

Phạm vi phân tích: chỉ đọc source trong `code/backend`. Không phân tích `ai_module`, không phân tích module eKYC, không phân tích frontend.

## 1. Tổng quan backend

- Framework: FastAPI.
- Ngôn ngữ/runtime: Python `>=3.10,<4.0`.
- Cách chạy backend:
  - Local theo README: vào thư mục backend, chạy `uv sync`, sau đó chạy `fastapi run --reload app/main.py`.
  - Dockerfile production command: `fastapi run --workers 4 app/main.py`.
  - Script prestart: `scripts/prestart.sh` chạy kiểm tra database, Alembic migration, rồi tạo initial data.
- Port đang dùng:
  - Chưa tìm thấy cấu hình port explicit trong source code `code/backend`.
  - Với lệnh `fastapi run` không truyền `--port`, port mặc định thường là `8000`.
- Base API URL:
  - API prefix trong source: `/api/v1`.
  - Khi chạy local mặc định: `http://localhost:8000/api/v1`.
  - Nếu Docker Compose hoặc reverse proxy map port khác thì chưa xác định được vì không nằm trong phạm vi `code/backend`.
- Swagger/OpenAPI:
  - Có OpenAPI JSON tại `/api/v1/openapi.json`.
  - FastAPI mặc định có Swagger UI tại `/docs` nếu không bị tắt; source không tắt Swagger UI.
- CORS:
  - Có cấu hình CORS bằng `CORSMiddleware` trong `app/main.py`.
  - Origin lấy từ `settings.all_cors_origins`, bao gồm `BACKEND_CORS_ORIGINS` cộng với `FRONTEND_HOST`.
  - `FRONTEND_HOST` mặc định là `http://localhost:5173`.
  - `allow_credentials=True`, `allow_methods=["*"]`, `allow_headers=["*"]`.
- Cấu hình env:
  - Có, dùng `pydantic-settings` trong `app/core/config.py`.
  - Source cấu hình đọc file env `../.env`, tức là một cấp phía trên `backend`.
  - Các biến quan trọng: `PROJECT_NAME`, `SECRET_KEY`, `API_V1_STR`, `FRONTEND_HOST`, `BACKEND_CORS_ORIGINS`, `ENVIRONMENT`, `POSTGRES_SERVER`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `FIRST_SUPERUSER`, `FIRST_SUPERUSER_PASSWORD`, SMTP config.

## 2. Cấu trúc thư mục backend

- `app/main.py`: tạo FastAPI app, cấu hình Sentry, CORS, mount router với prefix `/api/v1`.
- `app/api/main.py`: gom các route chính: `login`, `users`, `utils`, `items`; thêm `private` khi `ENVIRONMENT == "local"`.
- `app/api/deps.py`: dependency database session, OAuth2 bearer token, lấy current user, kiểm tra superuser.
- `app/api/routes/login.py`: login lấy access token, test token, password recovery, reset password.
- `app/api/routes/users.py`: CRUD user, register public, profile `/me`, đổi password, xoá account.
- `app/api/routes/utils.py`: health check và gửi test email cho superuser.
- `app/api/routes/private.py`: route tạo user local-only, chỉ include khi `ENVIRONMENT == "local"`.
- `app/core/config.py`: cấu hình env, database URL, CORS origins, token expiry, email settings.
- `app/core/security.py`: tạo JWT, hash password, verify password.
- `app/core/db.py`: tạo SQLModel engine và seed superuser đầu tiên.
- `app/models.py`: SQLModel table models và Pydantic/SQLModel request-response schemas.
- `app/crud.py`: hàm CRUD dùng chung cho user và item.
- `app/utils.py`: render email template, gửi email, tạo/verify password reset token.
- `app/backend_pre_start.py`: retry kiểm tra database sẵn sàng.
- `app/initial_data.py`: gọi seed initial data.
- `app/alembic/`: Alembic migrations.
- `scripts/prestart.sh`: check DB, chạy migration, seed data.
- `scripts/test.sh`, `scripts/tests-start.sh`, `scripts/lint.sh`, `scripts/format.sh`: script test/lint/format.
- `tests/`: test API, CRUD và script startup.
- `pyproject.toml`: dependency và tool config.
- `Dockerfile`: build và chạy backend bằng FastAPI CLI.

## 3. Danh sách module hiện có

Backend này không dùng khái niệm `Module` kiểu NestJS. Theo cấu trúc FastAPI, các module/router chính hiện có là:

- `login` router: authentication, token, password recovery.
- `users` router: user CRUD, register, profile.
- `items` router: item CRUD.
- `utils` router: health check, test email.
- `private` router: local-only helper tạo user khi `ENVIRONMENT == "local"`.
- `core.config`: env/config.
- `core.security`: JWT/password hashing.
- `core.db`: database engine và seed superuser.
- `crud`: thao tác database dùng chung.
- `models`: entity/schema.

Chưa tìm thấy trong source code các module riêng như `RoleModule`, `PermissionModule`, `AuthModule` dạng class.

## 4. Danh sách API hiện có

Base prefix cho tất cả endpoint bên dưới: `/api/v1`.

### Login/Auth APIs

| Method | Endpoint | Controller xử lý | Request body | Response body | Cần JWT | Cần role |
|---|---|---|---|---|---|---|
| POST | `/login/access-token` | `login_access_token` trong `login.py` | Form `application/x-www-form-urlencoded`: `username`, `password` theo `OAuth2PasswordRequestForm` | `Token`: `{ access_token, token_type: "bearer" }` | Không | Không |
| POST | `/login/test-token` | `test_token` trong `login.py` | Không có body | `UserPublic`: `{ email, is_active, is_superuser, full_name, id, created_at }` | Có | Không |
| POST | `/password-recovery/{email}` | `recover_password` trong `login.py` | Path param `email` | `Message`: `{ message }` | Không | Không |
| POST | `/reset-password/` | `reset_password` trong `login.py` | `NewPassword`: `{ token, new_password }` | `Message`: `{ message }` | Không | Không |
| POST | `/password-recovery-html-content/{email}` | `recover_password_html_content` trong `login.py` | Path param `email` | HTML response | Có | Superuser |

### User APIs

| Method | Endpoint | Controller xử lý | Request body | Response body | Cần JWT | Cần role |
|---|---|---|---|---|---|---|
| GET | `/users/` | `read_users` trong `users.py` | Query optional: `skip=0`, `limit=100` | `UsersPublic`: `{ data: UserPublic[], count }` | Có | Superuser |
| POST | `/users/` | `create_user` trong `users.py` | `UserCreate`: `{ email, password, is_active?, is_superuser?, full_name? }` | `UserPublic` | Có | Superuser |
| PATCH | `/users/me` | `update_user_me` trong `users.py` | `UserUpdateMe`: `{ full_name?, email? }` | `UserPublic` | Có | Không |
| PATCH | `/users/me/password` | `update_password_me` trong `users.py` | `UpdatePassword`: `{ current_password, new_password }` | `Message`: `{ message }` | Có | Không |
| GET | `/users/me` | `read_user_me` trong `users.py` | Không có body | `UserPublic` | Có | Không |
| DELETE | `/users/me` | `delete_user_me` trong `users.py` | Không có body | `Message`: `{ message }` | Có | Không; superuser bị chặn tự xoá |
| POST | `/users/signup` | `register_user` trong `users.py` | `UserRegister`: `{ email, password, full_name? }` | `UserPublic` | Không | Không |
| GET | `/users/{user_id}` | `read_user_by_id` trong `users.py` | Path param `user_id: UUID` | `UserPublic` | Có | Không nếu đọc chính mình; superuser nếu đọc user khác |
| PATCH | `/users/{user_id}` | `update_user` trong `users.py` | `UserUpdate`: `{ email?, password?, is_active?, is_superuser?, full_name? }` | `UserPublic` | Có | Superuser |
| DELETE | `/users/{user_id}` | `delete_user` trong `users.py` | Path param `user_id: UUID` | `Message`: `{ message }` | Có | Superuser |

### Utils APIs

| Method | Endpoint | Controller xử lý | Request body | Response body | Cần JWT | Cần role |
|---|---|---|---|---|---|---|
| POST | `/utils/test-email/` | `test_email` trong `utils.py` | Query parameter `email_to: EmailStr` | `Message`: `{ message }` | Có | Superuser |
| GET | `/utils/health-check/` | `health_check` trong `utils.py` | Không có body | `boolean` | Không | Không |

### Private local-only API

Route này chỉ được include khi `settings.ENVIRONMENT == "local"`.

| Method | Endpoint | Controller xử lý | Request body | Response body | Cần JWT | Cần role |
|---|---|---|---|---|---|---|
| POST | `/private/users/` | `create_user` trong `private.py` | `PrivateUserCreate`: `{ email, password, full_name, is_verified? }` | `UserPublic` | Không | Không |

## 5. Authentication hiện tại

- Login: có, endpoint `POST /api/v1/login/access-token`.
- Register: có, endpoint public `POST /api/v1/users/signup`.
- Logout: chưa tìm thấy endpoint logout trong source code.
- Cơ chế auth: JWT bearer token, không phải server-side session.
- OAuth2 dependency: `OAuth2PasswordBearer` trỏ tới `/api/v1/login/access-token`.
- JWT algorithm: `HS256`.
- Token payload: có `sub` là user id và `exp`.
- Access token: có.
- Refresh token: chưa tìm thấy trong source code.
- Thời hạn access token: `ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 8`, tức 8 ngày theo default trong source.
- Password hash:
  - Dùng `pwdlib.PasswordHash` với `Argon2Hasher` và `BcryptHasher`.
  - Hash mới dùng Argon2.
  - Password bcrypt cũ có thể verify và upgrade sang Argon2 khi login.
  - Có `DUMMY_HASH` để giảm timing attack khi email không tồn tại.
- Token trả về frontend:
  - Response JSON dạng `{ "access_token": "...", "token_type": "bearer" }`.
  - Frontend gửi lại bằng header `Authorization: Bearer <access_token>`.
- Role/permission:
  - Không có bảng role riêng.
  - Quyền admin dựa trên field `User.is_superuser`.
  - User active dựa trên field `User.is_active`.

## 6. Database hiện tại

- Database: PostgreSQL.
- Driver: `psycopg`.
- ORM/model layer: SQLModel, dựa trên SQLAlchemy.
- Migration: Alembic.
- Connection string: build từ `POSTGRES_SERVER`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`.

### Entity/schema hiện có

#### `User` table

- Table name inferred: `user`.
- Fields:
  - `id: UUID`, primary key.
  - `email: EmailStr`, unique index, max length 255.
  - `is_active: bool`.
  - `is_superuser: bool`.
  - `full_name: str | None`, max length 255.
  - `hashed_password: str`.
  - `created_at: datetime | None`.

### Quan hệ chính

- `User` 1-n `EkycRequest`.

### Seed data

- Có seed superuser đầu tiên trong `app/core/db.py` và `app/initial_data.py`.
- Nếu chưa có user với email `FIRST_SUPERUSER`, backend tạo user với `FIRST_SUPERUSER_PASSWORD` và `is_superuser=True`.
- Chưa tìm thấy seed role/permission riêng trong source code.

## 7. CORS hiện tại

- Đã enable CORS trong `app/main.py` nếu `settings.all_cors_origins` có giá trị.
- Theo source hiện tại, `all_cors_origins` luôn cộng thêm `FRONTEND_HOST`; default `FRONTEND_HOST = "http://localhost:5173"`, nên local mặc định có CORS cho Vite dev server.
- Origin được phép:
  - Các origin trong `BACKEND_CORS_ORIGINS`.
  - `FRONTEND_HOST`.
- Credentials:
  - Có, `allow_credentials=True`.
- Methods:
  - Tất cả, `allow_methods=["*"]`.
- Headers:
  - Tất cả, `allow_headers=["*"]`.
- Nếu frontend chạy Next.js ở `localhost:3000`, đề xuất:
  - Set `FRONTEND_HOST=http://localhost:3000`; hoặc
  - Thêm `http://localhost:3000` vào `BACKEND_CORS_ORIGINS`.

## 8. Những API frontend có thể kết nối ngay

### Login

- `POST /api/v1/login/access-token`
  - Gửi form data `username`, `password`.
  - Nhận `access_token`, `token_type`.
- `POST /api/v1/login/test-token`
  - Dùng để kiểm tra token hợp lệ và lấy user hiện tại.

### Register

- `POST /api/v1/users/signup`
  - Gửi `{ email, password, full_name? }`.
  - Nhận `UserPublic`.
  - Lưu ý: register không tự login trong source hiện tại; frontend cần gọi login sau register nếu muốn vào app ngay.

### Landing

- `GET /api/v1/utils/health-check/`
  - Có thể dùng kiểm tra backend sống.
- Chưa tìm thấy API public khác dành riêng cho landing trong source code.

### Dashboard/Profile

- `GET /api/v1/users/me`
  - Lấy profile hiện tại.
- `PATCH /api/v1/users/me`
  - Cập nhật `full_name`, `email`.
- `PATCH /api/v1/users/me/password`
  - Đổi mật khẩu.
- `DELETE /api/v1/users/me`
  - Xoá account user thường.
## 9. Những API còn thiếu

Chỉ xét backend chính trong `code/backend`, chưa xét AI/eKYC.

### Thiếu hoặc chưa đủ cho login/register/profile

- Logout endpoint: chưa tìm thấy trong source code. Với JWT stateless, frontend có thể logout bằng cách xoá token local, nhưng backend chưa có blacklist/revoke token.
- Refresh token: chưa tìm thấy trong source code.
- Register rồi trả token luôn: chưa có. Endpoint `/users/signup` chỉ trả `UserPublic`, không trả `Token`.
- Verify email/account activation flow: chưa tìm thấy trong source code.
- Forgot password UI callback endpoint phía frontend phụ thuộc `FRONTEND_HOST`; backend đã có password recovery/reset, nhưng cần đảm bảo email template build tồn tại khi chạy thật.
- Profile avatar, phone, address hoặc metadata người dùng: chưa có trong `User`.
- Role/permission API: chưa có bảng role và chưa có endpoint role; chỉ có `is_superuser`.

### API có thể cần bổ sung sau

- `POST /logout` hoặc token revoke nếu yêu cầu bảo mật đăng xuất phía server.
- `POST /refresh-token` nếu muốn phiên đăng nhập dài và access token ngắn hạn.
- `POST /auth/register-and-login` hoặc thay đổi register để trả token nếu UX cần auto-login.
- `GET /users/me/permissions` nếu frontend cần permission rõ ràng thay vì chỉ đọc `is_superuser`.
- Endpoint quản lý profile mở rộng nếu sản phẩm cần thêm trường ngoài `full_name` và `email`.
- Endpoint public landing content nếu landing page cần dữ liệu động.

## 10. Kế hoạch kết nối frontend-backend bước tiếp theo

1. Cấu hình CORS nếu thiếu:
   - Nếu frontend là Next.js local, set `FRONTEND_HOST=http://localhost:3000` hoặc thêm vào `BACKEND_CORS_ORIGINS`.
2. Tạo `NEXT_PUBLIC_API_URL` trong frontend:
   - Giá trị local đề xuất: `http://localhost:8000/api/v1`, nếu backend thật chạy port mặc định.
3. Tạo axios/api client:
   - Base URL lấy từ `NEXT_PUBLIC_API_URL`.
   - Interceptor gắn `Authorization: Bearer <token>` cho request cần auth.
4. Kết nối login:
   - Gửi `application/x-www-form-urlencoded` tới `/login/access-token`.
5. Lưu token:
   - Lưu `access_token` theo chiến lược frontend chọn.
   - Source backend hiện trả token trong JSON, không set cookie.
6. Gọi profile/me:
   - Gọi `GET /users/me` sau login để lấy thông tin user và trạng thái `is_superuser`.
7. Kết nối register:
   - Gọi `POST /users/signup`.
   - Sau register, gọi tiếp login nếu muốn vào dashboard ngay.
8. Làm protected route:
   - Nếu không có token hoặc `GET /users/me` lỗi 401/403 thì redirect về login.
9. Logout:
   - Hiện tại frontend xoá token local và redirect.
   - Nếu cần logout server-side, bổ sung endpoint revoke/blacklist token sau.

## 11. Đánh giá mức độ sẵn sàng

- Backend API readiness: 7/10
  - Có API auth, user, profile, item, health check và Swagger/OpenAPI. Thiếu một số API sản phẩm/domain cụ thể.
- Auth readiness: 7/10
  - Có login, register, JWT, password hash tốt, reset password. Thiếu refresh token và logout server-side.
- Database readiness: 7/10
  - Có PostgreSQL, SQLModel, Alembic, seed superuser. Schema còn cơ bản, chỉ có `user` và `item`.
- Security readiness: 7/10
  - Có Argon2, JWT expiry, active user check, superuser guard, CORS credentials. Cần kiểm tra `SECRET_KEY`, CORS production origin, token storage strategy và thiếu token revoke.
- Frontend integration readiness: 7/10
  - Có thể kết nối login/register/profile ngay. Cần chỉnh CORS cho `localhost:3000` nếu dùng Next.js và chuẩn hoá API client/token handling ở frontend.

## Kết luận ngắn

Backend chính đã đủ để frontend bắt đầu kết nối REST API cho login, register, profile và một dashboard cơ bản. Việc cần làm trước khi nối frontend là xác nhận port chạy thực tế, cấu hình CORS đúng origin frontend, tạo `NEXT_PUBLIC_API_URL`, rồi kết nối login và `/users/me`.
