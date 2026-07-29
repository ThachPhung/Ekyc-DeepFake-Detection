"use client";

import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { AppHeader } from "@/components/site/AppHeader";
import { useAuth } from "@/contexts/AuthContext";
import { useLanguage } from "@/contexts/LanguageContext";
import { ApiError } from "@/lib/api";
import {
  approveAdminEkycRequest,
  deleteAdminEkycRequest,
  generateAdminAiReview,
  getAdminEkycFileBlob,
  getAdminEkycRequest,
  listAdminEkycRequests,
  rejectAdminEkycRequest,
  retryAdminEkycRequest,
  updateAdminEkycDocumentFields,
  type AdminEkycDocumentFieldsPayload,
  type AdminEkycListParams,
  type AdminAiReview,
  type EkycRequestStatus,
  type EkycVideoStatus,
  type FaceDecision,
  type EkycRequestAdminResponse,
} from "@/services/ekyc.service";
import {
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  CheckCircle2,
  Eye,
  Loader2,
  Pencil,
  RefreshCcw,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  Trash2,
  X,
  XCircle,
} from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import type { FormEvent } from "react";
import { Suspense, useCallback, useEffect, useState } from "react";

const PAGE_SIZE = 20;
const STATUS_OPTIONS: Array<{ labelKey: string; value: EkycRequestStatus | "" }> = [
  { labelKey: "admin.ekyc.filters.allStatus", value: "" },
  { labelKey: "admin.ekyc.filters.pending", value: "PENDING" },
  { labelKey: "admin.ekyc.filters.processing", value: "PROCESSING" },
  { labelKey: "admin.ekyc.filters.success", value: "SUCCESS" },
  { labelKey: "admin.ekyc.filters.failed", value: "FAILED" },
  { labelKey: "admin.ekyc.filters.manualReview", value: "MANUAL_REVIEW" },
];
const VIDEO_STATUS_OPTIONS: Array<{ labelKey: string; value: EkycVideoStatus | "" }> = [
  { labelKey: "admin.ekyc.filters.allVideo", value: "" },
  { labelKey: "admin.ekyc.filters.notStarted", value: "NOT_STARTED" },
  { labelKey: "admin.ekyc.filters.pending", value: "PENDING" },
  { labelKey: "admin.ekyc.filters.processing", value: "PROCESSING" },
  { labelKey: "admin.ekyc.filters.success", value: "SUCCESS" },
  { labelKey: "admin.ekyc.filters.failed", value: "FAILED" },
];
const FACE_DECISION_OPTIONS: Array<{ labelKey: string; value: FaceDecision | "" }> = [
  { labelKey: "admin.ekyc.filters.allFace", value: "" },
  { labelKey: "admin.ekyc.filters.match", value: "match" },
  { labelKey: "admin.ekyc.filters.consider", value: "consider" },
  { labelKey: "admin.ekyc.filters.notMatch", value: "not_match" },
];

type DocumentFieldKey =
  | "full_name"
  | "id_number"
  | "passport_number"
  | "date_of_birth"
  | "birth_year"
  | "sex"
  | "gender"
  | "nationality"
  | "address"
  | "place_of_origin"
  | "place_of_residence"
  | "issue_date"
  | "issue_place"
  | "expiry_date"
  | "expired_date";

type DocumentFieldsFormState = Record<DocumentFieldKey, string>;

const DOCUMENT_FIELD_CONFIG: Array<{ key: DocumentFieldKey; label: string }> = [
  { key: "full_name", label: "Ho ten" },
  { key: "id_number", label: "So CCCD/CMND" },
  { key: "passport_number", label: "So ho chieu" },
  { key: "date_of_birth", label: "Ngay sinh" },
  { key: "birth_year", label: "Nam sinh" },
  { key: "sex", label: "Gioi tinh" },
  { key: "gender", label: "Gioi tinh OCR" },
  { key: "nationality", label: "Quoc tich" },
  { key: "address", label: "Dia chi" },
  { key: "place_of_origin", label: "Que quan" },
  { key: "place_of_residence", label: "Noi thuong tru" },
  { key: "issue_date", label: "Ngay cap" },
  { key: "issue_place", label: "Noi cap" },
  { key: "expiry_date", label: "Ngay het han" },
  { key: "expired_date", label: "Ngay het han OCR" },
];

