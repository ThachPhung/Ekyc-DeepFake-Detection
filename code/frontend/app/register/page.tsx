"use client";

import Link from "next/link";
import { AuthLayout } from "@/components/auth/AuthLayout";
import { useAuth } from "@/contexts/AuthContext";
import { useLanguage } from "@/contexts/LanguageContext";
import { ApiError } from "@/lib/api";
import { Eye, EyeOff, LockKeyhole, Mail, User } from "lucide-react";
import { FormEvent, useState } from "react";

export default function RegisterPage() {
  const { register } = useAuth();
  const { t } = useLanguage();
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [acceptedTerms, setAcceptedTerms] = useState(false);
  const [errorKey, setErrorKey] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrorKey("");

    if (!username.trim() || !email.trim() || !password || !confirmPassword) {
      setErrorKey("auth.register.errors.missingFields");
      return;
    }

    if (password.length < 8) {
      setErrorKey("auth.register.errors.passwordTooShort");
      return;
    }

    if (password !== confirmPassword) {
      setErrorKey("auth.register.errors.passwordMismatch");
      return;
    }

    if (!acceptedTerms) {
      setErrorKey("auth.register.errors.termsRequired");
      return;
    }

    setIsSubmitting(true);

    try {
      await register(username.trim(), email.trim(), password);
    } catch (caughtError) {
      if (caughtError instanceof ApiError && caughtError.status === 400) {
        setErrorKey("auth.register.errors.emailTaken");
      } else {
        setErrorKey("auth.register.errors.createFailed");
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <AuthLayout
      cardTitle={t("auth.register.cardTitle")}
      heading={t("auth.register.heading")}
      subheading={t("auth.register.subheading")}
    >
      <form className="space-y-4" onSubmit={handleSubmit}>
        <div>
          <label className="form-label" htmlFor="name">
            {t("auth.register.usernameLabel")}
          </label>
          <div className="input-shell">
            <User size={18} aria-hidden="true" />
            <input
              autoComplete="username"
              id="name"
              onChange={(event) => setUsername(event.target.value)}
              placeholder={t("auth.register.usernamePlaceholder")}
              type="text"
              value={username}
            />
          </div>
        </div>
        <div>
          <label className="form-label" htmlFor="register-email">
            {t("auth.register.emailLabel")}
          </label>
          <div className="input-shell">
            <Mail size={18} aria-hidden="true" />
            <input
              autoComplete="email"
              id="register-email"
              onChange={(event) => setEmail(event.target.value)}
              placeholder={t("auth.register.emailPlaceholder")}
              type="email"
              value={email}
            />
          </div>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="form-label" htmlFor="register-password">
              {t("auth.register.passwordLabel")}
            </label>
            <div className="input-shell">
              <LockKeyhole size={18} aria-hidden="true" />
              <input
                autoComplete="new-password"
                id="register-password"
                onChange={(event) => setPassword(event.target.value)}
                placeholder={t("auth.register.passwordPlaceholder")}
                type={showPassword ? "text" : "password"}
                value={password}
              />
              <button
                aria-label={
                  showPassword
                    ? t("auth.register.hidePassword")
                    : t("auth.register.showPassword")
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
          <div>
            <label className="form-label" htmlFor="confirm-password">
              {t("auth.register.confirmPasswordLabel")}
            </label>
            <div className="input-shell">
              <LockKeyhole size={18} aria-hidden="true" />
              <input
                autoComplete="new-password"
                id="confirm-password"
                onChange={(event) => setConfirmPassword(event.target.value)}
                placeholder={t("auth.register.confirmPasswordPlaceholder")}
                type={showConfirmPassword ? "text" : "password"}
                value={confirmPassword}
              />
              <button
                aria-label={
                  showConfirmPassword
                    ? t("auth.register.hideConfirmPassword")
                    : t("auth.register.showConfirmPassword")
                }
                className="inline-flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-md text-slate-300 transition hover:bg-white/10 hover:text-cyan-200"
                onClick={() => setShowConfirmPassword((current) => !current)}
                type="button"
              >
                {showConfirmPassword ? (
                  <EyeOff size={18} aria-hidden="true" />
                ) : (
                  <Eye size={18} aria-hidden="true" />
                )}
              </button>
            </div>
          </div>
        </div>
        <label className="flex items-start gap-3 text-sm leading-6 text-slate-300">
          <input
            checked={acceptedTerms}
            className="mt-1 accent-violet-500"
            onChange={(event) => setAcceptedTerms(event.target.checked)}
            type="checkbox"
          />
          {t("auth.register.terms")}
        </label>
        {errorKey ? (
          <p className="rounded-lg border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm font-semibold text-rose-100">
            {t(errorKey)}
          </p>
        ) : null}
        <button
          className="primary-button w-full disabled:cursor-not-allowed disabled:opacity-60"
          disabled={isSubmitting}
          type="submit"
        >
          {isSubmitting ? t("auth.register.creating") : t("auth.register.submit")}
          <span aria-hidden="true">-&gt;</span>
        </button>
      </form>

      <div className="grid gap-3 sm:grid-cols-2">
        <Link className="secondary-button justify-center" href="/login">
          {t("auth.register.backToLogin")}
        </Link>
        <Link className="secondary-button justify-center" href="/ekyc">
          {t("auth.register.continueEkyc")}
        </Link>
      </div>
    </AuthLayout>
  );
}
