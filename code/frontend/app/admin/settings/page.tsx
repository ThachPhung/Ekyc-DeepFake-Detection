"use client";

import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { AppHeader } from "@/components/site/AppHeader";
import { useAuth } from "@/contexts/AuthContext";
import { useLanguage } from "@/contexts/LanguageContext";
import { ApiError } from "@/lib/api";
import {
  getAdminSettings,
  updateAdminSettings,
  type AdminSettings,
} from "@/services/admin.service";
import {
  AlertTriangle,
  Bell,
  CheckCircle2,
  Loader2,
  RefreshCcw,
  Save,
  Server,
  Settings,
  TimerReset,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

function formatError(error: unknown) {
  if (error instanceof ApiError || error instanceof Error) {
    return error.message;
  }
  return "Unable to load admin settings.";
}

function sourceLabel(source: string | null | undefined, t: (key: string) => string) {
  return source === "database"
    ? t("admin.settings.sourceDatabase")
    : t("admin.settings.sourceEnvironment");
}

export default function AdminSettingsPage() {
  const { user } = useAuth();
  const { t } = useLanguage();
  const [settings, setSettings] = useState<AdminSettings | null>(null);
  const [timeoutMinutes, setTimeoutMinutes] = useState("5");
  const [notificationsEnabled, setNotificationsEnabled] = useState(true);
  const [errorMessage, setErrorMessage] = useState("");
  const [successMessage, setSuccessMessage] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  const loadSettings = useCallback(async () => {
    if (!user?.is_superuser) {
      return;
    }

    setIsLoading(true);
    setErrorMessage("");
    try {
      const response = await getAdminSettings();
      setSettings(response);
      setTimeoutMinutes(String(response.ekyc_processing_timeout_minutes));
      setNotificationsEnabled(response.user_notifications_enabled);
    } catch (error) {
      setErrorMessage(formatError(error));
    } finally {
      setIsLoading(false);
    }
  }, [user?.is_superuser]);

  useEffect(() => {
    void Promise.resolve().then(loadSettings);
  }, [loadSettings]);

  const parsedTimeout = Number(timeoutMinutes);
  const isTimeoutValid =
    Number.isInteger(parsedTimeout) && parsedTimeout >= 1 && parsedTimeout <= 240;

  const isDirty = useMemo(() => {
    if (!settings) {
      return false;
    }
    return (
      parsedTimeout !== settings.ekyc_processing_timeout_minutes ||
      notificationsEnabled !== settings.user_notifications_enabled
    );
  }, [notificationsEnabled, parsedTimeout, settings]);

  async function saveSettings() {
    if (!isTimeoutValid) {
      setErrorMessage(t("admin.settings.invalidTimeout"));
      return;
    }

    setIsSaving(true);
    setErrorMessage("");
    setSuccessMessage("");
    try {
      const response = await updateAdminSettings({
        ekyc_processing_timeout_minutes: parsedTimeout,
        user_notifications_enabled: notificationsEnabled,
      });
      setSettings(response);
      setTimeoutMinutes(String(response.ekyc_processing_timeout_minutes));
      setNotificationsEnabled(response.user_notifications_enabled);
      setSuccessMessage(t("admin.settings.saved"));
    } catch (error) {
      setErrorMessage(formatError(error));
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <ProtectedRoute>
      <main className="min-h-screen overflow-hidden bg-[#030712] text-white">
        <div className="vintrade-bg" />
        <AppHeader />

        <section className="relative z-10 mx-auto max-w-[1280px] px-4 py-8 sm:px-6 lg:px-8">
          {!user?.is_superuser ? (
            <div className="glass-panel mx-auto max-w-xl p-6 text-center">
              <AlertTriangle className="mx-auto text-rose-300" size={34} />
              <h1 className="mt-4 text-2xl font-black">
                {t("admin.common.accessDenied")}
              </h1>
              <p className="mt-2 text-sm text-slate-300">
                {t("admin.settings.deniedDescription")}
              </p>
            </div>
          ) : (
            <>
              <div className="mb-6 flex flex-col justify-between gap-4 lg:flex-row lg:items-end">
                <div>
                  <span className="micro-badge">
                    <span className="status-dot cyan" />
                    {t("admin.settings.badge")}
                  </span>
                  <h1 className="mt-4 text-4xl font-black tracking-normal sm:text-5xl">
                    {t("admin.settings.title")}
                  </h1>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    className="secondary-button"
                    disabled={isLoading || isSaving}
                    onClick={loadSettings}
                    type="button"
                  >
                    {isLoading ? (
                      <Loader2 className="animate-spin" size={16} />
                    ) : (
                      <RefreshCcw size={16} />
                    )}
                    {t("admin.common.refresh")}
                  </button>
                  <button
                    className="primary-button"
                    disabled={isSaving || !isDirty || !isTimeoutValid}
                    onClick={saveSettings}
                    type="button"
                  >
                    {isSaving ? (
                      <Loader2 className="animate-spin" size={16} />
                    ) : (
                      <Save size={16} />
                    )}
                    {t("admin.common.save")}
                  </button>
                </div>
              </div>

              {errorMessage ? (
                <div className="mb-4 rounded-lg border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm font-semibold text-rose-100">
                  {errorMessage}
                </div>
              ) : null}

              {successMessage ? (
                <div className="mb-4 flex items-center gap-2 rounded-lg border border-emerald-400/30 bg-emerald-500/10 px-4 py-3 text-sm font-semibold text-emerald-100">
                  <CheckCircle2 size={16} />
                  {successMessage}
                </div>
              ) : null}

              {isLoading && !settings ? (
                <div className="glass-panel p-6 text-sm font-bold text-slate-300">
                  {t("admin.settings.loading")}
                </div>
              ) : settings ? (
                <div className="grid gap-5 xl:grid-cols-[1fr_0.85fr]">
                  <section className="glass-panel overflow-hidden">
                    <div className="flex items-center justify-between border-b border-white/10 p-5">
                      <div>
                        <h2 className="text-xl font-black">
                          {t("admin.settings.editable")}
                        </h2>
                        <p className="mt-1 text-sm font-semibold text-slate-400">
                          {t("admin.settings.editableDescription")}
                        </p>
                      </div>
                      <Settings className="text-cyan-200" size={24} />
                    </div>

                    <div className="grid gap-4 p-5">
                      <div className="rounded-lg border border-white/10 bg-white/[0.03] p-4">
                        <div className="mb-4 flex items-center justify-between gap-3">
                          <div className="flex items-center gap-3">
                            <span className="grid h-10 w-10 place-items-center rounded-lg bg-cyan-400/10 text-cyan-200">
                              <TimerReset size={19} />
                            </span>
                            <div>
                              <p className="font-black text-white">
                                {t("admin.settings.timeoutTitle")}
                              </p>
                              <p className="text-xs font-bold text-slate-500">
                                {sourceLabel(settings.ekyc_processing_timeout_source, t)}
                              </p>
                            </div>
                          </div>
                        </div>
                        <label
                          className="text-xs font-black uppercase tracking-[0.18em] text-slate-500"
                          htmlFor="ekyc-timeout"
                        >
                          {t("admin.settings.minutes")}
                        </label>
                        <input
                          className="mt-2 h-11 w-full rounded-lg border border-white/10 bg-[#07111f] px-3 text-sm font-bold text-white outline-none transition focus:border-cyan-300/60"
                          id="ekyc-timeout"
                          max={240}
                          min={1}
                          onChange={(event) => setTimeoutMinutes(event.target.value)}
                          step={1}
                          type="number"
                          value={timeoutMinutes}
                        />
                      </div>

                      <div className="rounded-lg border border-white/10 bg-white/[0.03] p-4">
                        <div className="flex items-center justify-between gap-4">
                          <div className="flex items-center gap-3">
                            <span className="grid h-10 w-10 place-items-center rounded-lg bg-cyan-400/10 text-cyan-200">
                              <Bell size={18} />
                            </span>
                            <div>
                              <p className="font-black text-white">
                                {t("admin.settings.userNotifications")}
                              </p>
                              <p className="text-xs font-bold text-slate-500">
                                {sourceLabel(settings.user_notifications_source, t)}
                              </p>
                            </div>
                          </div>
                          <button
                            aria-pressed={notificationsEnabled}
                            className={`relative h-8 w-14 rounded-full border transition ${
                              notificationsEnabled
                                ? "border-cyan-300/50 bg-cyan-400/35"
                                : "border-white/10 bg-white/10"
                            }`}
                            onClick={() =>
                              setNotificationsEnabled((current) => !current)
                            }
                            type="button"
                          >
                            <span
                              className={`absolute top-1 h-5 w-5 rounded-full bg-white shadow transition ${
                                notificationsEnabled ? "left-7" : "left-1"
                              }`}
                            />
                          </button>
                        </div>
                      </div>
                    </div>
                  </section>

                  <section className="glass-panel overflow-hidden">
                    <div className="flex items-center justify-between border-b border-white/10 p-5">
                      <div>
                        <h2 className="text-xl font-black">
                          {t("admin.settings.runtime")}
                        </h2>
                        <p className="mt-1 text-sm font-semibold text-slate-400">
                          {t("admin.settings.runtimeDescription")}
                        </p>
                      </div>
                      <Server className="text-cyan-200" size={24} />
                    </div>

                    <dl className="grid gap-3 p-5">
                      <RuntimeRow
                        label={t("admin.settings.runtimeRows.project")}
                        value={settings.runtime.project_name}
                      />
                      <RuntimeRow
                        label={t("admin.settings.runtimeRows.environment")}
                        value={settings.runtime.environment}
                      />
                      <RuntimeRow
                        label={t("admin.settings.runtimeRows.aiService")}
                        value={settings.runtime.ai_service_url}
                      />
                      <RuntimeRow
                        label={t("admin.settings.runtimeRows.aiModel")}
                        value={settings.runtime.ai_model_version}
                      />
                      <RuntimeRow
                        label={t("admin.settings.runtimeRows.queue")}
                        value={settings.runtime.ekyc_queue_name}
                      />
                      <RuntimeRow
                        label={t("admin.settings.runtimeRows.uploadDir")}
                        value={settings.runtime.upload_dir}
                      />
                      <RuntimeRow
                        label={t("admin.settings.runtimeRows.imageUpload")}
                        value={`${settings.runtime.max_upload_size_mb} MB`}
                      />
                      <RuntimeRow
                        label={t("admin.settings.runtimeRows.videoUpload")}
                        value={`${settings.runtime.max_video_upload_size_mb} MB`}
                      />
                    </dl>
                  </section>
                </div>
              ) : null}
            </>
          )}
        </section>
      </main>
    </ProtectedRoute>
  );
}

function RuntimeRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.03] px-4 py-3">
      <dt className="text-xs font-black uppercase tracking-[0.18em] text-slate-500">
        {label}
      </dt>
      <dd className="mt-1 break-words text-sm font-bold text-slate-100">{value}</dd>
    </div>
  );
}
