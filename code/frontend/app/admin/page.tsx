"use client";

import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { AppHeader } from "@/components/site/AppHeader";
import { useAuth } from "@/contexts/AuthContext";
import { useLanguage } from "@/contexts/LanguageContext";
import { ApiError } from "@/lib/api";
import {
  getAdminOverview,
  type AdminOverview,
  type AdminServiceHealth,
} from "@/services/admin.service";
import {
  AlertTriangle,
  Activity,
  Clock3,
  Database,
  FileWarning,
  Loader2,
  RefreshCcw,
  Server,
  ShieldCheck,
  UserCog,
  UsersRound,
} from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";

function formatError(error: unknown) {
  if (error instanceof ApiError || error instanceof Error) {
    return error.message;
  }
  return "Unable to load admin overview.";
}

function formatDate(value: string | null | undefined, locale: string) {
  if (!value) {
    return "-";
  }
  return new Intl.DateTimeFormat(locale, {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value));
}

function healthClass(status?: string | null) {
  return status === "ok" ? "status-pill success" : "status-pill danger";
}

export default function AdminOverviewPage() {
  const { user } = useAuth();
  const { locale, t } = useLanguage();
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  const attentionCount = useMemo(() => {
    if (!overview) {
      return 0;
    }
    return overview.ekyc.failed + overview.ekyc.manual_review + overview.ekyc.processing;
  }, [overview]);

  async function loadOverview() {
    if (!user?.is_superuser) {
      return;
    }
    setIsLoading(true);
    setErrorMessage("");
    try {
      setOverview(await getAdminOverview());
    } catch (error) {
      setErrorMessage(formatError(error));
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    if (!user?.is_superuser) {
      return;
    }

    let isMounted = true;

    getAdminOverview()
      .then((response) => {
        if (isMounted) {
          setOverview(response);
        }
      })
      .catch((error) => {
        if (isMounted) {
          setErrorMessage(formatError(error));
        }
      })
      .finally(() => {
        if (isMounted) {
          setIsLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [user?.is_superuser]);

  return (
    <ProtectedRoute>
      <main className="min-h-screen overflow-hidden bg-[#030712] text-white">
        <div className="vintrade-bg" />
        <AppHeader />
        <section className="relative z-10 mx-auto max-w-[1480px] px-4 py-8 sm:px-6 lg:px-8">
          {!user?.is_superuser ? (
            <div className="glass-panel mx-auto max-w-xl p-6 text-center">
              <AlertTriangle className="mx-auto text-rose-300" size={34} />
              <h1 className="mt-4 text-2xl font-black">
                {t("admin.common.accessDenied")}
              </h1>
              <p className="mt-2 text-sm text-slate-300">
                {t("admin.overview.deniedDescription")}
              </p>
            </div>
          ) : (
            <>
              <div className="mb-6 flex flex-col justify-between gap-4 lg:flex-row lg:items-end">
                <div>
                  <span className="micro-badge">
                    <span className="status-dot cyan" />
                    {t("admin.overview.badge")}
                  </span>
                  <h1 className="mt-4 text-4xl font-black tracking-normal sm:text-5xl">
                    {t("admin.overview.title")}
                  </h1>
                  <p className="mt-3 max-w-2xl text-slate-300">
                    {t("admin.overview.description")}
                  </p>
                </div>
                <button
                  className="secondary-button"
                  disabled={isLoading}
                  onClick={loadOverview}
                  type="button"
                >
                  {isLoading ? (
                    <Loader2 className="animate-spin" size={16} />
                  ) : (
                    <RefreshCcw size={16} />
                  )}
                  {t("admin.common.refresh")}
                </button>
              </div>

              {errorMessage ? (
                <div className="mb-5 rounded-lg border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm font-semibold text-rose-100">
                  {errorMessage}
                </div>
              ) : null}

              {isLoading && !overview ? (
                <div className="glass-panel p-6 text-sm font-bold text-slate-300">
                  {t("admin.overview.loading")}
                </div>
              ) : overview ? (
                <>
                  <div className="mb-5 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                    <MetricCard
                      icon={<UsersRound size={27} />}
                      label={t("admin.overview.metrics.totalUsers")}
                      value={overview.users.total}
                    />
                    <MetricCard
                      icon={<UserCog size={27} />}
                      label={t("admin.overview.metrics.activeUsers")}
                      value={overview.users.active}
                      tone="success"
                    />
                    <MetricCard
                      icon={<ShieldCheck size={27} />}
                      label={t("admin.overview.metrics.reviewStaff")}
                      value={overview.users.reviewers}
                      tone="warning"
                    />
                    <MetricCard
                      icon={<Activity size={27} />}
                      label={t("admin.overview.metrics.ekycToday")}
                      value={overview.ekyc.today}
                      tone="info"
                    />
                  </div>

                  <div className="mb-5 grid gap-3 md:grid-cols-2 xl:grid-cols-5">
                    <StatusMetric
                      label={t("admin.overview.metrics.pending")}
                      value={overview.ekyc.pending}
                    />
                    <StatusMetric
                      label={t("admin.overview.metrics.processing")}
                      value={overview.ekyc.processing}
                    />
                    <StatusMetric
                      label={t("admin.overview.metrics.success")}
                      value={overview.ekyc.success}
                      tone="success"
                    />
                    <StatusMetric
                      label={t("admin.overview.metrics.failed")}
                      value={overview.ekyc.failed}
                      tone="danger"
                    />
                    <StatusMetric
                      label={t("admin.overview.metrics.manualReview")}
                      value={overview.ekyc.manual_review}
                      tone="warning"
                    />
                  </div>

                  <div className="grid gap-5 xl:grid-cols-[1fr_0.9fr]">
                    <section className="glass-panel overflow-hidden">
                      <div className="flex items-center justify-between border-b border-white/10 p-5">
                        <div>
                          <h2 className="text-xl font-black">
                            {t("admin.overview.systemHealth")}
                          </h2>
                          <p className="mt-1 text-sm text-slate-400">
                            {t("admin.overview.updated", {
                              date: formatDate(overview.system.generated_at, locale),
                            })}
                          </p>
                        </div>
                        <Server className="text-cyan-200" size={25} />
                      </div>
                      <div className="grid gap-3 p-5">
                        <HealthRow
                          icon={<Database size={18} />}
                          label={t("admin.overview.database")}
                          health={overview.system.database}
                        />
                        <HealthRow
                          icon={<Server size={18} />}
                          label={t("admin.overview.redis")}
                          health={overview.system.redis}
                        />
                        <div className="rounded-lg border border-white/10 bg-slate-950/50 p-4">
                          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                            <div className="flex items-center gap-3">
                              <Activity className="text-cyan-200" size={18} />
                              <div>
                                <p className="text-sm font-black text-white">
                                  {t("admin.overview.ekycQueue")}
                                </p>
                                <p className="mt-1 text-xs text-slate-400">
                                  {overview.system.ekyc_queue.queue_name}
                                </p>
                              </div>
                            </div>
                            <div className="flex items-center gap-3">
                              <span className={healthClass(overview.system.ekyc_queue.status)}>
                                {overview.system.ekyc_queue.status}
                              </span>
                              <span className="min-w-20 text-right text-2xl font-black text-white">
                                {overview.system.ekyc_queue.pending_jobs ?? "-"}
                              </span>
                            </div>
                          </div>
                          {overview.system.ekyc_queue.message ? (
                            <p className="mt-3 break-words text-xs font-semibold text-rose-200">
                              {overview.system.ekyc_queue.message}
                            </p>
                          ) : null}
                        </div>
                      </div>
                    </section>

                    <section className="glass-panel overflow-hidden">
                      <div className="flex items-center justify-between border-b border-white/10 p-5">
                        <div>
                          <h2 className="text-xl font-black">
                            {t("admin.overview.attentionNeeded")}
                          </h2>
                          <p className="mt-1 text-sm text-slate-400">
                            {t("admin.overview.attentionDescription")}
                          </p>
                        </div>
                        <FileWarning className="text-amber-200" size={25} />
                      </div>
                      <div className="grid gap-3 p-5">
                        <AttentionRow
                          href="/admin/ekyc?status=FAILED"
                          label={t("admin.overview.metrics.failed")}
                          value={overview.ekyc.failed}
                          tone="danger"
                        />
                        <AttentionRow
                          href="/admin/ekyc?status=MANUAL_REVIEW"
                          label={t("admin.overview.metrics.manualReview")}
                          value={overview.ekyc.manual_review}
                          tone="warning"
                        />
                        <AttentionRow
                          href="/admin/ekyc?status=PROCESSING"
                          label={t("admin.overview.metrics.processing")}
                          value={overview.ekyc.processing}
                        />
                        <div className="mt-2 rounded-lg border border-white/10 bg-slate-950/50 p-4">
                          <div className="flex items-center gap-3">
                            <Clock3 className="text-slate-300" size={18} />
                            <div>
                              <p className="text-sm font-black text-white">
                                {t("admin.overview.latestEkyc")}
                              </p>
                              <p className="mt-1 text-xs text-slate-400">
                                {t("admin.overview.created", {
                                  date: formatDate(overview.ekyc.latest_created_at, locale),
                                })}
                              </p>
                              <p className="mt-1 text-xs text-slate-400">
                                {t("admin.overview.processed", {
                                  date: formatDate(
                                    overview.ekyc.latest_processed_at,
                                    locale,
                                  ),
                                })}
                              </p>
                            </div>
                          </div>
                        </div>
                      </div>
                    </section>
                  </div>

                  <div className="mt-5 grid gap-3 md:grid-cols-2">
                    <Link className="secondary-button justify-center" href="/admin/users">
                      <UserCog size={17} />
                      {t("admin.overview.adminUsers")}
                    </Link>
                    <Link className="secondary-button justify-center" href="/admin/ekyc">
                      <ShieldCheck size={17} />
                      {t("admin.overview.adminEkyc")}
                    </Link>
                  </div>

                  <p className="mt-5 text-sm font-semibold text-slate-400">
                    {t("admin.overview.attentionSummary", { count: attentionCount })}
                  </p>
                </>
              ) : null}
            </>
          )}
        </section>
      </main>
    </ProtectedRoute>
  );
}

function MetricCard({
  icon,
  label,
  tone = "default",
  value,
}: {
  icon: ReactNode;
  label: string;
  tone?: "default" | "success" | "warning" | "danger" | "info";
  value: number;
}) {
  const toneClass =
    tone === "success"
      ? "text-emerald-300"
      : tone === "warning"
        ? "text-amber-200"
        : tone === "danger"
          ? "text-rose-200"
          : tone === "info"
            ? "text-sky-200"
            : "text-cyan-200";

  return (
    <div className="glass-panel p-5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-bold text-slate-400">{label}</p>
          <p className="mt-2 text-3xl font-black text-white">{value}</p>
        </div>
        <div className={toneClass}>{icon}</div>
      </div>
    </div>
  );
}

function StatusMetric({
  label,
  tone = "default",
  value,
}: {
  label: string;
  tone?: "default" | "success" | "warning" | "danger";
  value: number;
}) {
  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.04] p-4">
      <p className="text-xs font-black uppercase text-slate-500">{label}</p>
      <div className="mt-3 flex items-end justify-between gap-3">
        <p className="text-3xl font-black text-white">{value}</p>
        <span
          className={`h-2.5 w-2.5 rounded-full ${
            tone === "success"
              ? "bg-emerald-300"
              : tone === "warning"
                ? "bg-amber-300"
                : tone === "danger"
                  ? "bg-rose-300"
                  : "bg-cyan-300"
          }`}
        />
      </div>
    </div>
  );
}

function HealthRow({
  health,
  icon,
  label,
}: {
  health: AdminServiceHealth;
  icon: ReactNode;
  label: string;
}) {
  return (
    <div className="rounded-lg border border-white/10 bg-slate-950/50 p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <div className="text-cyan-200">{icon}</div>
          <p className="text-sm font-black text-white">{label}</p>
        </div>
        <span className={healthClass(health.status)}>{health.status}</span>
      </div>
      {health.message ? (
        <p className="mt-3 break-words text-xs font-semibold text-rose-200">
          {health.message}
        </p>
      ) : null}
    </div>
  );
}

function AttentionRow({
  href,
  label,
  tone = "default",
  value,
}: {
  href?: string;
  label: string;
  tone?: "default" | "warning" | "danger";
  value: number;
}) {
  const pillClass =
    tone === "danger"
      ? "status-pill danger"
      : tone === "warning"
        ? "status-pill"
        : "status-pill";

  const content = (
    <>
      <span className={pillClass}>{label}</span>
      <span className="text-2xl font-black text-white">{value}</span>
    </>
  );

  if (href) {
    return (
      <Link
        className="flex items-center justify-between gap-4 rounded-lg border border-white/10 bg-slate-950/50 p-4 transition hover:border-cyan-300/35 hover:bg-cyan-400/10"
        href={href}
      >
        {content}
      </Link>
    );
  }

  return (
    <div className="flex items-center justify-between gap-4 rounded-lg border border-white/10 bg-slate-950/50 p-4">
      {content}
    </div>
  );
}
