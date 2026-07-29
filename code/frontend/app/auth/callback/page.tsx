"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AuthLayout } from "@/components/auth/AuthLayout";
import { useAuth } from "@/contexts/AuthContext";
import { useLanguage } from "@/contexts/LanguageContext";
import { setStoredToken } from "@/lib/api";

const providerLabels: Record<string, string> = {
  google: "Google",
  facebook: "Facebook",
  microsoft: "Microsoft",
};

export default function AuthCallbackPage() {
  const router = useRouter();
  const { refreshMe } = useAuth();
  const { t } = useLanguage();
  const [messageKey, setMessageKey] = useState("auth.callback.completing");
  const [providerLabel, setProviderLabel] = useState("");

  useEffect(() => {
    let isMounted = true;

    async function completeOAuthLogin() {
      const params = new URLSearchParams(window.location.search);
      const token = params.get("token");
      const provider = params.get("provider");
      const oauthError = params.get("oauth_error");

      if (oauthError) {
        router.replace(`/login?oauth_error=${encodeURIComponent(oauthError)}`);
        return;
      }

      if (!token) {
        router.replace("/login?oauth_error=oauth_login_failed");
        return;
      }

      setStoredToken(token);

      if (isMounted && provider) {
        setMessageKey("auth.callback.verifyingProvider");
        setProviderLabel(providerLabels[provider] ?? provider);
      }

      try {
        await refreshMe();
        router.replace("/trading");
      } catch {
        router.replace("/login?oauth_error=oauth_login_failed");
      }
    }

    completeOAuthLogin();

    return () => {
      isMounted = false;
    };
  }, [refreshMe, router]);

  return (
    <AuthLayout
      heading={t("auth.callback.heading")}
      subheading={t("auth.callback.subheading")}
    >
      <p className="rounded-lg border border-cyan-300/20 bg-cyan-300/10 px-4 py-3 text-sm font-semibold text-cyan-100">
        {t(
          messageKey,
          providerLabel ? { provider: providerLabel } : undefined,
        )}
      </p>
    </AuthLayout>
  );
}
