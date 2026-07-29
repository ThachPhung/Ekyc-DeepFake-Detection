"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { AuthLayout } from "@/components/auth/AuthLayout";
import { useLanguage } from "@/contexts/LanguageContext";
import {
  resendEmailVerification,
  verifyEmail,
} from "@/services/auth.service";
import {
  ArrowLeft,
  CheckCircle2,
  MailCheck,
  RefreshCw,
  XCircle,
} from "lucide-react";
import { Suspense, useEffect, useState } from "react";

type VerificationState = "idle" | "verifying" | "success" | "error";

function VerifyEmailContent() {
  const searchParams = useSearchParams();
  const { t } = useLanguage();
  const token = searchParams.get("token") ?? "";
  const email = searchParams.get("email") ?? "";
  const [status, setStatus] = useState<VerificationState>(
    token ? "verifying" : "idle",
  );
  const [messageKey, setMessageKey] = useState(
    token
      ? "auth.verifyEmail.messages.verifying"
      : "auth.verifyEmail.messages.checkInbox",
  );
  const [isResending, setIsResending] = useState(false);

  useEffect(() => {
    if (!token) {
      return;
    }

    let isMounted = true;

    async function confirmEmail() {
      try {
        await verifyEmail(token);

        if (isMounted) {
          setStatus("success");
          setMessageKey("auth.verifyEmail.messages.success");
        }
      } catch {
        if (isMounted) {
          setStatus("error");
          setMessageKey("auth.verifyEmail.messages.invalid");
        }
      }
    }

    confirmEmail();

    return () => {
      isMounted = false;
    };
  }, [token]);

  const isSuccess = status === "success";
  const isError = status === "error";
  const canResend = Boolean(email) && !isSuccess;

  async function handleResendVerification() {
    if (!email || isResending) {
      return;
    }

    setIsResending(true);
    setStatus("idle");

    try {
      await resendEmailVerification(email);
      setMessageKey("auth.verifyEmail.messages.resent");
    } catch {
      setStatus("error");
      setMessageKey("auth.verifyEmail.messages.resendFailed");
    } finally {
      setIsResending(false);
    }
  }

  return (
    <AuthLayout
      cardTitle={t(
        token
          ? "auth.verifyEmail.cardTitleWithToken"
          : "auth.verifyEmail.cardTitleNoToken",
      )}
      eyebrow={t("auth.verifyEmail.eyebrow")}
      heading={t(
        token
          ? "auth.verifyEmail.headingWithToken"
          : "auth.verifyEmail.headingNoToken",
      )}
      subheading={t(
        token
          ? "auth.verifyEmail.subheadingWithToken"
          : "auth.verifyEmail.subheadingNoToken",
      )}
    >
      <div
        className={`rounded-lg border px-4 py-5 text-center ${
          isSuccess
            ? "border-emerald-300/30 bg-emerald-400/10 text-emerald-100"
            : isError
              ? "border-rose-400/30 bg-rose-500/10 text-rose-100"
              : "border-cyan-300/25 bg-cyan-300/10 text-cyan-100"
        }`}
      >
        <div className="mx-auto mb-3 grid h-12 w-12 place-items-center rounded-lg bg-white/10">
          {isSuccess ? (
            <CheckCircle2 size={28} aria-hidden="true" />
          ) : isError ? (
            <XCircle size={28} aria-hidden="true" />
          ) : (
            <MailCheck size={28} aria-hidden="true" />
          )}
        </div>
        <p className="text-sm font-semibold">{t(messageKey)}</p>
        {email ? (
          <p className="mt-2 break-all text-xs text-slate-300">{email}</p>
        ) : null}
      </div>

      {canResend ? (
        <button
          className="primary-button w-full justify-center disabled:cursor-not-allowed disabled:opacity-60"
          disabled={isResending}
          onClick={handleResendVerification}
          type="button"
        >
          <RefreshCw size={18} aria-hidden="true" />
          {isResending
            ? t("auth.verifyEmail.sending")
            : t("auth.verifyEmail.resend")}
        </button>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2">
        <Link className="secondary-button justify-center" href="/login">
          <ArrowLeft size={18} aria-hidden="true" />
          {t("auth.verifyEmail.login")}
        </Link>
        <Link className="primary-button justify-center" href="/forgot-password">
          {t("auth.verifyEmail.passwordHelp")}
        </Link>
      </div>
    </AuthLayout>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={null}>
      <VerifyEmailContent />
    </Suspense>
  );
}