function formatError(error: unknown) {
  if (error instanceof ApiError || error instanceof Error) {
    return error.message;
  }
  return "Unable to load eKYC data.";
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

function statusClass(status?: string | null) {
  if (status === "SUCCESS" || status === "match") {
    return "status-pill success";
  }
  if (status === "FAILED" || status === "not_match") {
    return "status-pill danger";
  }
  return "status-pill";
}

function shortId(value?: string | null) {
  return value ? `${value.slice(0, 8)}...${value.slice(-6)}` : "-";
}

function ekycDisplayField(
  request: EkycRequestAdminResponse,
  key: "full_name" | "id_number",
) {
  const confirmed = request.document_confirmed_fields?.[key];
  const ocr = request.ocr_result?.[key];
  const parsedFields =
    request.ocr_result?.parsed_fields &&
      typeof request.ocr_result.parsed_fields === "object" &&
      !Array.isArray(request.ocr_result.parsed_fields)
      ? (request.ocr_result.parsed_fields as Record<string, unknown>)
      : null;
  const parsed = parsedFields?.[key];
  if (typeof confirmed === "string" && confirmed.trim()) {
    return confirmed;
  }
  if (typeof ocr === "string" && ocr.trim()) {
    return ocr;
  }
  if (typeof parsed === "string" && parsed.trim()) {
    return parsed;
  }
  return "";
}

function objectValue(
  source: Partial<Record<DocumentFieldKey, unknown>> | null | undefined,
  key: DocumentFieldKey,
) {
  const value = source?.[key];
  return typeof value === "string" ? value : "";
}

function parsedOcrFields(request: EkycRequestAdminResponse) {
  const parsedFields = request.ocr_result?.parsed_fields;
  return parsedFields &&
    typeof parsedFields === "object" &&
    !Array.isArray(parsedFields)
    ? (parsedFields as Record<string, unknown>)
    : null;
}

function documentFieldsFormFromRequest(
  request: EkycRequestAdminResponse,
): DocumentFieldsFormState {
  const parsedFields = parsedOcrFields(request);
  return DOCUMENT_FIELD_CONFIG.reduce<DocumentFieldsFormState>((form, field) => {
    const confirmed = objectValue(request.document_confirmed_fields, field.key);
    const ocr = objectValue(request.ocr_result, field.key);
    const parsed = objectValue(parsedFields, field.key);
    form[field.key] = confirmed || ocr || parsed;
    return form;
  }, {} as DocumentFieldsFormState);
}

export default function AdminEkycPage() {
  const { t } = useLanguage();

  return (
    <Suspense
      fallback={
        <main className="min-h-screen bg-[#030712] text-white">
          <div className="vintrade-bg" />
          <div className="relative z-10 grid min-h-screen place-items-center px-4">
            <div className="glass-panel p-6 text-center">
              <p className="text-sm font-bold text-cyan-200">
                {t("admin.ekyc.loading")}
              </p>
            </div>
          </div>
        </main>
      }
    >
      <AdminEkycContent />
    </Suspense>
  );
}

function AdminEkycContent() {
  const { locale, t } = useLanguage();
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user } = useAuth();
  const canReviewEkyc =
    Boolean(user?.is_superuser) || user?.role === "ekyc_reviewer";
  const [requests, setRequests] = useState<EkycRequestAdminResponse[]>([]);
  const [selected, setSelected] = useState<EkycRequestAdminResponse | null>(null);
  const [totalCount, setTotalCount] = useState(0);
  const [page, setPage] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [deletingRequestId, setDeletingRequestId] = useState<string | null>(null);
  const [reviewingRequestId, setReviewingRequestId] = useState<string | null>(null);
  const [aiReviewRequestId, setAiReviewRequestId] = useState<string | null>(null);
  const [retryingRequestId, setRetryingRequestId] = useState<string | null>(null);
  const [savingDocumentFieldsRequestId, setSavingDocumentFieldsRequestId] =
    useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState("");
  const pageCount = Math.max(1, Math.ceil(totalCount / PAGE_SIZE));
  const pageStart = totalCount === 0 ? 0 : page * PAGE_SIZE + 1;
  const pageEnd = Math.min((page + 1) * PAGE_SIZE, totalCount);
  const filterKey = searchParams.toString();
  const statusFilter = (searchParams.get("status") ?? "") as
    | EkycRequestStatus
    | "";
  const videoStatusFilter = (searchParams.get("video_status") ?? "") as
    | EkycVideoStatus
    | "";
  const faceDecisionFilter = (searchParams.get("face_decision") ?? "") as
    | FaceDecision
    | "";
  const queryFilter = searchParams.get("q") ?? "";
  const sortFilter =
    searchParams.get("sort") === "oldest" ? "oldest" : "latest";
  const hasFilters = Boolean(
    statusFilter ||
    videoStatusFilter ||
    faceDecisionFilter ||
    queryFilter ||
    sortFilter === "oldest",
  );

  const listParams = useCallback((targetPage = page): AdminEkycListParams => {
    return {
      faceDecision: faceDecisionFilter,
      limit: PAGE_SIZE,
      query: queryFilter,
      skip: targetPage * PAGE_SIZE,
      sort: sortFilter,
      status: statusFilter,
      videoStatus: videoStatusFilter,
    };
  }, [
    faceDecisionFilter,
    page,
    queryFilter,
    sortFilter,
    statusFilter,
    videoStatusFilter,
  ]);

  async function loadRequests(targetPage = page) {
    setIsLoading(true);
    setErrorMessage("");
    try {
      const response = await listAdminEkycRequests(listParams(targetPage));
      setRequests(response.data);
      setTotalCount(response.count);
      setSelected(null);
    } catch (error) {
      setErrorMessage(formatError(error));
    } finally {
      setIsLoading(false);
    }
  }

  async function openDetail(requestId: string) {
    setErrorMessage("");
    try {
      const detail = await getAdminEkycRequest(requestId);
      setSelected(detail);
    } catch (error) {
      setErrorMessage(formatError(error));
    }
  }

  function updateRecord(updatedRecord: EkycRequestAdminResponse) {
    setRequests((current) =>
      current.map((item) =>
        item.request_id === updatedRecord.request_id ? updatedRecord : item,
      ),
    );
    setSelected((current) =>
      current?.request_id === updatedRecord.request_id ? updatedRecord : current,
    );
  }

  async function approveRecord(request: EkycRequestAdminResponse) {
    const confirmed = window.confirm(
      t("admin.ekyc.confirmApprove", {
        label: request.owner_email ?? request.request_id,
      }),
    );
    if (!confirmed) {
      return;
    }

    setReviewingRequestId(request.request_id);
    setErrorMessage("");
    try {
      const updatedRecord = await approveAdminEkycRequest(request.request_id);
      updateRecord(updatedRecord);
    } catch (error) {
      setErrorMessage(formatError(error));
    } finally {
      setReviewingRequestId(null);
    }
  }

  async function rejectRecord(request: EkycRequestAdminResponse) {
    const reason = window.prompt(
      t("admin.ekyc.promptReject", {
        label: request.owner_email ?? request.request_id,
      }),
    );
    if (reason === null) {
      return;
    }
    const trimmedReason = reason.trim();
    if (!trimmedReason) {
      setErrorMessage(t("admin.ekyc.rejectReasonRequired"));
      return;
    }

    setReviewingRequestId(request.request_id);
    setErrorMessage("");
    try {
      const updatedRecord = await rejectAdminEkycRequest(
        request.request_id,
        trimmedReason,
      );
      updateRecord(updatedRecord);
    } catch (error) {
      setErrorMessage(formatError(error));
    } finally {
      setReviewingRequestId(null);
    }
  }

  async function retryRecord(request: EkycRequestAdminResponse) {
    const confirmed = window.confirm(
      t("admin.ekyc.confirmRetry", {
        label: request.owner_email ?? request.request_id,
      }),
    );
    if (!confirmed) {
      return;
    }

    setRetryingRequestId(request.request_id);
    setErrorMessage("");
    try {
      const updatedRecord = await retryAdminEkycRequest(request.request_id);
      updateRecord(updatedRecord);
    } catch (error) {
      setErrorMessage(formatError(error));
    } finally {
      setRetryingRequestId(null);
    }
  }

  async function generateAiReview(request: EkycRequestAdminResponse) {
    setAiReviewRequestId(request.request_id);
    setErrorMessage("");
    try {
      const updatedRecord = await generateAdminAiReview(request.request_id);
      updateRecord(updatedRecord);
    } catch (error) {
      setErrorMessage(formatError(error));
    } finally {
      setAiReviewRequestId(null);
    }
  }

  async function saveDocumentFields(
    request: EkycRequestAdminResponse,
    fields: AdminEkycDocumentFieldsPayload,
  ) {
    setSavingDocumentFieldsRequestId(request.request_id);
    setErrorMessage("");
    try {
      const updatedRecord = await updateAdminEkycDocumentFields(
        request.request_id,
        fields,
      );
      updateRecord(updatedRecord);
    } catch (error) {
      setErrorMessage(formatError(error));
    } finally {
      setSavingDocumentFieldsRequestId(null);
    }
  }

  async function deleteRecord(request: EkycRequestAdminResponse) {
    const userLabel =
      request.owner_email ??
      request.owner_full_name ??
      ekycDisplayField(request, "full_name") ??
      request.request_id;
    const confirmed = window.confirm(
      t("admin.ekyc.confirmDelete", { label: userLabel }),
    );
    if (!confirmed) {
      return;
    }

    setDeletingRequestId(request.request_id);
    setErrorMessage("");
    try {
      await deleteAdminEkycRequest(request.request_id);
      setRequests((current) =>
        current.filter((item) => item.request_id !== request.request_id),
      );
      setTotalCount((count) => Math.max(count - 1, 0));
      setSelected((current) =>
        current?.request_id === request.request_id ? null : current,
      );
    } catch (error) {
      setErrorMessage(formatError(error));
    } finally {
      setDeletingRequestId(null);
    }
  }

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    const nextParams = new URLSearchParams();
    const query = String(formData.get("q") ?? "").trim();
    const status = String(formData.get("status") ?? "");
    const videoStatus = String(formData.get("video_status") ?? "");
    const faceDecision = String(formData.get("face_decision") ?? "");
    const sort = String(formData.get("sort") ?? "latest");

    if (query) {
      nextParams.set("q", query);
    }
    if (status) {
      nextParams.set("status", status);
    }
    if (videoStatus) {
      nextParams.set("video_status", videoStatus);
    }
    if (faceDecision) {
      nextParams.set("face_decision", faceDecision);
    }
    if (sort === "oldest") {
      nextParams.set("sort", sort);
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

    listAdminEkycRequests(listParams(page))
      .then((response) => {
        if (!isMounted) {
          return;
        }
        setRequests(response.data);
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
          {!canReviewEkyc ? (
            <div className="glass-panel mx-auto max-w-xl p-6 text-center">
              <AlertTriangle className="mx-auto text-rose-300" size={34} />
              <h1 className="mt-4 text-2xl font-black">
                {t("admin.common.accessDenied")}
              </h1>
              <p className="mt-2 text-sm text-slate-300">
                {t("admin.ekyc.deniedDescription")}
              </p>
            </div>
          ) : (
            <>
              <div className="mb-6 flex flex-col justify-between gap-4 lg:flex-row lg:items-end">
                <div>
                  <span className="micro-badge">
                    <span className="status-dot cyan" />
                    {t("admin.ekyc.badge")}
                  </span>
                  <h1 className="mt-4 text-4xl font-black tracking-normal sm:text-5xl">
                    {t("admin.ekyc.title")}
                  </h1>
                  <p className="mt-3 max-w-2xl text-slate-300">
                    {t("admin.ekyc.description")}
                  </p>
                </div>
                <button
                  className="secondary-button"
                  disabled={isLoading}
                  onClick={() => loadRequests()}
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
                className="mb-5 grid gap-3 rounded-lg border border-white/10 bg-white/[0.04] p-4 lg:grid-cols-[1.5fr_1fr_1fr_1fr_0.8fr_auto]"
                onSubmit={applyFilters}
              >
                <div className="input-shell min-h-11">
                  <input
                    aria-label={t("admin.ekyc.searchLabel")}
                    defaultValue={queryFilter}
                    key={`q-${filterKey}`}
                    name="q"
                    placeholder={t("admin.ekyc.searchPlaceholder")}
                    type="search"
                  />
                </div>

                <div className="input-shell min-h-11">
                  <select
                    className="w-full border-0 bg-transparent text-white outline-0"
                    defaultValue={statusFilter}
                    key={`status-${filterKey}`}
                    name="status"
                  >
                    {STATUS_OPTIONS.map((option) => (
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
                    defaultValue={videoStatusFilter}
                    key={`video-${filterKey}`}
                    name="video_status"
                  >
                    {VIDEO_STATUS_OPTIONS.map((option) => (
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
                    defaultValue={faceDecisionFilter}
                    key={`face-${filterKey}`}
                    name="face_decision"
                  >
                    {FACE_DECISION_OPTIONS.map((option) => (
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
                    defaultValue={sortFilter}
                    key={`sort-${filterKey}`}
                    name="sort"
                  >
                    <option className="bg-slate-950 text-white" value="latest">
                      {t("admin.ekyc.filters.latest")}
                    </option>
                    <option className="bg-slate-950 text-white" value="oldest">
                      {t("admin.ekyc.filters.oldest")}
                    </option>
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
                    <h2 className="text-xl font-black">
                      {t("admin.ekyc.listTitle")}
                    </h2>
                    <p className="mt-1 text-sm text-slate-400">
                      {t("admin.ekyc.listSummary", {
                        end: pageEnd,
                        start: pageStart,
                        total: totalCount,
                      })}
                    </p>
                  </div>
                  <ShieldCheck className="text-cyan-200" size={24} />
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full min-w-[1040px] text-left text-sm">
                    <thead className="border-b border-white/10 text-xs uppercase text-slate-400">
                      <tr>
                        <th className="px-5 py-4">{t("admin.ekyc.table.user")}</th>
                        <th className="px-5 py-4">{t("admin.ekyc.table.ekycName")}</th>
                        <th className="px-5 py-4">{t("admin.ekyc.table.idNumber")}</th>
                        <th className="px-5 py-4">{t("admin.ekyc.table.ocr")}</th>
                        <th className="px-5 py-4">{t("admin.ekyc.table.video")}</th>
                        <th className="px-5 py-4">{t("admin.ekyc.table.face")}</th>
                        <th className="px-5 py-4">{t("admin.common.updated")}</th>
                        <th className="px-5 py-4">{t("admin.common.actions")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {isLoading ? (
                        <tr>
                          <td className="px-5 py-8 text-center text-slate-300" colSpan={8}>
                            {t("admin.ekyc.loading")}
                          </td>
                        </tr>
                      ) : requests.length ? (
                        requests.map((request) => (
                          <tr
                            className="cursor-pointer border-b border-white/10 transition hover:bg-cyan-400/5"
                            key={request.request_id}
                            onClick={() => openDetail(request.request_id)}
                          >
                            <td className="px-5 py-4">
                              <button
                                className="text-left"
                                onClick={(event) => {
                                  event.stopPropagation();
                                  openDetail(request.request_id);
                                }}
                                type="button"
                              >
                                <p className="font-bold text-white transition hover:text-cyan-200">
                                  {request.owner_full_name ||
                                    request.owner_email ||
                                    t("admin.common.unknown")}
                                </p>
                                <p className="mt-1 text-xs text-slate-400">
                                  {request.owner_email ?? request.user_id ?? "-"}
                                </p>
                              </button>
                            </td>
                            <td className="px-5 py-4 font-bold text-white">
                              {ekycDisplayField(request, "full_name") || "-"}
                            </td>
                            <td className="px-5 py-4 text-slate-300">
                              <div className="space-y-1">
                                <div>{ekycDisplayField(request, "id_number") || "-"}</div>
                                {request.duplicate_identity_detected ? (
                                  <div className="inline-flex items-center gap-1 rounded-full border border-amber-300/30 bg-amber-500/10 px-2 py-1 text-[11px] font-semibold text-amber-100">
                                    <AlertTriangle size={12} />
                                    Duplicate identity
                                  </div>
                                ) : null}
                              </div>
                            </td>
                            <td className="px-5 py-4">
                              <span className={statusClass(request.status)}>
                                {request.status}
                              </span>
                            </td>
                            <td className="px-5 py-4">
                              <span className={statusClass(request.video_status)}>
                                {request.video_status}
                              </span>
                            </td>
                            <td className="px-5 py-4">
                              <span className={statusClass(request.face_decision)}>
                                {request.face_decision ?? "-"}
                              </span>
                            </td>
                            <td className="px-5 py-4 text-slate-300">
                              {formatDate(request.updated_at, locale)}
                            </td>
                            <td className="px-5 py-4">
                              <div className="flex items-center gap-2">
                                <button
                                  className="secondary-button h-10 px-3"
                                  onClick={(event) => {
                                    event.stopPropagation();
                                    openDetail(request.request_id);
                                  }}
                                  type="button"
                                >
                                  <Eye size={15} />
                                  {t("admin.common.view")}
                                </button>
                                <button
                                  className="secondary-button h-10 px-3 text-rose-100 hover:border-rose-300/60 hover:bg-rose-500/15"
                                  disabled={deletingRequestId === request.request_id}
                                  onClick={(event) => {
                                    event.stopPropagation();
                                    deleteRecord(request);
                                  }}
                                  type="button"
                                >
                                  {deletingRequestId === request.request_id ? (
                                    <Loader2 className="animate-spin" size={15} />
                                  ) : (
                                    <Trash2 size={15} />
                                  )}
                                  {t("admin.common.deleteRecord")}
                                </button>
                              </div>
                            </td>
                          </tr>
                        ))
                      ) : (
                        <tr>
                          <td className="px-5 py-8 text-center text-slate-300" colSpan={8}>
                            {t("admin.ekyc.empty")}
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

              <DetailModal
                aiReviewRequestId={aiReviewRequestId}
                deletingRequestId={deletingRequestId}
                onApprove={approveRecord}
                onClose={() => setSelected(null)}
                onDelete={deleteRecord}
                onGenerateAiReview={generateAiReview}
                onReject={rejectRecord}
                onRetry={retryRecord}
                onSaveDocumentFields={saveDocumentFields}
                reviewingRequestId={reviewingRequestId}
                retryingRequestId={retryingRequestId}
                savingDocumentFieldsRequestId={savingDocumentFieldsRequestId}
                selected={selected}
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

function DetailModal({
  aiReviewRequestId,
  deletingRequestId,
  onApprove,
  onDelete,
  onGenerateAiReview,
  onReject,
  onRetry,
  onSaveDocumentFields,
  reviewingRequestId,
  retryingRequestId,
  savingDocumentFieldsRequestId,
  selected,
  onClose,
}: {
  aiReviewRequestId: string | null;
  deletingRequestId: string | null;
  onApprove: (request: EkycRequestAdminResponse) => void;
  onDelete: (request: EkycRequestAdminResponse) => void;
  onGenerateAiReview: (request: EkycRequestAdminResponse) => void;
  onReject: (request: EkycRequestAdminResponse) => void;
  onRetry: (request: EkycRequestAdminResponse) => void;
  onSaveDocumentFields: (
    request: EkycRequestAdminResponse,
    fields: AdminEkycDocumentFieldsPayload,
  ) => Promise<void>;
  reviewingRequestId: string | null;
  retryingRequestId: string | null;
  savingDocumentFieldsRequestId: string | null;
  selected: EkycRequestAdminResponse | null;
  onClose: () => void;
}) {
  const { locale, t } = useLanguage();
  const [visibleLogRequestId, setVisibleLogRequestId] = useState<string | null>(null);
  const [editingDocumentRequestId, setEditingDocumentRequestId] =
    useState<string | null>(null);

  if (!selected) {
    return null;
  }

  const showLogs = visibleLogRequestId === selected.request_id;
  const showDocumentEditor = editingDocumentRequestId === selected.request_id;

  return (
    <div
      aria-labelledby="ekyc-detail-title"
      aria-modal="true"
      className="fixed inset-0 z-[80] flex items-center justify-center bg-black/70 px-3 py-4 backdrop-blur-md sm:px-6 sm:py-8"
      onClick={onClose}
      role="dialog"
      >
        <section
        className="glass-panel ekyc-detail-modal-panel max-h-[88vh] w-full max-w-5xl overflow-y-auto p-0 shadow-[0_24px_90px_rgba(0,0,0,0.45)] [scrollbar-color:rgba(103,232,249,0.38)_rgba(15,23,42,0.72)] [scrollbar-width:thin]"
        onClick={(event) => event.stopPropagation()}
        style={{ overflowY: "auto" }}
      >
        <div className="sticky top-0 z-10 flex items-start justify-between gap-4 border-b border-white/10 bg-slate-950/90 p-5 backdrop-blur-xl">
          <div>
            <span className={statusClass(selected.face_decision)}>
              {selected.face_decision ?? t("admin.ekyc.noFaceResult")}
            </span>
            <h2 id="ekyc-detail-title" className="mt-4 text-2xl font-black">
              {t("admin.ekyc.detailTitle")}
            </h2>
            <p className="mt-2 break-all text-sm text-slate-300">
              {t("admin.ekyc.requestId", { id: selected.request_id })}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              aria-label={t("admin.common.closeDetailModal")}
              className="grid h-10 w-10 place-items-center rounded-full border border-rose-300/60 bg-rose-500/10 text-rose-100 transition hover:bg-rose-500/20"
              onClick={onClose}
              type="button"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        <div className="px-5 pb-5">
          <div className="mt-5 grid gap-3 sm:grid-cols-2">
            <MiniField
              label={t("admin.ekyc.detailFields.user")}
              value={selected.owner_email ?? selected.user_id}
            />
            <MiniField
              label={t("admin.ekyc.detailFields.request")}
              value={shortId(selected.request_id)}
            />
            <MiniField label={t("admin.ekyc.detailFields.ocrStatus")} value={selected.status} />
            <MiniField
              label={t("admin.ekyc.detailFields.videoStatus")}
              value={selected.video_status}
            />
            <MiniField
              label={t("admin.ekyc.detailFields.faceSimilarity")}
              value={
                selected.face_similarity === null || selected.face_similarity === undefined
                  ? "-"
                  : `${Math.round(selected.face_similarity * 100)}%`
              }
            />
            <MiniField label={t("admin.ekyc.detailFields.model")} value={selected.model_version} />
            <MiniField
              label={t("admin.ekyc.detailFields.created")}
              value={formatDate(selected.created_at, locale)}
            />
            <MiniField
              label={t("admin.ekyc.detailFields.updated")}
              value={formatDate(selected.updated_at, locale)}
            />
          </div>

          {selected.duplicate_identity_warning ? (
            <div className="mt-5 rounded-lg border border-amber-300/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
              <div className="flex items-start gap-2">
                <AlertTriangle className="mt-0.5 shrink-0" size={16} />
                <p>{selected.duplicate_identity_warning}</p>
              </div>
            </div>
          ) : null}

          <div className="mt-5 flex flex-col gap-3 rounded-lg border border-white/10 bg-slate-950/45 p-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex flex-wrap gap-3">
              <button
                className="secondary-button h-11 shrink-0 px-4"
                disabled={
                  aiReviewRequestId === selected.request_id ||
                  selected.status === "PENDING" ||
                  selected.status === "PROCESSING"
                }
                onClick={() => onGenerateAiReview(selected)}
                type="button"
              >
                {aiReviewRequestId === selected.request_id ? (
                  <Loader2 className="animate-spin" size={16} />
                ) : (
                  <Sparkles size={16} />
                )}
                AI review
              </button>
              <button
                className="secondary-button h-11 shrink-0 px-4"
                disabled={
                  retryingRequestId === selected.request_id ||
                  selected.status === "PENDING" ||
                  selected.status === "SUCCESS"
                }
                onClick={() => onRetry(selected)}
                type="button"
              >
                {retryingRequestId === selected.request_id ? (
                  <Loader2 className="animate-spin" size={16} />
                ) : (
                  <RotateCcw size={16} />
                )}
                {t("admin.common.retryAi")}
              </button>
              <button
                className="secondary-button h-11 shrink-0 px-4"
                onClick={() =>
                  setEditingDocumentRequestId((current) =>
                    current === selected.request_id ? null : selected.request_id,
                  )
                }
                type="button"
              >
                <Pencil size={16} />
                {showDocumentEditor ? "Dong sua" : "Sua thong tin"}
              </button>
              <button
                className="primary-button h-11 shrink-0 px-5"
                disabled={
                  reviewingRequestId === selected.request_id ||
                  selected.status === "SUCCESS"
                }
                onClick={() => onApprove(selected)}
                type="button"
              >
                {reviewingRequestId === selected.request_id ? (
                  <Loader2 className="animate-spin" size={16} />
                ) : (
                  <CheckCircle2 size={16} />
                )}
                {t("admin.common.approve")}
              </button>
              <button
                className="secondary-button h-11 shrink-0 px-4 text-rose-100 hover:border-rose-300/60 hover:bg-rose-500/15"
                disabled={
                  reviewingRequestId === selected.request_id ||
                  selected.status === "FAILED"
                }
                onClick={() => onReject(selected)}
                type="button"
              >
                {reviewingRequestId === selected.request_id ? (
                  <Loader2 className="animate-spin" size={16} />
                ) : (
                  <XCircle size={16} />
                )}
                {t("admin.common.reject")}
              </button>
            </div>
            <button
              className="secondary-button h-11 shrink-0 px-4 text-rose-100 hover:border-rose-300/60 hover:bg-rose-500/15 lg:ml-auto"
              disabled={deletingRequestId === selected.request_id}
              onClick={() => onDelete(selected)}
              type="button"
            >
              {deletingRequestId === selected.request_id ? (
                <Loader2 className="animate-spin" size={16} />
              ) : (
                <Trash2 size={16} />
              )}
              {t("admin.common.deleteRecord")}
            </button>
          </div>

          {showDocumentEditor ? (
            <DocumentFieldsEditor
              isSaving={savingDocumentFieldsRequestId === selected.request_id}
              key={selected.request_id}
              onCancel={() => setEditingDocumentRequestId(null)}
              onSave={(fields) => onSaveDocumentFields(selected, fields)}
              request={selected}
            />
          ) : null}

          <div className="mt-5 grid gap-4">
            <AdminAiReviewPanel
              loading={aiReviewRequestId === selected.request_id}
              review={selected.ai_admin_review}
            />
            <EkycMediaPreview requestId={selected.request_id} />

            <div className="rounded-lg border border-white/10 bg-slate-950/55 p-4">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <p className="text-sm font-black text-white">Log kỹ thuật</p>
                  <p className="mt-1 text-xs font-semibold text-slate-400">
                    OCR, video, voice, đường dẫn file
                  </p>
                </div>
                <button
                  className="secondary-button h-10 shrink-0 px-4"
                  onClick={() =>
                    setVisibleLogRequestId((current) =>
                      current === selected.request_id ? null : selected.request_id,
                    )
                  }
                  type="button"
                >
                  {showLogs ? <X size={15} /> : <Eye size={15} />}
                  {showLogs ? "Ẩn log" : "Xem log"}
                </button>
              </div>
            </div>

            {showLogs ? (
              <div className="grid gap-4">
                <JsonBlock
                  title={t("admin.ekyc.detailFields.confirmedInfo")}
                  value={selected.document_confirmed_fields}
                />
                <JsonBlock title={t("admin.ekyc.detailFields.rawOcr")} value={selected.ocr_result} />
                <JsonBlock
                  title={t("admin.ekyc.detailFields.videoResult")}
                  value={selected.video_result}
                />
                <JsonBlock
                  title={t("admin.ekyc.detailFields.voiceResult")}
                  value={selected.voice_result}
                />
                <div className="grid gap-3 rounded-lg border border-white/10 bg-slate-950/70 p-4">
                  <MiniField
                    label={t("admin.ekyc.detailFields.frontImagePath")}
                    value={selected.front_image_path}
                    wide
                  />
                  <MiniField
                    label={t("admin.ekyc.detailFields.backImagePath")}
                    value={selected.back_image_path}
                    wide
                  />
                  <MiniField
                    label={t("admin.ekyc.detailFields.videoPath")}
                    value={selected.video_path}
                    wide
                  />
                  <MiniField
                    label={t("admin.ekyc.detailFields.ocrError")}
                    value={selected.error_message}
                    wide
                  />
                  <MiniField
                    label={t("admin.ekyc.detailFields.videoError")}
                    value={selected.video_error_message}
                    wide
                  />
                </div>
              </div>
            ) : null}
          </div>
        </div>
      </section>
    </div>
  );
}

function DocumentFieldsEditor({
  isSaving,
  onCancel,
  onSave,
  request,
}: {
  isSaving: boolean;
  onCancel: () => void;
  onSave: (fields: AdminEkycDocumentFieldsPayload) => Promise<void>;
  request: EkycRequestAdminResponse;
}) {
  const [form, setForm] = useState<DocumentFieldsFormState>(() =>
    documentFieldsFormFromRequest(request),
  );

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void onSave(form);
  }

  return (
    <form
      className="mt-5 rounded-lg border border-cyan-300/20 bg-cyan-500/10 p-4"
      onSubmit={handleSubmit}
    >
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h3 className="text-sm font-black uppercase tracking-wide text-cyan-100">
            Sua thong tin giay to
          </h3>
          <p className="mt-1 text-xs font-semibold text-slate-400">
            Admin co the chinh lai thong tin OCR truoc khi approve ho so.
          </p>
        </div>
        <span className="status-pill">Manual edit</span>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {DOCUMENT_FIELD_CONFIG.map((field) => (
          <label className="grid gap-1.5" key={field.key}>
            <span className="text-xs font-bold uppercase tracking-wide text-slate-400">
              {field.label}
            </span>
            <span className="input-shell min-h-11">
              <input
                className="w-full"
                disabled={isSaving}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    [field.key]: event.target.value,
                  }))
                }
                value={form[field.key]}
              />
            </span>
          </label>
        ))}
      </div>

      <div className="mt-4 flex flex-wrap justify-end gap-3">
        <button
          className="secondary-button h-10 px-4"
          disabled={isSaving}
          onClick={onCancel}
          type="button"
        >
          Huy
        </button>
        <button className="primary-button h-10 px-4" disabled={isSaving} type="submit">
          {isSaving ? <Loader2 className="animate-spin" size={16} /> : <Pencil size={16} />}
          Luu thong tin
        </button>
      </div>
    </form>
  );
}

function aiReviewRecommendationClass(ketLuan?: AdminAiReview["ket_luan"]) {
  if (ketLuan === "PASS") {
    return "status-pill success";
  }
  if (ketLuan === "REJECT") {
    return "status-pill danger";
  }
  return "status-pill";
}

function aiReviewRiskClass(mucDoRuiRo?: AdminAiReview["muc_do_rui_ro"]) {
  if (mucDoRuiRo === "CAO") {
    return "status-pill danger";
  }
  if (mucDoRuiRo === "THẤP") {
    return "status-pill success";
  }
  return "status-pill";
}

function AdminAiReviewPanel({
  loading,
  review,
}: {
  loading: boolean;
  review?: AdminAiReview | null;
}) {
  if (loading) {
    return (
      <div className="rounded-lg border border-violet-300/20 bg-violet-500/10 p-4">
        <div className="flex items-center gap-2 text-sm text-violet-100">
          <Loader2 className="animate-spin" size={16} />
          Đang phân tích LLM...
        </div>
      </div>
    );
  }

  if (!review) {
    return (
      <div className="rounded-lg border border-dashed border-white/15 bg-slate-950/50 p-4 text-sm text-slate-400">
        Chưa có gợi ý LLM. Bấm <strong className="text-slate-200">AI review</strong> để
        nhận tóm tắt và đề xuất quyết định (hỗ trợ admin, không thay quyết định cuối).
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-lg border border-violet-300/25 bg-slate-950/72">
      <div className="border-b border-violet-300/15 bg-violet-500/10 p-4 sm:p-5">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex min-w-0 items-start gap-3">
            <div className="grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-violet-300/25 bg-violet-400/10 text-violet-100">
              <Sparkles size={18} />
            </div>
            <div className="min-w-0">
              <h3 className="text-sm font-black uppercase tracking-wide text-violet-100">
                Gợi ý LLM cho admin
              </h3>
              <p className="mt-1 text-xs text-slate-400">
                Chỉ là hỗ trợ ra quyết định, admin vẫn là người duyệt cuối.
              </p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <span className={aiReviewRecommendationClass(review.ket_luan)}>
              {review.ket_luan}
            </span>
            <span className={aiReviewRiskClass(review.muc_do_rui_ro)}>
              Rủi ro {review.muc_do_rui_ro}
            </span>
            <span className="status-pill">
              Độ tin cậy {Math.round((review.do_tin_cay ?? 0) * 100)}%
            </span>
          </div>
        </div>

        {review.tom_tat ? (
          <p className="mt-4 max-w-4xl text-sm leading-6 text-slate-100">
            {review.tom_tat}
          </p>
        ) : null}
      </div>

      {(review.khuyen_nghi_cho_admin || review.giai_thich) ? (
        <div className="grid gap-3 border-b border-white/10 p-4 sm:grid-cols-2 sm:p-5">
          {review.khuyen_nghi_cho_admin ? (
            <div className="rounded-lg border border-violet-300/20 bg-violet-500/10 p-4">
              <p className="text-xs font-bold uppercase tracking-wide text-violet-100">
                Khuyến nghị
              </p>
              <p className="mt-2 text-sm leading-6 text-slate-100">
                {review.khuyen_nghi_cho_admin}
              </p>
            </div>
          ) : null}
          {review.giai_thich ? (
            <div className="rounded-lg border border-white/10 bg-slate-900/70 p-4">
              <p className="text-xs font-bold uppercase tracking-wide text-slate-400">
                Giải thích
              </p>
              <p className="mt-2 text-sm leading-6 text-slate-300">
                {review.giai_thich}
              </p>
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="grid gap-3 p-4 sm:grid-cols-2 sm:p-5">
        <ReviewList title="Điểm tích cực" items={review.diem_tich_cuc} />
        <ReviewList title="Vấn đề phát hiện" items={review.van_de_phat_hien} />
        <ReviewList
          title="Cần admin kiểm tra"
          items={review.danh_sach_can_admin_kiem_tra}
        />
        <ReviewList title="Dữ liệu còn thiếu" items={review.du_lieu_con_thieu} />
      </div>

      {review.bang_chung?.length ? (
        <div className="border-t border-white/10 p-4 sm:p-5">
          <p className="text-xs font-bold uppercase tracking-wide text-slate-400">
            Bằng chứng
          </p>
          <ul className="mt-3 grid gap-3 text-sm text-slate-200 sm:grid-cols-2">
            {review.bang_chung.map((item) => (
              <li
                key={`${item.hang_muc}-${item.ket_qua}`}
                className="rounded-lg border border-white/10 bg-slate-900/72 p-3"
              >
                <p className="font-bold text-slate-100">{item.hang_muc}</p>
                <p className="mt-1 leading-6 text-slate-300">{item.ket_qua}</p>
                <p className="mt-2 text-xs font-semibold text-cyan-100">
                  Độ tin cậy {Math.round((item.do_tin_cay ?? 0) * 100)}%
                </p>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {review.error ? (
        <p className="border-t border-amber-300/20 bg-amber-500/10 px-4 py-3 text-xs text-amber-100 sm:px-5">
          LLM: {review.error}
        </p>
      ) : null}
    </div>
  );
}

function ReviewList({ title, items }: { title: string; items?: string[] }) {
  if (!items?.length) {
    return null;
  }
  return (
    <div className="rounded-lg border border-white/10 bg-slate-900/55 p-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">{title}</p>
      <ul className="mt-2 list-disc space-y-1 pl-4 text-sm text-slate-200">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

function EkycMediaPreview({ requestId }: { requestId: string }) {
  const { t } = useLanguage();
  const [mediaUrls, setMediaUrls] = useState<{
    back: string | null;
    front: string | null;
    liveness: string | null;
  }>({
    back: null,
    front: null,
    liveness: null,
  });
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState("");

  useEffect(() => {
    let isMounted = true;
    const objectUrls: string[] = [];

    async function loadMedia() {
      setIsLoading(true);
      setErrorMessage("");
      setMediaUrls({ back: null, front: null, liveness: null });

      try {
        const [frontBlob, backBlob, livenessBlob] = await Promise.all([
          getAdminEkycFileBlob(requestId, "front"),
          getAdminEkycFileBlob(requestId, "back"),
          getAdminEkycFileBlob(requestId, "liveness"),
        ]);
        const nextUrls = {
          back: backBlob ? URL.createObjectURL(backBlob) : null,
          front: frontBlob ? URL.createObjectURL(frontBlob) : null,
          liveness: livenessBlob ? URL.createObjectURL(livenessBlob) : null,
        };
        Object.values(nextUrls).forEach((url) => {
          if (url) {
            objectUrls.push(url);
          }
        });

        if (isMounted) {
          setMediaUrls(nextUrls);
        } else {
          objectUrls.forEach((url) => URL.revokeObjectURL(url));
        }
      } catch (error) {
        if (isMounted) {
          setErrorMessage(formatError(error));
        }
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    }

    loadMedia();

    return () => {
      isMounted = false;
      objectUrls.forEach((url) => URL.revokeObjectURL(url));
    };
  }, [requestId]);

  return (
    <section className="mt-5 rounded-lg border border-white/10 bg-slate-950/70 p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-black text-white">
            {t("admin.ekyc.mediaTitle")}
          </h3>
          <p className="mt-1 text-xs font-semibold text-slate-400">
            {t("admin.ekyc.mediaDescription")}
          </p>
        </div>
        {isLoading ? <Loader2 className="animate-spin text-cyan-200" size={18} /> : null}
      </div>

      {errorMessage ? (
        <p className="mt-4 rounded-lg border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-xs font-semibold text-rose-100">
          {errorMessage}
        </p>
      ) : null}

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <MediaImageCard label={t("admin.ekyc.frontDocument")} url={mediaUrls.front} />
        <MediaImageCard label={t("admin.ekyc.backDocument")} url={mediaUrls.back} />
      </div>
      <div className="mt-4">
        <MediaVideoCard url={mediaUrls.liveness} />
      </div>
    </section>
  );
}

function MediaImageCard({
  label,
  url,
}: {
  label: string;
  url: string | null;
}) {
  const { t } = useLanguage();

  return (
    <div className="overflow-hidden rounded-lg border border-white/10 bg-slate-950/60">
      <div className="border-b border-white/10 px-3 py-2 text-xs font-black uppercase text-slate-400">
        {label}
      </div>
      <div className="grid min-h-56 place-items-center bg-black/25 p-3">
        {url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            alt={label}
            className="max-h-[380px] w-full rounded-md object-contain"
            src={url}
          />
        ) : (
          <span className="text-sm font-semibold text-slate-500">
            {t("admin.ekyc.noImage")}
          </span>
        )}
      </div>
    </div>
  );
}

function MediaVideoCard({ url }: { url: string | null }) {
  const { t } = useLanguage();

  return (
    <div className="overflow-hidden rounded-lg border border-white/10 bg-slate-950/60">
      <div className="border-b border-white/10 px-3 py-2 text-xs font-black uppercase text-slate-400">
        {t("admin.ekyc.livenessVideo")}
      </div>
      <div className="grid min-h-64 place-items-center bg-black/25 p-3">
        {url ? (
          <video
            className="max-h-[520px] w-full rounded-md"
            controls
            preload="metadata"
            src={url}
          />
        ) : (
          <span className="text-sm font-semibold text-slate-500">
            {t("admin.ekyc.noVideo")}
          </span>
        )}
      </div>
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
      className={`rounded-lg border border-white/10 bg-slate-950/50 p-3 ${wide ? "sm:col-span-2" : ""
        }`}
    >
      <p className="text-xs font-black uppercase text-slate-500">{label}</p>
      <p className="mt-2 break-words text-sm font-bold text-slate-100">
        {value || "-"}
      </p>
    </div>
  );
}

function JsonBlock({
  title,
  value,
}: {
  title: string;
  value?: Record<string, unknown> | null;
}) {
  return (
    <div className="mt-5 rounded-lg border border-white/10 bg-slate-950/70 p-4">
      <h3 className="text-sm font-black text-white">{title}</h3>
      <pre className="mt-3 max-h-72 overflow-auto whitespace-pre-wrap break-words text-xs leading-5 text-slate-300">
        {value ? JSON.stringify(value, null, 2) : "-"}
      </pre>
    </div>
  );
}
