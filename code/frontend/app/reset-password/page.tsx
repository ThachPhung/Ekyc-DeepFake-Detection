"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { AuthLayout } from "@/components/auth/AuthLayout";
import { useLanguage } from "@/contexts/LanguageContext";
import { resetPassword } from "@/services/auth.service";
import { ArrowLeft, CheckCircle2, Eye, EyeOff, LockKeyhole } from "lucide-react";
import { FormEvent, Suspense, useState } from "react";

function ResetPasswordContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { t } = useLanguage();
  const token = searchParams.get("token") ?? "";
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [errorKey, setErrorKey] = useState("");
  const [messageKey, setMessageKey] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrorKey("");
    setMessageKey("");

    if (!token) {
      setErrorKey("auth.resetPassword.errors.missingToken");
      return;
    }

    if (password.length < 8) {
      setErrorKey("auth.resetPassword.errors.passwordTooShort");
      return;
    }

    if (password !== confirmPassword) {
      setErrorKey("auth.resetPassword.errors.passwordMismatch");
      return;
    }

    setIsSubmitting(true);

    try {
      await resetPassword(token, password);
      setMessageKey("auth.resetPassword.messages.updated");
      window.setTimeout(() => router.replace("/login"), 1400);
    } catch {
      setErrorKey("auth.resetPassword.errors.invalidToken");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <AuthLayout
      cardTitle={t("auth.resetPassword.cardTitle")}
      eyebrow={t("auth.resetPassword.eyebrow")}
      heading={t("auth.resetPassword.heading")}
      subheading={t("auth.resetPassword.subheading")}
    >
      <form className="space-y-5" onSubmit={handleSubmit}>
        <div>
          <label className="form-label" htmlFor="new-password">
            {t("auth.resetPassword.newPasswordLabel")}
          </label>
          <div className="input-shell">
            <LockKeyhole size={18} aria-hidden="true" />
            <input
              autoComplete="new-password"
              id="new-password"
              onChange={(event) => setPassword(event.target.value)}
              placeholder={t("auth.resetPassword.newPasswordPlaceholder")}
              type={showPassword ? "text" : "password"}
              value={password}
            />
            <button
              aria-label={
                showPassword
                  ? t("auth.resetPassword.hidePassword")
                  : t("auth.resetPassword.showPassword")
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
          <label className="form-label" htmlFor="confirm-new-password">
            {t("auth.resetPassword.confirmPasswordLabel")}
          </label>
          <div className="input-shell">
            <LockKeyhole size={18} aria-hidden="true" />
            <input
              autoComplete="new-password"
              id="confirm-new-password"
              onChange={(event) => setConfirmPassword(event.target.value)}
              placeholder={t("auth.resetPassword.confirmPasswordPlaceholder")}
              type={showConfirmPassword ? "text" : "password"}
              value={confirmPassword}
            />
            <button
              aria-label={
                showConfirmPassword
                  ? t("auth.resetPassword.hideConfirmPassword")
                  : t("auth.resetPassword.showConfirmPassword")
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

        {errorKey ? (
          <p className="rounded-lg border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm font-semibold text-rose-100">
            {t(errorKey)}
          </p>
        ) : null}

        {messageKey ? (
          <p className="rounded-lg border border-emerald-300/30 bg-emerald-400/10 px-4 py-3 text-sm font-semibold text-emerald-100">
            <CheckCircle2 className="mr-2 inline" size={18} aria-hidden="true" />
            {t(messageKey)}
          </p>
        ) : null}

        <button
          className="primary-button w-full disabled:cursor-not-allowed disabled:opacity-60"
          disabled={isSubmitting}
          type="submit"
        >
          {isSubmitting
            ? t("auth.resetPassword.updating")
            : t("auth.resetPassword.submit")}
        </button>
      </form>

      <Link className="secondary-button w-full justify-center" href="/login">
        <ArrowLeft size={18} aria-hidden="true" />
        {t("auth.resetPassword.backToLogin")}
      </Link>
    </AuthLayout>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={null}>
      <ResetPasswordContent />
    </Suspense>
  );
}
