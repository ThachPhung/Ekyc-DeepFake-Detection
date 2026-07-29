# API Contract

Base URL:

```text
{API_BASE_URL}/api/v1
```

If backend is run directly with the FastAPI CLI default:

```text
http://localhost:8000/api/v1
```

Authentication header for protected routes:

```http
Authorization: Bearer <access_token>
```

Common response schemas:

```ts
type Message = {
  message: string;
};

type Token = {
  access_token: string;
  token_type: "bearer";
};

type UserPublic = {
  id: string;
  email: string;
  is_active: boolean;
  is_superuser: boolean;
  full_name: string | null;
  created_at: string | null;
};

type UsersPublic = {
  data: UserPublic[];
  count: number;
};
```

## Auth APIs

### POST `/login/access-token`

OAuth2-compatible login.

- JWT required: No
- Role required: No
- Content-Type: `application/x-www-form-urlencoded`

Request body:

```ts
type LoginForm = {
  username: string; // email
  password: string;
};
```

Response body:

```ts
type Response = Token;
```

Errors:

- `400 Incorrect email or password`
- `400 Inactive user`

### POST `/login/test-token`

Validates current JWT and returns current user.

- JWT required: Yes
- Role required: Active user

Request body:

```ts
type Request = undefined;
```

Response body:

```ts
type Response = UserPublic;
```

### POST `/password-recovery/{email}`

Starts password recovery. Always returns the same message to avoid email enumeration.

- JWT required: No in route implementation
- Role required: No

Path params:

```ts
type Params = {
  email: string;
};
```

Request body:

```ts
type Request = undefined;
```

Response body:

```ts
type Response = {
  message: "If that email is registered, we sent a password recovery link";
};
```

### POST `/reset-password/`

Resets password using a reset token.

- JWT required: No in route implementation
- Role required: No

Request body:

```ts
type Request = {
  token: string;
  new_password: string; // min 8, max 128
};
```

Response body:

```ts
type Response = {
  message: "Password updated successfully";
};
```

Errors:

- `400 Invalid token`
- `400 Inactive user`

### POST `/password-recovery-html-content/{email}`

Returns HTML email preview for password recovery.

- JWT required: Yes
- Role required: Superuser

Path params:

```ts
type Params = {
  email: string;
};
```

Response body:

```ts
type Response = string; // HTML response
```

Errors:

- `404 The user with this username does not exist in the system.`
- `403 The user doesn't have enough privileges`

## User APIs

### GET `/users/`

Lists users.

- JWT required: Yes
- Role required: Superuser

Query params:

```ts
type Query = {
  skip?: number; // default 0
  limit?: number; // default 100
};
```

Response body:

```ts
type Response = UsersPublic;
```

### POST `/users/`

Creates a new user as admin.

- JWT required: Yes
- Role required: Superuser

Request body:

```ts
type Request = {
  email: string;
  password: string; // min 8, max 128
  is_active?: boolean;
  is_superuser?: boolean;
  full_name?: string | null;
};
```

Response body:

```ts
type Response = UserPublic;
```

Errors:

- `400 The user with this email already exists in the system.`
- `403 The user doesn't have enough privileges`

### PATCH `/users/me`

Updates current user profile.

- JWT required: Yes
- Role required: Active user

Request body:

```ts
type Request = {
  full_name?: string | null;
  email?: string;
};
```

Response body:

```ts
type Response = UserPublic;
```

Errors:

- `409 User with this email already exists`

### PATCH `/users/me/password`

Updates current user's password.

- JWT required: Yes
- Role required: Active user

Request body:

```ts
type Request = {
  current_password: string; // min 8, max 128
  new_password: string; // min 8, max 128
};
```

Response body:

```ts
type Response = {
  message: "Password updated successfully";
};
```

Errors:

- `400 Incorrect password`
- `400 New password cannot be the same as the current one`

### GET `/users/me`

Returns current user.

- JWT required: Yes
- Role required: Active user

Response body:

```ts
type Response = UserPublic;
```

### DELETE `/users/me`

Deletes current user account.

- JWT required: Yes
- Role required: Active user; superusers cannot delete themselves

Response body:

```ts
type Response = {
  message: "User deleted successfully";
};
```

Errors:

- `403 Super users are not allowed to delete themselves`

### POST `/users/signup`

Public signup.

- JWT required: No
- Role required: No

Request body:

```ts
type Request = {
  email: string;
  password: string; // min 8, max 128
  full_name?: string | null;
};
```

Response body:

```ts
type Response = UserPublic;
```

Errors:

- `400 The user with this email already exists in the system`

### GET `/users/{user_id}`

Gets a user by id. Current user can get self. Superuser can get any user.

- JWT required: Yes
- Role required: Active user; superuser if requesting another user

Path params:

```ts
type Params = {
  user_id: string; // UUID
};
```

Response body:

```ts
type Response = UserPublic;
```

Errors:

- `403 The user doesn't have enough privileges`
- `404 User not found`

### PATCH `/users/{user_id}`

Updates a user as admin.

- JWT required: Yes
- Role required: Superuser

Path params:

```ts
type Params = {
  user_id: string; // UUID
};
```

Request body:

```ts
type Request = {
  email?: string;
  password?: string;
  is_active?: boolean;
  is_superuser?: boolean;
  full_name?: string | null;
};
```

Response body:

```ts
type Response = UserPublic;
```

Errors:

- `404 The user with this id does not exist in the system`
- `409 User with this email already exists`
- `403 The user doesn't have enough privileges`

### DELETE `/users/{user_id}`

Deletes a user as admin.

- JWT required: Yes
- Role required: Superuser

Path params:

```ts
type Params = {
  user_id: string; // UUID
};
```

Response body:

```ts
type Response = {
  message: "User deleted successfully";
};
```

Errors:

- `404 User not found`
- `403 Super users are not allowed to delete themselves`
- `403 The user doesn't have enough privileges`

## Utility APIs

### POST `/utils/test-email/`

Sends a test email.

- JWT required: Yes
- Role required: Superuser

Query parameter:

```ts
type Query = {
  email_to: string;
};
```

Request body:

```ts
type Request = undefined;
```

Response body:

```ts
type Response = {
  message: "Test email sent";
};
```

### GET `/utils/health-check/`

Health check endpoint.

- JWT required: No
- Role required: No

Response body:

```ts
type Response = true;
```

## Local-Only Private APIs

The private router is included only when `ENVIRONMENT == "local"`.

### POST `/private/users/`

Creates a user without authentication. This should not be exposed outside local development.

- JWT required: No
- Role required: No
- Availability: local environment only

Request body:

```ts
type Request = {
  email: string;
  password: string;
  full_name: string;
  is_verified?: boolean; // accepted by request model, not persisted in current User model
};
```

Response body:

```ts
type Response = UserPublic;
```

## Missing APIs For VinTrade AI Frontend

These APIs do not exist yet in `code/backend`:

- Market overview / prices
- Market chart data
- AI signals
- Portfolio summary
- Portfolio positions
- Trading risk scores
- eKYC workflow
- Document upload
- Face/liveness verification
- Deepfake detection
