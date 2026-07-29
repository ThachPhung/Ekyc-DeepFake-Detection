# Frontend Integration Plan

Scope: plan for connecting the current frontend to `code/backend` through REST APIs. eKYC workflow, CCCD upload, face verification, deepfake detection, and AI modules are intentionally excluded for now.

## Current Backend API Base

Backend API prefix:

```text
/api/v1
```

Expected direct local backend URL:

```text
http://localhost:8000/api/v1
```

Recommended frontend environment variable:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
```

Current frontend dev port has been configured as:

```text
http://localhost:3060
```

Backend CORS currently defaults to:

```text
FRONTEND_HOST=http://localhost:5173
```

Before integrating from the Next frontend, update backend environment configuration so CORS allows:

```env
FRONTEND_HOST=http://localhost:3060
```

or:

```env
BACKEND_CORS_ORIGINS=http://localhost:3060
```

## Authentication Flow

### Login

Use:

```http
POST /api/v1/login/access-token
Content-Type: application/x-www-form-urlencoded
```

Frontend login form fields:

- `email`
- `password`

Backend expects OAuth2 form fields:

- `username`: use the email value
- `password`

Request example:

```ts
const body = new URLSearchParams();
body.set("username", email);
body.set("password", password);

const res = await fetch(`${API_URL}/login/access-token`, {
  method: "POST",
  headers: {
    "Content-Type": "application/x-www-form-urlencoded",
  },
  body,
});
```

Response:

```ts
type Token = {
  access_token: string;
  token_type: "bearer";
};
```

After login, call:

```http
GET /api/v1/users/me
Authorization: Bearer <token>
```

to hydrate current user data.

### Register

Use:

```http
POST /api/v1/users/signup
Content-Type: application/json
```

Current frontend register form:

- full name
- email
- phone number
- password
- confirm password
- terms checkbox

Backend supports:

```ts
type UserRegister = {
  email: string;
  password: string;
  full_name?: string | null;
};
```

Important gap:

- Backend does not currently store `phone_number`.
- Frontend should either ignore phone number during first integration or backend should add a phone field later.

Recommended first integration behavior:

- Validate password and confirm password in frontend.
- Validate terms checkbox in frontend.
- Send only `email`, `password`, and `full_name` to `/users/signup`.
- After successful signup, either:
  - redirect to login, or
  - automatically call login to get token.

## Token Storage

Recommended pragmatic first step:

- Store `access_token` in memory plus `localStorage` if "Remember me" is checked.
- Store in `sessionStorage` if "Remember me" is not checked.
- Keep token under a single key, for example:

```ts
const TOKEN_KEY = "vintrade_access_token";
```

Security note:

- `localStorage` is simple but exposed to XSS.
- A more secure future version should use HttpOnly cookies via a backend/session endpoint or a Next.js BFF route.

## Frontend API Client

Create a small client module in the frontend, for example:

```text
frontend/lib/api/client.ts
```

Suggested responsibilities:

- Read `process.env.NEXT_PUBLIC_API_URL`.
- Build URLs safely.
- Attach `Authorization: Bearer <token>` when available.
- Send JSON bodies by default.
- Send form body for login.
- Normalize API errors into a predictable frontend error shape.

Suggested TypeScript shape:

```ts
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export async function apiFetch<T>(
  path: string,
  options: RequestInit & { token?: string } = {},
): Promise<T> {
  const headers = new Headers(options.headers);

  if (options.token) {
    headers.set("Authorization", `Bearer ${options.token}`);
  }

  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(error?.detail ?? `API request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}
```

Suggested auth API module:

```text
frontend/lib/api/auth.ts
```

Functions:

- `login(email: string, password: string): Promise<Token>`
- `signup(input: { email: string; password: string; full_name?: string }): Promise<UserPublic>`
- `getMe(token: string): Promise<UserPublic>`
- `testToken(token: string): Promise<UserPublic>`
- `requestPasswordRecovery(email: string): Promise<Message>`
- `resetPassword(token: string, newPassword: string): Promise<Message>`

## How To Call APIs From Frontend Pages

Current frontend pages are mostly presentational. First integration should be conservative:

### Login page

Wire submit handler to:

```text
POST /login/access-token
```

Then:

1. Store token.
2. Call `/users/me`.
3. Store current user in auth state.
4. Redirect to a dashboard/landing page.

### Register page

Wire submit handler to:

```text
POST /users/signup
```

Then:

1. Show success state.
2. Redirect to login or automatically login.
3. Do not send phone number until backend supports it.

### Header

When auth state exists:

- Replace `Login` with user/account menu.
- Optionally show logout.

### Protected frontend pages

For pages that require auth later:

- Check token presence.
- Call `/users/me` to validate token.
- Redirect to `/login` if invalid.

## APIs Already Available

Useful for immediate frontend integration:

- `POST /login/access-token`
  - Login and token generation.
- `POST /users/signup`
  - Public registration.
- `GET /users/me`
  - Current user profile.
- `PATCH /users/me`
  - Update current user profile.
- `PATCH /users/me/password`
  - Change password.
- `POST /login/test-token`
  - Validate token.
- `POST /password-recovery/{email}`
  - Start forgot-password flow.
- `POST /reset-password/`
  - Complete reset-password flow.
- `GET /utils/health-check/`
  - Backend health check.

Available but likely not relevant to the current VinTrade demo UI:

- `/items/*`
  - Generic template item CRUD.
- Admin `/users/*`
  - User management for superusers.
- `/utils/test-email/`
  - Superuser-only email test.
- `/private/users/`
  - Local-only dev helper.

## APIs Missing For Current VinTrade AI Product UI

The current frontend displays fake data for several fintech/trading concepts. Backend does not yet provide these:

- Market stats:
  - Total market cap
  - 24h volume
  - Active users
  - AI signals today
- Market overview:
  - BTC
  - ETH
  - VNINDEX
  - AAPL
  - TSLA
- Chart/candlestick/volume series
- AI signal feed
- Portfolio summary/tracking
- Risk scoring
- Pricing/subscription
- eKYC workflow
- Document upload
- Face/liveness verification
- Deepfake detection

Per current instruction, eKYC and AI/deepfake APIs should be deferred.

## Recommended Integration Sequence

1. Add frontend env:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
```

2. Update backend CORS for frontend dev port:

```env
FRONTEND_HOST=http://localhost:3060
```

3. Create frontend API client and auth API module.

4. Wire login form:

- submit to `/login/access-token`
- store token
- call `/users/me`
- handle invalid credentials

5. Wire register form:

- submit to `/users/signup`
- ignore phone number for now or keep it client-only
- handle duplicate email error

6. Add auth state helper:

- `getToken`
- `setToken`
- `clearToken`
- `getCurrentUser`

7. Add logout.

8. Keep market/trading/eKYC UI using fake data until backend endpoints are intentionally designed.

## Open Questions Before Coding Integration

- Should login token be stored in `localStorage`, `sessionStorage`, or moved to HttpOnly cookie via a Next.js BFF route?
- Should signup automatically login or redirect to login?
- Should phone number become a real backend user field?
- What route should authenticated users land on after login?
- Should `/items` be removed/ignored in the product frontend since it is template CRUD and not VinTrade domain data?
- What exact backend URL/port will be used in local Docker Compose?
