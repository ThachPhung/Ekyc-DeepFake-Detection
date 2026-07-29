# OAuth Provider Setup

This project already has the OAuth backend and frontend callback flow wired.
The provider setup person only needs to create provider apps and paste keys into `.env`.

## Local URLs

Backend:

```text
http://localhost:8000
```

Frontend:

```text
http://localhost:3060
```

## Paste Into `.env`

```env
BACKEND_URL=http://localhost:8000
FRONTEND_HOST=http://localhost:3060
FRONTEND_URL=http://localhost:3060
OAUTH_STATE_SECRET=replace-with-a-long-random-string

GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=

FACEBOOK_CLIENT_ID=
FACEBOOK_CLIENT_SECRET=

MICROSOFT_CLIENT_ID=
MICROSOFT_CLIENT_SECRET=
MICROSOFT_TENANT_ID=common
```

Only fill the provider you want to enable. Empty providers will return
`provider_not_configured`.

## Provider Redirect URLs

Add these exact redirect/callback URLs in each provider dashboard.

Google:

```text
http://localhost:8000/api/auth/oauth/google/callback
```

Facebook:

```text
http://localhost:8000/api/auth/oauth/facebook/callback
```

Microsoft:

```text
http://localhost:8000/api/auth/oauth/microsoft/callback
```

## Frontend `.env.local`

In `code/frontend/.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

`NEXT_PUBLIC_API_URL` is used for normal API calls.
`NEXT_PUBLIC_API_BASE_URL` is used to build OAuth login URLs.

## Quick Test

After backend and frontend are running, open:

```text
http://localhost:8000/api/auth/oauth/google/login
```

Expected flow:

1. Browser redirects to the provider login page.
2. Provider redirects back to backend callback.
3. Backend redirects to:

```text
http://localhost:3060/auth/callback?token=...
```

4. Frontend stores the token and redirects to `/dashboard`.

If it returns to `/login?oauth_error=...`, use the error value to debug the setup.
