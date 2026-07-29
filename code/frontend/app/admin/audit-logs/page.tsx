"use client";

import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { AppHeader } from "@/components/site/AppHeader";
import { useAuth } from "@/contexts/AuthContext";
import { useLanguage } from "@/contexts/LanguageContext";
import { ApiError } from "@/lib/api";
import {
  listAdminAuditLogs,
  type AdminAuditLog,
  type AdminAuditLogsParams,
} from "@/services/admin.service";
import {
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  Eye,
  FileClock,
  Loader2,
  RefreshCcw,
  X,
} from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import type { FormEvent } from "react";
import { Suspense, useCallback, useEffect, useState } from "react";

const PAGE_SIZE = 25;
const ACTION_OPTIONS = [
  { labelKey: "admin.audit.filters.allActions", value: "" },
  { labelKey: "admin.audit.filters.settingsUpdate", value: "admin.settings.update" },
  { labelKey: "admin.audit.filters.userCreate", value: "user.create" },
  { labelKey: "admin.audit.filters.userUpdate", value: "user.update" },
  { labelKey: "admin.audit.filters.userDelete", value: "user.delete" },
  { labelKey: "admin.audit.filters.ekycApprove", value: "ekyc.approve" },
  { labelKey: "admin.audit.filters.ekycReject", value: "ekyc.reject" },
  { labelKey: "admin.audit.filters.ekycRetry", value: "ekyc.retry" },
  { labelKey: "admin.audit.filters.ekycDelete", value: "ekyc.delete" },
];
const TARGET_TYPE_OPTIONS = [
  { labelKey: "admin.audit.filters.allTargets", value: "" },
  { labelKey: "admin.audit.filters.user", value: "user" },
  { labelKey: "admin.audit.filters.ekycRequest", value: "ekyc_request" },
];

function formatError(error: unknown) {
  if (error instanceof ApiError || error instanceof Error) {
    return error.message;
  }
  return "Unable to load audit logs.";
}

function formatDate(value: string | null | undefined, locale: string) {
  if (!value) {
    return "-";
  }
  return new Intl.DateTimeFormat(locale, {
    dateStyle: "short",
    timeStyle: "medium",
  }).format(new Date(value));
}

function actionClass(action: string) {
  if (action.includes("delete") || action.includes("reject")) {
    return "status-pill danger";
  }
  if (action.includes("approve") || action.includes("create")) {
    return "status-pill success";
  }
  return "status-pill";
}

function shortValue(value?: string | null) {
  if (!value) {
    return "-";
  }
  return value.length > 24 ? `${value.slice(0, 12)}...${value.slice(-8)}` : value;
}

export default function AdminAuditLogsPage() {
  const { t } = useLanguage();

  return (
    <Suspense
      fallback={
        <main className="min-h-screen bg-[#030712] text-white">
          <div className="vintrade-bg" />
          <div className="relative z-10 grid min-h-screen place-items-center px-4">
            <div className="glass-panel p-6 text-center">
              <p className="text-sm font-bold text-cyan-200">
                {t("admin.audit.loading")}
              </p>
            </div>
          </div>
        </main>
      }
    >
      <AdminAuditLogsContent />
    </Suspense>
  );
}

