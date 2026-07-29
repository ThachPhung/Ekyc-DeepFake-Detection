"use client";

import Link from "next/link";
import Image from "next/image";
import { AuthLayout } from "@/components/auth/AuthLayout";
import { useAuth } from "@/contexts/AuthContext";
import { useLanguage } from "@/contexts/LanguageContext";
import { getOAuthLoginUrl, type OAuthProvider } from "@/services/auth.service";
import { Eye, EyeOff, LockKeyhole, Mail } from "lucide-react";
import { FormEvent, useState } from "react";

const socialProviders: { name: string; provider: OAuthProvider; icon: string }[] = [
  { name: "Google", provider: "google", icon: "/icons/google.png" },
];

const oauthErrorMessageKeys: Record<string, string> = {
  provider_not_configured: "auth.login.errors.providerNotConfigured",
  invalid_state: "auth.login.errors.invalidState",
  expired_state: "auth.login.errors.expiredState",
  provider_denied: "auth.login.errors.providerDenied",
  missing_code: "auth.login.errors.missingCode",
  profile_missing_email: "auth.login.errors.profileMissingEmail",
  inactive_user: "auth.login.errors.inactiveUser",
  oauth_login_failed: "auth.login.errors.oauthLoginFailed",
};

function getInitialOAuthErrorKey(): string {
  if (typeof window === "undefined") {
    return "";
  }

  const oauthError = new URLSearchParams(window.location.search).get("oauth_error");
  return oauthError
    ? oauthErrorMessageKeys[oauthError] ??
        oauthErrorMessageKeys.oauth_login_failed
    : "";
}

export default function LoginPage() {
  const { login } = useAuth();
  const { t } = useLanguage();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [errorKey, setErrorKey] = useState(getInitialOAuthErrorKey);
  const [isSubmitting, setIsSubmitting] = useState(false);

  function handleSocialLogin(provider: OAuthProvider) {
    setErrorKey("");
    window.location.assign(getOAuthLoginUrl(provider));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrorKey("");

    const formData = new FormData(event.currentTarget);
    const submittedEmail = String(formData.get("email") ?? "").trim();
    const submittedPassword = String(formData.get("password") ?? "");

    if (!submittedEmail || !submittedPassword) {
      setErrorKey("auth.login.errors.missingCredentials");
      return;
    }

    setIsSubmitting(true);

    try {
      await login(submittedEmail, submittedPassword);
    } catch {
      setErrorKey("auth.login.errors.invalidCredentials");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <AuthLayout
      cardTitle={t("auth.layout.defaultSignInCardTitle")}
      eyebrow={t("auth.login.eyebrow")}
      heading={t("auth.login.heading")}
      subheading={t("auth.login.subheading")}
    >
      <form className="space-y-5" onSubmit={handleSubmit}>
        <div>
          <label className="form-label" htmlFor="email">
            {t("auth.login.emailLabel")}
          </label>
          <div className="input-shell">
            <Mail size={18} aria-hidden="true" />
            <input
              autoComplete="email"
              id="email"
              name="email"
              onChange={(event) => setEmail(event.target.value)}
              placeholder={t("auth.login.emailPlaceholder")}
              type="email"
              value={email}
            />
          </div>
        </div>
        <div>
          <label className="form-label" htmlFor="password">
            {t("auth.login.passwordLabel")}
          </label>
          <div className="input-shell">
            <LockKeyhole size={18} aria-hidden="true" />
            <input
              autoComplete="current-password"
              id="password"
              name="password"
              onChange={(event) => setPassword(event.target.value)}
              placeholder={t("auth.login.passwordPlaceholder")}
              type={showPassword ? "text" : "password"}
              value={password}
            />
            <button
              aria-label={
                showPassword
                  ? t("auth.login.hidePassword")
                  : t("auth.login.showPassword")
              }
              className="inline-flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-md text-slate-300 transition hover:bg-white/10 hover:text-cyan-200"
              onClick={() => setShowPassword((current) => !current)}
              type="button"
            >
              {showPassword ? (
                <EyeOff size={18} aria-hidden="true" />
              ) : (
                <Eye size={18} aria-hidden="true" />
              )}
            </button>
          </div>
        </div>
        {errorKey ? (
          <p className="rounded-lg border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm font-semibold text-rose-100">
            {t(errorKey)}
          </p>
        ) : null}
        <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-slate-300">
          <label className="inline-flex items-center gap-2">
            <input className="accent-violet-500" defaultChecked type="checkbox" />
            {t("auth.login.rememberMe")}
          </label>
          <Link
            className="text-cyan-300 transition hover:text-cyan-100"
            href="/forgot-password"
          >
            {t("auth.login.forgotPassword")}
          </Link>
        </div>
        <button
          className="primary-button w-full disabled:cursor-not-allowed disabled:opacity-60"
          disabled={isSubmitting}
          type="submit"
        >
          {isSubmitting ? t("auth.login.signingIn") : t("auth.login.submit")}
          <span aria-hidden="true">-&gt;</span>
        </button>
      </form>

      <div className="divider">
        <span />
        {t("auth.login.continueWith")}
        <span />
      </div>

      <div className="grid gap-3">
        {socialProviders.map((provider) => (
          <button
            className="social-button w-full justify-center"
            key={provider.name}
            onClick={() => handleSocialLogin(provider.provider)}
            type="button"
          >
            <span>
              <Image
                alt={`${provider.name} logo`}
                className="h-4 w-4 object-contain"
                height={16}
                src={provider.icon}
                width={16}
              />
            </span>
            {provider.name}
          </button>
        ))}
      </div>

      <p className="text-center text-sm text-slate-300">
        {t("auth.login.noAccount")}{" "}
        <Link className="font-semibold text-cyan-300 hover:text-cyan-100" href="/register">
          {t("auth.login.createAccount")}
        </Link>
      </p>
    </AuthLayout>
  );
}
