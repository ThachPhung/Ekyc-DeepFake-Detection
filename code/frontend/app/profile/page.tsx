"use client";

import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { AppHeader } from "@/components/site/AppHeader";
import { useAuth } from "@/contexts/AuthContext";
import { useLanguage } from "@/contexts/LanguageContext";
import {
  getMyVerifiedIdentity,
  type MyVerifiedIdentityResponse,
} from "@/services/ekyc.service";
import { persistUser, updateMe } from "@/services/auth.service";
import { CheckCircle2, IdCard, Loader2, Pencil, Save, UserRound, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

const USERNAME_MAX_LENGTH = 59;

export default function ProfilePage() {
  const { setUser, user } = useAuth();
  const { locale, t } = useLanguage();
  const [identity, setIdentity] = useState<MyVerifiedIdentityResponse | null>(null);
  const [isEditingUsername, setIsEditingUsername] = useState(false);
  const [isSavingUsername, setIsSavingUsername] = useState(false);
  const [usernameDraft, setUsernameDraft] = useState("");
  const [usernameError, setUsernameError] = useState<string | null>(null);
  const [usernameSuccess, setUsernameSuccess] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;

    async function loadIdentity() {
      try {
        const response = await getMyVerifiedIdentity({ reveal: true });
        if (isMounted) {
          setIdentity(response.is_verified ? response : null);
        }
      } catch {
        if (isMounted) {
          setIdentity(null);
        }
      }
    }

    loadIdentity();

    return () => {
      isMounted = false;
    };
  }, []);

  const username = user?.full_name || t("profile.defaultUser");
  const trimmedUsernameDraft = usernameDraft.trim();
  const isUsernameUnchanged = trimmedUsernameDraft === (user?.full_name ?? "").trim();

  async function handleSaveUsername() {
    setUsernameError(null);
    setUsernameSuccess(null);

    if (!trimmedUsernameDraft) {
      setUsernameError(t("profile.usernameRequired"));
      return;
    }

    if (trimmedUsernameDraft.length > USERNAME_MAX_LENGTH) {
      setUsernameError(
        t("profile.usernameTooLong", { max: USERNAME_MAX_LENGTH }),
      );
      return;
    }

    try {
      setIsSavingUsername(true);
      const updatedUser = await updateMe({ full_name: trimmedUsernameDraft });
      persistUser(updatedUser);
      setUser(updatedUser);
      setIsEditingUsername(false);
      setUsernameSuccess(t("profile.usernameUpdated"));
    } catch (error) {
      setUsernameError(formatErrorMessage(error, t("profile.usernameUpdateFailed")));
    } finally {
      setIsSavingUsername(false);
    }
  }

  function handleCancelUsernameEdit() {
    setUsernameDraft(user?.full_name ?? "");
    setUsernameError(null);
    setIsEditingUsername(false);
  }

  const identityFields = useMemo(
    () => [
      {
        label: t("ekyc.fields.documentType"),
        value: identity?.document_type
          ? getDocumentTypeLabel(identity.document_type, t)
          : null,
      },
      { label: t("ekyc.fields.documentNumber"), value: identity?.identity_number },
      { label: t("ekyc.fields.fullName"), value: identity?.full_name },
      { label: t("ekyc.fields.dateOfBirth"), value: identity?.birth_date },
      { label: t("ekyc.fields.gender"), value: identity?.gender },
      { label: t("ekyc.fields.nationality"), value: identity?.nationality },
      { label: t("profile.fields.placeOfOrigin"), value: identity?.place_of_origin },
      {
        label: t("profile.fields.placeOfResidence"),
        value: identity?.place_of_residence || identity?.address,
      },
      { label: t("ekyc.fields.issuedDate"), value: identity?.issued_date },
      { label: t("profile.fields.issuedPlace"), value: identity?.issue_place },
      { label: t("ekyc.fields.expiryDate"), value: identity?.expired_date },
      {
        label: t("profile.fields.verifiedAt"),
        value: identity?.verified_at
          ? formatDateTime(identity.verified_at, locale === "vi" ? "vi-VN" : "en-GB")
          : null,
      },
    ],
    [identity, locale, t],
  );

  return (
    <ProtectedRoute>
      <main className="min-h-screen overflow-hidden bg-[#030712] text-white">
        <div className="vintrade-bg" />
        <AppHeader />
        <section className="relative z-10 mx-auto max-w-[1480px] px-4 py-10 sm:px-6 lg:px-8">
          <div className="mb-6">
            <h1 className="text-4xl font-black tracking-normal sm:text-5xl">
              {t("profile.title")}
            </h1>
            <p className="mt-3 max-w-2xl text-slate-300">
              {t("profile.description")}
            </p>
          </div>

          <div className="glass-panel p-6">
            <div className="mb-6 flex items-center gap-4">
              <div className="grid h-14 w-14 place-items-center rounded-lg border border-cyan-300/30 bg-cyan-400/10 text-cyan-200">
                <UserRound size={26} />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-bold text-slate-400">
                  {t("profile.personalProfile")}
                </p>
                <div className="mt-1 flex flex-col gap-3 lg:flex-row lg:items-center">
                  <h2 className="break-words text-2xl font-black">
                    {username}
                  </h2>
                  {!isEditingUsername ? (
                    <button
                      type="button"
                      className="inline-flex h-10 w-fit items-center gap-2 rounded-lg border border-cyan-300/30 bg-cyan-400/10 px-3 text-sm font-black text-cyan-100 transition hover:border-cyan-200/70 hover:bg-cyan-400/20"
                      onClick={() => {
                        setUsernameDraft(user?.full_name ?? "");
                        setUsernameError(null);
                        setUsernameSuccess(null);
                        setIsEditingUsername(true);
                      }}
                    >
                      <Pencil size={16} />
                      {t("profile.editUsername")}
                    </button>
                  ) : null}
                </div>
              </div>
            </div>

            {isEditingUsername ? (
              <div className="mb-5 rounded-lg border border-white/10 bg-slate-950/40 p-4">
                <label
                  className="text-xs font-black uppercase text-slate-500"
                  htmlFor="profile-username"
                >
                  {t("profile.username")}
                </label>
                <div className="mt-2 flex flex-col gap-3 lg:flex-row lg:items-start">
                  <div className="min-w-0 flex-1">
                    <input
                      id="profile-username"
                      type="text"
                      className="h-12 w-full rounded-lg border border-white/10 bg-slate-950 px-4 text-sm font-bold text-white outline-none transition placeholder:text-slate-600 focus:border-cyan-300/70"
                      maxLength={USERNAME_MAX_LENGTH}
                      value={usernameDraft}
                      onChange={(event) => {
                        setUsernameDraft(event.target.value);
                        setUsernameError(null);
                        setUsernameSuccess(null);
                      }}
                    />
                    <div className="mt-2 flex items-center justify-between gap-3 text-xs font-semibold text-slate-500">
                      <span>{t("profile.usernameHelper", { max: USERNAME_MAX_LENGTH })}</span>
                      <span>
                        {trimmedUsernameDraft.length}/{USERNAME_MAX_LENGTH}
                      </span>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      className="inline-flex h-12 items-center justify-center gap-2 rounded-lg border border-emerald-300/30 bg-emerald-400/10 px-4 text-sm font-black text-emerald-100 transition hover:border-emerald-200/70 hover:bg-emerald-400/20 disabled:cursor-not-allowed disabled:opacity-60"
                      disabled={isSavingUsername || !trimmedUsernameDraft || isUsernameUnchanged}
                      onClick={handleSaveUsername}
                    >
                      {isSavingUsername ? (
                        <Loader2 className="animate-spin" size={16} />
                      ) : (
                        <Save size={16} />
                      )}
                      {t("profile.saveUsername")}
                    </button>
                    <button
                      type="button"
                      className="inline-flex h-12 items-center justify-center gap-2 rounded-lg border border-white/10 bg-white/5 px-4 text-sm font-black text-slate-200 transition hover:border-white/25 hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-60"
                      disabled={isSavingUsername}
                      onClick={handleCancelUsernameEdit}
                    >
                      <X size={16} />
                      {t("profile.cancelEdit")}
                    </button>
                  </div>
                </div>
                {usernameError ? (
                  <p className="mt-3 text-sm font-semibold text-rose-200">
                    {usernameError}
                  </p>
                ) : null}
              </div>
            ) : null}

            {usernameSuccess ? (
              <p className="mb-5 rounded-lg border border-emerald-300/30 bg-emerald-400/10 px-4 py-3 text-sm font-semibold text-emerald-100">
                {usernameSuccess}
              </p>
            ) : null}

            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <ProfileField
                label={t("profile.username")}
                value={username}
                emptyLabel={t("profile.notProvided")}
              />
              <ProfileField
                label={t("profile.email")}
                value={user?.email}
                emptyLabel={t("profile.notProvided")}
              />
              <ProfileField
                label={t("profile.phoneNumber")}
                value={null}
                emptyLabel={t("profile.notProvided")}
              />
              <ProfileField
                label={t("profile.estimatedAssets")}
                value="$0.00"
                emptyLabel={t("profile.notProvided")}
              />
            </div>
          </div>

          {identity ? (
            <div className="mt-4 glass-panel p-6">
            <div className="mb-6 flex items-center justify-between gap-4">
              <div className="flex items-center gap-4">
                <div className="grid h-14 w-14 place-items-center rounded-lg border border-emerald-300/30 bg-emerald-400/10 text-emerald-200">
                  <IdCard size={26} />
                </div>
                <div>
                  <p className="text-sm font-bold text-slate-400">
                    {t("profile.identityProfile")}
                  </p>
                  <h2 className="mt-1 text-2xl font-black">
                    {t("profile.verifiedInformation")}
                  </h2>
                </div>
              </div>
              <div className="flex items-center gap-2 rounded-lg border border-white/10 bg-slate-950/40 px-3 py-2 text-sm font-black text-slate-200">
                <CheckCircle2 size={17} className="text-emerald-300" />
                {t("profile.verified")}
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {identityFields.map((field) => (
                <ProfileField
                  key={field.label}
                  label={field.label}
                  value={field.value}
                  emptyLabel={t("profile.notProvided")}
                />
              ))}
            </div>
            </div>
          ) : null}
        </section>
      </main>
    </ProtectedRoute>
  );
}

function ProfileField({
  emptyLabel,
  label,
  value,
}: {
  emptyLabel: string;
  label: string;
  value?: string | null;
}) {
  return (
    <div className="rounded-lg border border-white/10 bg-slate-950/50 p-4">
      <p className="text-xs font-black uppercase text-slate-500">{label}</p>
      <p className="mt-2 break-words text-sm font-bold text-slate-100">
        {value || emptyLabel}
      </p>
    </div>
  );
}

function getDocumentTypeLabel(documentType: string, t: (key: string) => string) {
  if (documentType === "CCCD") {
    return t("ekyc.documentTypes.CCCD.shortLabel");
  }
  if (documentType === "GPLX") {
    return t("ekyc.documentTypes.GPLX.shortLabel");
  }
  if (documentType === "HOCHIEU") {
    return t("ekyc.documentTypes.HOCHIEU.shortLabel");
  }
  return documentType;
}

function formatDateTime(value: string, locale: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString(locale, {
    dateStyle: "short",
    timeStyle: "medium",
  });
}

function formatErrorMessage(error: unknown, fallback: string) {
  if (error instanceof Error && error.message) {
    return error.message;
  }

  return fallback;
}