function AdminAuditLogsContent() {
  const { locale, t } = useLanguage();
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user } = useAuth();
  const [logs, setLogs] = useState<AdminAuditLog[]>([]);
  const [selected, setSelected] = useState<AdminAuditLog | null>(null);
  const [totalCount, setTotalCount] = useState(0);
  const [page, setPage] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState("");
  const pageCount = Math.max(1, Math.ceil(totalCount / PAGE_SIZE));
  const pageStart = totalCount === 0 ? 0 : page * PAGE_SIZE + 1;
  const pageEnd = Math.min((page + 1) * PAGE_SIZE, totalCount);
  const filterKey = searchParams.toString();
  const actionFilter = searchParams.get("action") ?? "";
  const targetTypeFilter = searchParams.get("target_type") ?? "";
  const queryFilter = searchParams.get("q") ?? "";
  const hasFilters = Boolean(actionFilter || targetTypeFilter || queryFilter);

  const listParams = useCallback((targetPage = page): AdminAuditLogsParams => {
    return {
      action: actionFilter,
      limit: PAGE_SIZE,
      query: queryFilter,
      skip: targetPage * PAGE_SIZE,
      targetType: targetTypeFilter,
    };
  }, [actionFilter, page, queryFilter, targetTypeFilter]);

  async function loadLogs(targetPage = page) {
    setIsLoading(true);
    setErrorMessage("");
    try {
      const response = await listAdminAuditLogs(listParams(targetPage));
      setLogs(response.data);
      setTotalCount(response.count);
      setSelected(null);
    } catch (error) {
      setErrorMessage(formatError(error));
    } finally {
      setIsLoading(false);
    }
  }

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const nextParams = new URLSearchParams();
    const query = String(formData.get("q") ?? "").trim();
    const action = String(formData.get("action") ?? "");
    const targetType = String(formData.get("target_type") ?? "");

    if (query) {
      nextParams.set("q", query);
    }
    if (action) {
      nextParams.set("action", action);
    }
    if (targetType) {
      nextParams.set("target_type", targetType);
    }

    setPage(0);
    router.replace(
      nextParams.toString() ? `${pathname}?${nextParams.toString()}` : pathname,
    );
  }

  function clearFilters() {
    setPage(0);
    router.replace(pathname);
  }

  useEffect(() => {
    let isMounted = true;

    listAdminAuditLogs(listParams(page))
      .then((response) => {
        if (!isMounted) {
          return;
        }
        setLogs(response.data);
        setTotalCount(response.count);
        setSelected(null);
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
  }, [page, filterKey, listParams]);

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
                {t("admin.audit.deniedDescription")}
              </p>
            </div>
          ) : (
            <>
              <div className="mb-6 flex flex-col justify-between gap-4 lg:flex-row lg:items-end">
                <div>
                  <span className="micro-badge">
                    <span className="status-dot cyan" />
                    {t("admin.audit.badge")}
                  </span>
                  <h1 className="mt-4 text-4xl font-black tracking-normal sm:text-5xl">
                    {t("admin.audit.title")}
                  </h1>
                  <p className="mt-3 max-w-2xl text-slate-300">
                    {t("admin.audit.description")}
                  </p>
                </div>
                <button
                  className="secondary-button"
                  disabled={isLoading}
                  onClick={() => loadLogs()}
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

              <form
                className="mb-5 grid gap-3 rounded-lg border border-white/10 bg-white/[0.04] p-4 lg:grid-cols-[1.5fr_1fr_1fr_auto]"
                onSubmit={applyFilters}
              >
                <div className="input-shell min-h-11">
                  <input
                    aria-label={t("admin.audit.searchLabel")}
                    defaultValue={queryFilter}
                    key={`q-${filterKey}`}
                    name="q"
                    placeholder={t("admin.audit.searchPlaceholder")}
                    type="search"
                  />
                </div>
                <div className="input-shell min-h-11">
                  <select
                    className="w-full border-0 bg-transparent text-white outline-0"
                    defaultValue={actionFilter}
                    key={`action-${filterKey}`}
                    name="action"
                  >
                    {ACTION_OPTIONS.map((option) => (
                      <option
                        className="bg-slate-950 text-white"
                        key={option.value || "all"}
                        value={option.value}
                      >
                        {t(option.labelKey)}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="input-shell min-h-11">
                  <select
                    className="w-full border-0 bg-transparent text-white outline-0"
                    defaultValue={targetTypeFilter}
                    key={`target-${filterKey}`}
                    name="target_type"
                  >
                    {TARGET_TYPE_OPTIONS.map((option) => (
                      <option
                        className="bg-slate-950 text-white"
                        key={option.value || "all"}
                        value={option.value}
                      >
                        {t(option.labelKey)}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="flex gap-2">
                  <button
                    className="primary-button h-11 justify-center px-4"
                    disabled={isLoading}
                    type="submit"
                  >
                    {t("admin.common.apply")}
                  </button>
                  {hasFilters ? (
                    <button
                      className="secondary-button h-11 justify-center px-4"
                      disabled={isLoading}
                      onClick={clearFilters}
                      type="button"
                    >
                      {t("admin.common.clear")}
                    </button>
                  ) : null}
                </div>
              </form>

              <div className="glass-panel overflow-hidden">
                <div className="flex items-center justify-between border-b border-white/10 p-5">
                  <div>
                    <h2 className="text-xl font-black">{t("admin.audit.trail")}</h2>
                    <p className="mt-1 text-sm text-slate-400">
                      {t("admin.audit.trailSummary", {
                        end: pageEnd,
                        start: pageStart,
                        total: totalCount,
                      })}
                    </p>
                  </div>
                  <FileClock className="text-cyan-200" size={24} />
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full min-w-[1040px] text-left text-sm">
                    <thead className="border-b border-white/10 text-xs uppercase text-slate-400">
                      <tr>
                        <th className="px-5 py-4">{t("admin.audit.table.time")}</th>
                        <th className="px-5 py-4">{t("admin.audit.table.actor")}</th>
                        <th className="px-5 py-4">{t("admin.audit.table.action")}</th>
                        <th className="px-5 py-4">{t("admin.audit.table.target")}</th>
                        <th className="px-5 py-4">{t("admin.audit.table.targetId")}</th>
                        <th className="px-5 py-4">{t("admin.audit.table.detail")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {isLoading ? (
                        <tr>
                          <td className="px-5 py-8 text-center text-slate-300" colSpan={6}>
                            {t("admin.audit.loading")}
                          </td>
                        </tr>
                      ) : logs.length ? (
                        logs.map((log) => (
                          <tr
                            className="border-b border-white/10 transition hover:bg-cyan-400/5"
                            key={log.id}
                          >
                            <td className="px-5 py-4 text-slate-300">
                              {formatDate(log.created_at, locale)}
                            </td>
                            <td className="px-5 py-4">
                              <p className="font-bold text-white">
                                {log.actor_email ?? t("admin.common.unknown")}
                              </p>
                              <p className="mt-1 text-xs text-slate-500">
                                {shortValue(log.actor_user_id)}
                              </p>
                            </td>
                            <td className="px-5 py-4">
                              <span className={actionClass(log.action)}>
                                {log.action}
                              </span>
                            </td>
                            <td className="px-5 py-4 text-slate-300">
                              <p className="font-bold text-white">
                                {log.target_label ?? "-"}
                              </p>
                              <p className="mt-1 text-xs uppercase text-slate-500">
                                {log.target_type}
                              </p>
                            </td>
                            <td className="px-5 py-4 font-mono text-xs text-slate-400">
                              {shortValue(log.target_id)}
                            </td>
                            <td className="px-5 py-4">
                              <button
                                className="secondary-button h-10 px-3"
                                onClick={() => setSelected(log)}
                                type="button"
                              >
                                <Eye size={15} />
                                {t("admin.common.view")}
                              </button>
                            </td>
                          </tr>
                        ))
                      ) : (
                        <tr>
                          <td className="px-5 py-8 text-center text-slate-300" colSpan={6}>
                            {t("admin.audit.empty")}
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>

                <PaginationControls
                  isLoading={isLoading}
                  onNext={() => {
                    setIsLoading(true);
                    setPage((current) => Math.min(current + 1, pageCount - 1));
                  }}
                  onPrevious={() => {
                    setIsLoading(true);
                    setPage((current) => Math.max(current - 1, 0));
                  }}
                  page={page}
                  pageCount={pageCount}
                  pageEnd={pageEnd}
                  pageStart={pageStart}
                  totalCount={totalCount}
                />
              </div>

              <AuditLogDetailModal
                log={selected}
                onClose={() => setSelected(null)}
              />
            </>
          )}
        </section>
      </main>
    </ProtectedRoute>
  );
}

function PaginationControls({
  isLoading,
  onNext,
  onPrevious,
  page,
  pageCount,
  pageEnd,
  pageStart,
  totalCount,
}: {
  isLoading: boolean;
  onNext: () => void;
  onPrevious: () => void;
  page: number;
  pageCount: number;
  pageEnd: number;
  pageStart: number;
  totalCount: number;
}) {
  const { t } = useLanguage();

  return (
    <div className="flex flex-col gap-3 border-t border-white/10 p-4 text-sm text-slate-300 sm:flex-row sm:items-center sm:justify-between">
      <span>
        {t("admin.common.showing", {
          end: pageEnd,
          start: pageStart,
          total: totalCount,
        })}
      </span>
      <div className="flex items-center gap-2">
        <button
          className="secondary-button h-10 px-3"
          disabled={isLoading || page === 0}
          onClick={onPrevious}
          title={t("admin.common.previousPage")}
          type="button"
        >
          <ChevronLeft size={16} />
        </button>
        <span className="min-w-24 text-center font-bold text-slate-100">
          {t("admin.common.page", { current: page + 1, total: pageCount })}
        </span>
        <button
          className="secondary-button h-10 px-3"
          disabled={isLoading || page + 1 >= pageCount}
          onClick={onNext}
          title={t("admin.common.nextPage")}
          type="button"
        >
          <ChevronRight size={16} />
        </button>
      </div>
    </div>
  );
}

function AuditLogDetailModal({
  log,
  onClose,
}: {
  log: AdminAuditLog | null;
  onClose: () => void;
}) {
  const { locale, t } = useLanguage();

  if (!log) {
    return null;
  }

  return (
    <div
      aria-labelledby="audit-log-detail-title"
      aria-modal="true"
      className="fixed inset-0 z-[80] flex items-center justify-center bg-black/70 px-4 py-8 backdrop-blur-md"
      onClick={onClose}
      role="dialog"
    >
      <section
        className="glass-panel max-h-[78vh] w-full max-w-3xl overflow-y-auto p-5 shadow-[0_24px_90px_rgba(0,0,0,0.45)]"
        onClick={(event) => event.stopPropagation()}
        style={{ overflowY: "auto" }}
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <span className={actionClass(log.action)}>{log.action}</span>
            <h2 id="audit-log-detail-title" className="mt-4 text-2xl font-black">
              {t("admin.audit.detailTitle")}
            </h2>
            <p className="mt-2 text-sm text-slate-300">
              {formatDate(log.created_at, locale)}
            </p>
          </div>
          <button
            aria-label={t("admin.common.closeDetailModal")}
            className="grid h-10 w-10 place-items-center rounded-full border border-rose-300/60 bg-rose-500/10 text-rose-100 transition hover:bg-rose-500/20"
            onClick={onClose}
            type="button"
          >
            <X size={18} />
          </button>
        </div>

        <div className="mt-5 grid gap-3 sm:grid-cols-2">
          <MiniField label={t("admin.audit.table.actor")} value={log.actor_email} />
          <MiniField label={t("admin.audit.table.actorId")} value={log.actor_user_id} />
          <MiniField label={t("admin.audit.table.targetType")} value={log.target_type} />
          <MiniField label={t("admin.audit.table.targetLabel")} value={log.target_label} />
          <MiniField label={t("admin.audit.table.targetId")} value={log.target_id} wide />
        </div>

        <JsonBlock title={t("admin.common.details")} value={log.details} />
      </section>
    </div>
  );
}

function MiniField({
  label,
  value,
  wide = false,
}: {
  label: string;
  value?: string | number | null;
  wide?: boolean;
}) {
  return (
    <div
      className={`rounded-lg border border-white/10 bg-slate-950/50 p-3 ${
        wide ? "sm:col-span-2" : ""
      }`}
    >
      <span className="text-xs font-black uppercase text-slate-500">{label}</span>
      <p className="mt-1 break-all text-sm font-semibold text-slate-100">
        {value ?? "-"}
      </p>
    </div>
  );
}

function JsonBlock({
  title,
  value,
}: {
  title: string;
  value?: unknown;
}) {
  return (
    <section className="mt-5 rounded-lg border border-white/10 bg-slate-950/70 p-4">
      <h3 className="text-sm font-black text-white">{title}</h3>
      <pre className="mt-3 max-h-[360px] overflow-auto whitespace-pre-wrap break-words rounded-lg bg-black/40 p-3 text-xs leading-5 text-cyan-100">
        {JSON.stringify(value ?? {}, null, 2)}
      </pre>
    </section>
  );
}
