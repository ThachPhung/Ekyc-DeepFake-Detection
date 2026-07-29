"use client";

import Link from "next/link";
import { AuthLayout } from "@/components/auth/AuthLayout";
import { useLanguage } from "@/contexts/LanguageContext";
import { requestPasswordRecovery } from "@/services/auth.service";
import { ArrowLeft, Mail, Send } from "lucide-react";
import { FormEvent, useState } from "react";

export default function ForgotPasswordPage() {
  const { t } = useLanguage();
  const [email, setEmail] = useState("");
  const [errorKey, setErrorKey] = useState("");
  const [messageKey, setMessageKey] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrorKey("");
    setMessageKey("");

    const submittedEmail = email.trim();

    if (!submittedEmail) {
      setErrorKey("auth.forgotPassword.errors.missingEmail");
      return;
    }

    setIsSubmitting(true);

    try {
      await requestPasswordRecovery(submittedEmail);
      setMessageKey("auth.forgotPassword.messages.sent");
    } catch {
      setErrorKey("auth.forgotPassword.errors.sendFailed");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <AuthLayout
      cardTitle={t("auth.forgotPassword.cardTitle")}
      eyebrow={t("auth.forgotPassword.eyebrow")}
      heading={t("auth.forgotPassword.heading")}
      subheading={t("auth.forgotPassword.subheading")}
    >
      <form className="space-y-5" onSubmit={handleSubmit}>
        <div>
          <label className="form-label" htmlFor="recovery-email">
            {t("auth.forgotPassword.emailLabel")}
          </label>
          <div className="input-shell">
            <Mail size={18} aria-hidden="true" />
            <input
              autoComplete="email"
              id="recovery-email"
              onChange={(event) => setEmail(event.target.value)}
              placeholder={t("auth.forgotPassword.emailPlaceholder")}
              type="email"
              value={email}
            />
          </div>
        </div>

        {errorKey ? (
          <p className="rounded-lg border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm font-semibold text-rose-100">
            {t(errorKey)}
          </p>
        ) : null}

        {messageKey ? (
          <p className="rounded-lg border border-emerald-300/30 bg-emerald-400/10 px-4 py-3 text-sm font-semibold text-emerald-100">
            {t(messageKey)}
          </p>
        ) : null}

        <button
          className="primary-button w-full disabled:cursor-not-allowed disabled:opacity-60"
          disabled={isSubmitting}
          type="submit"
        >
          <Send size={18} aria-hidden="true" />
          {isSubmitting
            ? t("auth.forgotPassword.sending")
            : t("auth.forgotPassword.submit")}
        </button>
      </form>

      <Link className="secondary-button w-full justify-center" href="/login">
        <ArrowLeft size={18} aria-hidden="true" />
        {t("auth.forgotPassword.backToLogin")}
      </Link>
    </AuthLayout>
  );
}
