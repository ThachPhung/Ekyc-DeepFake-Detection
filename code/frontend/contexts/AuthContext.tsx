"use client";

import { useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { getStoredToken } from "@/lib/api";
import * as authService from "@/services/auth.service";
import type { UserPublic } from "@/services/auth.service";

type AuthContextValue = {
  user: UserPublic | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (username: string, email: string, password: string) => Promise<void>;
  logout: () => void;
  refreshMe: () => Promise<UserPublic | null>;
  setUser: (user: UserPublic | null) => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

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

function getPostAuthRedirectPath(): string {
  return "/trading";
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<UserPublic | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const doLogout = useCallback(() => {
    authService.logout();
    setToken(null);
    setUser(null);
    router.replace("/login");
  }, [router]);

  const refreshMe = useCallback(async () => {
    const storedToken = getStoredToken();

    if (!storedToken) {
      setToken(null);
      setUser(null);
      return null;
    }

    setToken(storedToken);

    try {
      const currentUser = await authService.getMe();
      authService.persistUser(currentUser);
      setUser(currentUser);
      return currentUser;
    } catch {
      authService.logout();
      setToken(null);
      setUser(null);
      return null;
    }
  }, []);

  useEffect(() => {
    let isMounted = true;

    async function bootstrapAuth() {
      const storedToken = getStoredToken();

      if (!storedToken) {
        if (isMounted) {
          setIsLoading(false);
        }
        return;
      }

      const currentUser = await refreshMe();

      if (isMounted) {
        setIsLoading(false);

        const currentPath =
          typeof window === "undefined" ? "/" : window.location.pathname;

        if (!currentUser && !publicPaths.includes(currentPath)) {
          router.replace("/login");
        }
      }
    }

    bootstrapAuth();

    return () => {
      isMounted = false;
    };
  }, [refreshMe, router]);

  const login = useCallback(
    async (email: string, password: string) => {
      const tokenResponse = await authService.login(email, password);
      setToken(tokenResponse.access_token);

      const currentUser = await authService.getMe();
      authService.persistUser(currentUser);
      setUser(currentUser);
      router.replace(getPostAuthRedirectPath());
    },
    [router],
  );

  const register = useCallback(
    async (username: string, email: string, password: string) => {
      await authService.register({
        email,
        password,
        full_name: username,
      });
      router.replace(`/verify-email?email=${encodeURIComponent(email)}`);
    },
    [router],
  );

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      token,
      isAuthenticated: Boolean(user && token),
      isLoading,
      login,
      register,
      logout: doLogout,
      refreshMe,
      setUser,
    }),
    [doLogout, isLoading, login, refreshMe, register, token, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);

  if (!context) {
    throw new Error("useAuth must be used inside AuthProvider");
  }

  return context;
}
