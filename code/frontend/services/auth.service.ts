import {
  apiFetch,
  BACKEND_BASE_URL,
  clearAuthStorage,
  setStoredToken,
  USER_STORAGE_KEY,
} from "@/lib/api";

export type UserPublic = {
  id: string;
  email: string;
  is_active: boolean;
  is_superuser: boolean;
  role: UserRole;
  full_name: string | null;
  created_at: string | null;
  ekyc_status?: EkycStatus | null;
};

export type UserRole = "user" | "ekyc_reviewer";
export type EkycStatus =
  | "PENDING"
  | "PROCESSING"
  | "SUCCESS"
  | "FAILED"
  | "MANUAL_REVIEW";

export type TokenResponse = {
  access_token: string;
  token_type: string;
};

export type MessageResponse = {
  message: string;
};

export type OAuthProvider = "google" | "facebook" | "microsoft";

export type RegisterPayload = {
  email: string;
  password: string;
  full_name: string;
};

export type UpdateMePayload = {
  full_name?: string;
  email?: string;
};

export function getOAuthLoginUrl(provider: OAuthProvider): string {
  return `${BACKEND_BASE_URL.replace(/\/$/, "")}/api/auth/oauth/${provider}/login`;
}

export async function login(
  email: string,
  password: string,
): Promise<TokenResponse> {
  const body = new URLSearchParams();
  body.set("username", email);
  body.set("password", password);

  const token = await apiFetch<TokenResponse>(
    "/login/access-token",
    {
      method: "POST",
      body,
    },
    { auth: false },
  );

  setStoredToken(token.access_token);
  return token;
}

export async function getMe(): Promise<UserPublic> {
  return apiFetch<UserPublic>("/users/me", { method: "GET" }, { auth: true });
}

export async function updateMe(payload: UpdateMePayload): Promise<UserPublic> {
  return apiFetch<UserPublic>(
    "/users/me",
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
    { auth: true },
  );
}

export async function register(payload: RegisterPayload): Promise<UserPublic> {
  return apiFetch<UserPublic>(
    "/users/signup",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    { auth: false },
  );
}

export async function verifyEmail(token: string): Promise<MessageResponse> {
  return apiFetch<MessageResponse>(
    "/users/verify-email",
    {
      method: "POST",
      body: JSON.stringify({ token }),
    },
    { auth: false },
  );
}

export async function resendEmailVerification(
  email: string,
): Promise<MessageResponse> {
  return apiFetch<MessageResponse>(
    "/users/resend-verification",
    {
      method: "POST",
      body: JSON.stringify({ email }),
    },
    { auth: false },
  );
}

export async function requestPasswordRecovery(
  email: string,
): Promise<MessageResponse> {
  return apiFetch<MessageResponse>(
    `/password-recovery/${encodeURIComponent(email)}`,
    { method: "POST" },
    { auth: false },
  );
}

export async function resetPassword(
  token: string,
  newPassword: string,
): Promise<MessageResponse> {
  return apiFetch<MessageResponse>(
    "/reset-password/",
    {
      method: "POST",
      body: JSON.stringify({
        token,
        new_password: newPassword,
      }),
    },
    { auth: false },
  );
}

export function persistUser(user: UserPublic): void {
  if (typeof window === "undefined") {
    return;
  }

  window.sessionStorage.setItem(USER_STORAGE_KEY, JSON.stringify(user));
  window.localStorage.removeItem(USER_STORAGE_KEY);
}

export function logout(): void {
  // Demo storage only. Production should consider httpOnly cookies or a refresh-token flow.
  clearAuthStorage();
}
