"use client";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export const BACKEND_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  API_BASE_URL.replace(/\/api\/v1\/?$/, "");

export const ACCESS_TOKEN_KEY = "vintrade_access_token";
export const USER_STORAGE_KEY = "vintrade_user";

const publicPaths = [
  "/",
  "/landing",
  "/markets",
  "/login",
  "/register",
  "/auth/callback",
  "/verify-email",
  "/forgot-password",
  "/reset-password",
];

export type ApiErrorPayload = {
  detail?: string;
  message?: string;
};

export class ApiError extends Error {
  status: number;
  payload: ApiErrorPayload | null;

  constructor(status: number, payload: ApiErrorPayload | null, fallback: string) {
    super(payload?.detail ?? payload?.message ?? fallback);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

export function getStoredToken(): string | null {
  if (typeof window === "undefined") {
    return null;
  }

  window.localStorage.removeItem(ACCESS_TOKEN_KEY);
  window.localStorage.removeItem(USER_STORAGE_KEY);

  return window.sessionStorage.getItem(ACCESS_TOKEN_KEY);
}

export function setStoredToken(token: string): void {
  window.sessionStorage.setItem(ACCESS_TOKEN_KEY, token);
  window.localStorage.removeItem(ACCESS_TOKEN_KEY);
  window.localStorage.removeItem(USER_STORAGE_KEY);
}

export function clearAuthStorage(): void {
  if (typeof window === "undefined") {
    return;
  }

  window.sessionStorage.removeItem(ACCESS_TOKEN_KEY);
  window.sessionStorage.removeItem(USER_STORAGE_KEY);
  window.localStorage.removeItem(ACCESS_TOKEN_KEY);
  window.localStorage.removeItem(USER_STORAGE_KEY);
}

function isProtectedBrowserPath(): boolean {
  if (typeof window === "undefined") {
    return false;
  }

  return !publicPaths.includes(window.location.pathname);
}

function handleUnauthorized(): void {
  clearAuthStorage();

  if (isProtectedBrowserPath()) {
    window.location.assign("/login");
  }
}

function buildUrl(path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }

  return `${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
  config: { auth?: boolean } = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  const body = options.body;

  if (body && !(body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set(
      "Content-Type",
      body instanceof URLSearchParams
        ? "application/x-www-form-urlencoded"
        : "application/json",
    );
  }

  if (config.auth) {
    const token = getStoredToken();

    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }
  }

  const response = await fetch(buildUrl(path), {
    ...options,
    headers,
  });

  if (response.status === 401 || response.status === 403) {
    handleUnauthorized();
  }

  if (!response.ok) {
    let payload: ApiErrorPayload | null = null;

    try {
      payload = (await response.json()) as ApiErrorPayload;
    } catch {
      payload = null;
    }

    throw new ApiError(response.status, payload, "Request failed");
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}
