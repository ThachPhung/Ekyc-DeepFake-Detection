"use client";

import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { AppHeader } from "@/components/site/AppHeader";
import { useAuth } from "@/contexts/AuthContext";
import { useLanguage } from "@/contexts/LanguageContext";
import { ApiError } from "@/lib/api";
import type { EkycStatus, UserPublic, UserRole } from "@/services/auth.service";
import {
  deleteUser,
  listUsers,
  updateUser,
  type UpdateUserPayload,
} from "@/services/users.service";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Loader2,
  Pencil,
  RefreshCcw,
  ShieldCheck,
  Trash2,
  UserCog,
  X,
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";

const PAGE_SIZE = 20;

type UserFormState = {
  id: string | null;
  email: string;
  full_name: string;
  is_active: boolean;
  is_superuser: boolean;
  role: UserRole;
};

const emptyForm: UserFormState = {
  id: null,
  email: "",
  full_name: "",
  is_active: true,
  is_superuser: false,
  role: "user",
};

function formatError(error: unknown) {
  if (error instanceof ApiError || error instanceof Error) {
    return error.message;
  }
  return "Unable to complete user request.";
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

function roleLabel(role: UserRole, t: (key: string) => string) {
  if (role === "ekyc_reviewer") {
    return t("admin.common.staffReviewer");
  }
  return t("admin.common.user");
}

function ekycStatusLabel(status: EkycStatus | null | undefined, t: (key: string) => string) {
  if (!status) {
    return t("admin.users.ekycStatuses.notStarted");
  }
  return t(`admin.users.ekycStatuses.${status}`);
}

function ekycStatusClass(status: EkycStatus | null | undefined) {
  if (status === "SUCCESS") {
    return "status-pill success";
  }
  if (status === "FAILED") {
    return "status-pill danger";
  }
  return "status-pill";
}

function getInitials(user: UserPublic) {
  const source = user.full_name?.trim() || user.email;
  return source
    .split(/[.\s@_-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");
}

function toEditForm(user: UserPublic): UserFormState {
  return {
    id: user.id,
    email: user.email,
    full_name: user.full_name ?? "",
    is_active: user.is_active,
    is_superuser: user.is_superuser,
    role: user.role,
  };
}

export default function AdminUsersPage() {
  const { user: currentUser, refreshMe } = useAuth();
  const { locale, t } = useLanguage();
  const [users, setUsers] = useState<UserPublic[]>([]);
  const [form, setForm] = useState<UserFormState>(emptyForm);
  const [query, setQuery] = useState("");
  const [totalCount, setTotalCount] = useState(0);
  const [page, setPage] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  const isEditing = Boolean(form.id);
  const pageCount = Math.max(1, Math.ceil(totalCount / PAGE_SIZE));
  const pageStart = totalCount === 0 ? 0 : page * PAGE_SIZE + 1;
  const pageEnd = Math.min((page + 1) * PAGE_SIZE, totalCount);

  const filteredUsers = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) {
      return users;
    }

    return users.filter((user) =>
      [user.email, user.full_name ?? "", user.id]
        .join(" ")
        .toLowerCase()
        .includes(needle),
    );
  }, [query, users]);

  const activeCount = users.filter((item) => item.is_active).length;
  const adminCount = users.filter((item) => item.is_superuser).length;
  const reviewerCount = users.filter((item) => item.role === "ekyc_reviewer").length;

  async function loadUsers(targetPage = page) {
    setIsLoading(true);
    setErrorMessage("");
    try {
      const response = await listUsers(targetPage * PAGE_SIZE, PAGE_SIZE);
      setUsers(response.data);
      setTotalCount(response.count);
    } catch (error) {
      setErrorMessage(formatError(error));
    } finally {
      setIsLoading(false);
    }
  }

  function resetForm() {
    setForm(emptyForm);
    setSuccessMessage("");
    setErrorMessage("");
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSaving(true);
    setErrorMessage("");
    setSuccessMessage("");

    try {
      if (isEditing && form.id) {
        const payload: UpdateUserPayload = {
          is_active: form.is_active,
          is_superuser: form.is_superuser,
          role: form.is_superuser ? "user" : form.role,
        };
        const updated = await updateUser(form.id, payload);
        setUsers((items) =>
          items.map((item) => (item.id === updated.id ? updated : item)),
        );
        if (updated.id === currentUser?.id) {
          await refreshMe();
        }
        setSuccessMessage(t("admin.users.userUpdated"));
        setForm(emptyForm);
      }
    } catch (error) {
      setErrorMessage(formatError(error));
    } finally {
      setIsSaving(false);
    }
  }

  async function handleDelete(targetUser: UserPublic) {
    const confirmed = window.confirm(
      t("admin.users.deleteConfirm", { email: targetUser.email }),
    );

    if (!confirmed) {
      return;
    }

    setDeletingId(targetUser.id);
    setErrorMessage("");
    setSuccessMessage("");

    try {
      await deleteUser(targetUser.id);
      setUsers((items) => items.filter((item) => item.id !== targetUser.id));
      setTotalCount((count) => Math.max(count - 1, 0));
      if (form.id === targetUser.id) {
        setForm(emptyForm);
      }
      setSuccessMessage(t("admin.users.userDeleted"));
    } catch (error) {
      setErrorMessage(formatError(error));
    } finally {
      setDeletingId(null);
    }
  }

  useEffect(() => {
    let isMounted = true;

    listUsers(page * PAGE_SIZE, PAGE_SIZE)
      .then((response) => {
        if (isMounted) {
          setUsers(response.data);
          setTotalCount(response.count);
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
  }, [page]);

  return (
    <ProtectedRoute>
      <main className="min-h-screen overflow-hidden bg-[#030712] text-white">
        <div className="vintrade-bg" />
        <AppHeader />
        <section className="relative z-10 mx-auto max-w-[1480px] px-4 py-8 sm:px-6 lg:px-8">
          {!currentUser?.is_superuser ? (
            <div className="glass-panel mx-auto max-w-xl p-6 text-center">
              <AlertTriangle className="mx-auto text-rose-300" size={34} />
              <h1 className="mt-4 text-2xl font-black">
                {t("admin.common.accessDenied")}
              </h1>
              <p className="mt-2 text-sm text-slate-300">
                {t("admin.users.deniedDescription")}
              </p>
            </div>
          ) : (
            <>
              <div className="mb-6 flex flex-col justify-between gap-4 lg:flex-row lg:items-end">
                <div>
                  <span className="micro-badge">
                    <span className="status-dot cyan" />
                    {t("admin.users.badge")}
                  </span>
                  <h1 className="mt-4 text-4xl font-black tracking-normal sm:text-5xl">
                    {t("admin.users.title")}
                  </h1>
                  <p className="mt-3 max-w-2xl text-slate-300">
                    {t("admin.users.description")}
                  </p>
                </div>
                <button
                  className="secondary-button"
                  disabled={isLoading}
                  onClick={() => loadUsers()}
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

              <div className="mb-5 grid gap-3 md:grid-cols-4">
                <MetricCard label={t("admin.users.metrics.totalUsers")} value={totalCount} />
                <MetricCard
                  label={t("admin.users.metrics.activeShown")}
                  value={activeCount}
                  tone="success"
                />
                <MetricCard
                  label={t("admin.users.metrics.reviewersShown")}
                  value={reviewerCount}
                  tone="reviewer"
                />
                <MetricCard
                  label={t("admin.users.metrics.adminsShown")}
                  value={adminCount}
                  tone="admin"
                />
              </div>

              {errorMessage ? (
                <AlertBox tone="danger" message={errorMessage} />
              ) : null}
              {successMessage ? (
                <AlertBox tone="success" message={successMessage} />
              ) : null}

              <div className="glass-panel overflow-hidden">
                  <div className="flex flex-col gap-4 border-b border-white/10 p-5 md:flex-row md:items-center md:justify-between">
                    <div>
                      <h2 className="text-xl font-black">
                        {t("admin.users.directory")}
                      </h2>
                      <p className="mt-1 text-sm text-slate-400">
                        {t("admin.users.directorySummary", {
                          end: pageEnd,
                          filtered: filteredUsers.length,
                          shown: users.length,
                          start: pageStart,
                          total: totalCount,
                        })}
                      </p>
                    </div>
                    <div className="input-shell min-h-11 w-full md:max-w-sm">
                      <input
                        aria-label={t("admin.users.searchLabel")}
                        onChange={(event) => setQuery(event.target.value)}
                        placeholder={t("admin.users.searchPlaceholder")}
                        type="search"
                        value={query}
                      />
                    </div>
                  </div>

                  <div className="overflow-x-auto">
                    <table className="w-full min-w-[1040px] text-left text-sm">
                      <thead className="border-b border-white/10 text-xs uppercase text-slate-400">
                        <tr>
                          <th className="px-5 py-4">{t("admin.users.table.user")}</th>
                          <th className="px-5 py-4">{t("admin.users.table.ekycStatus")}</th>
                          <th className="px-5 py-4">{t("admin.common.status")}</th>
                          <th className="px-5 py-4">{t("admin.users.table.role")}</th>
                          <th className="px-5 py-4">{t("admin.common.created")}</th>
                          <th className="px-5 py-4">{t("admin.common.actions")}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {isLoading ? (
                          <tr>
                            <td className="px-5 py-8 text-center text-slate-300" colSpan={6}>
                              {t("admin.users.loading")}
                            </td>
                          </tr>
                        ) : filteredUsers.length ? (
                          filteredUsers.map((item) => (
                            <tr
                              className="border-b border-white/10 transition hover:bg-cyan-400/5"
                              key={item.id}
                            >
                              <td className="px-5 py-4">
                                <div className="flex items-center gap-3">
                                  <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg border border-cyan-300/25 bg-cyan-400/10 text-xs font-black text-cyan-100">
                                    {getInitials(item) || "U"}
                                  </span>
                                  <div>
                                    <p className="font-bold text-white">
                                      {item.full_name || t("admin.common.noName")}
                                    </p>
                                    <p className="mt-1 text-xs text-slate-400">
                                      {item.email}
                                    </p>
                                  </div>
                                </div>
                              </td>
                              <td className="px-5 py-4">
                                <span className={ekycStatusClass(item.ekyc_status)}>
                                  {ekycStatusLabel(item.ekyc_status, t)}
                                </span>
                              </td>
                              <td className="px-5 py-4">
                                <span
                                  className={`status-pill ${
                                    item.is_active ? "success" : "danger"
                                  }`}
                                >
                                  {item.is_active
                                    ? t("admin.common.active")
                                    : t("admin.common.inactive")}
                                </span>
                              </td>
                              <td className="px-5 py-4">
                                <span
                                  className={`status-pill ${
                                    item.is_superuser ? "success" : ""
                                  }`}
                                >
                                  {item.is_superuser
                                    ? t("admin.common.systemAdmin")
                                    : roleLabel(item.role, t)}
                                </span>
                              </td>
                              <td className="px-5 py-4 text-slate-300">
                                {formatDate(item.created_at, locale)}
                              </td>
                              <td className="px-5 py-4">
                                <div className="flex gap-2">
                                  <button
                                    className="secondary-button h-10 px-3"
                                    onClick={() => setForm(toEditForm(item))}
                                    title={t("admin.users.editUser")}
                                    type="button"
                                  >
                                    <Pencil size={15} />
                                  </button>
                                  <button
                                    className="secondary-button h-10 px-3 text-rose-100"
                                    disabled={
                                      deletingId === item.id ||
                                      item.id === currentUser.id
                                    }
                                    onClick={() => handleDelete(item)}
                                    title={
                                      item.id === currentUser.id
                                        ? t("admin.users.cannotDeleteSelf")
                                        : t("admin.users.deleteUser")
                                    }
                                    type="button"
                                  >
                                    {deletingId === item.id ? (
                                      <Loader2 className="animate-spin" size={15} />
                                    ) : (
                                      <Trash2 size={15} />
                                    )}
                                  </button>
                                </div>
                              </td>
                            </tr>
                          ))
                        ) : (
                          <tr>
                            <td className="px-5 py-8 text-center text-slate-300" colSpan={6}>
                              {t("admin.users.empty")}
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

              {isEditing ? (
                <UserEditModal
                  form={form}
                  isSaving={isSaving}
                  onCancel={resetForm}
                  onChange={setForm}
                  onSubmit={handleSubmit}
                />
              ) : null}
            </>
          )}
        </section>
      </main>
    </ProtectedRoute>
  );
}

function MetricCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone?: "success" | "admin" | "reviewer";
}) {
  const iconClass =
    tone === "success"
      ? "text-emerald-300"
      : tone === "admin"
        ? "text-violet-200"
        : tone === "reviewer"
          ? "text-amber-200"
          : "text-cyan-200";

  return (
    <div className="glass-panel p-5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-bold text-slate-400">{label}</p>
          <p className="mt-2 text-3xl font-black text-white">{value}</p>
        </div>
        <UserCog className={iconClass} size={28} />
      </div>
    </div>
  );
}

function AlertBox({
  message,
  tone,
}: {
  message: string;
  tone: "danger" | "success";
}) {
  const isSuccess = tone === "success";
  return (
    <div
      className={`mb-5 flex items-center gap-3 rounded-lg border px-4 py-3 text-sm font-semibold ${
        isSuccess
          ? "border-emerald-400/30 bg-emerald-500/10 text-emerald-100"
          : "border-rose-400/30 bg-rose-500/10 text-rose-100"
      }`}
    >
      {isSuccess ? <CheckCircle2 size={18} /> : <AlertTriangle size={18} />}
      {message}
    </div>
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

function UserEditModal({
  form,
  isSaving,
  onCancel,
  onChange,
  onSubmit,
}: {
  form: UserFormState;
  isSaving: boolean;
  onCancel: () => void;
  onChange: (form: UserFormState) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  const { t } = useLanguage();

  return (
    <div
      aria-labelledby="admin-user-edit-title"
      aria-modal="true"
      className="fixed inset-0 z-50 grid place-items-center bg-slate-950/75 px-4 py-6 backdrop-blur-sm"
      role="dialog"
    >
      <button
        aria-label={t("admin.users.editor.close")}
        className="absolute inset-0 cursor-default"
        onClick={onCancel}
        type="button"
      />
      <section className="glass-panel relative z-10 max-h-[calc(100vh-3rem)] w-full max-w-2xl overflow-y-auto p-5 shadow-2xl">
        <div className="flex items-start justify-between gap-4">
          <div>
            <span className="micro-badge">
              <ShieldCheck size={14} />
              {t("admin.users.editor.badge")}
            </span>
            <h2 id="admin-user-edit-title" className="mt-4 text-2xl font-black">
              {t("admin.users.editor.title")}
            </h2>
            <p className="mt-2 text-sm text-slate-300">
              {t("admin.users.editor.description")}
            </p>
          </div>
          <button
            className="secondary-button h-10 px-3"
            onClick={onCancel}
            title={t("admin.users.editor.close")}
            type="button"
          >
            <X size={16} />
          </button>
        </div>

        <form className="mt-6 grid gap-4" onSubmit={onSubmit}>
          <div>
            <label className="form-label" htmlFor="admin-user-id">
              {t("admin.users.editor.userId")}
            </label>
            <div className="input-shell">
              <input
                id="admin-user-id"
                onChange={() => undefined}
                readOnly
                type="text"
                value={form.id ?? ""}
              />
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="form-label" htmlFor="admin-user-email">
                {t("profile.email")}
              </label>
              <div className="input-shell">
                <input
                  autoComplete="email"
                  id="admin-user-email"
                  onChange={() => undefined}
                  placeholder="user@example.com"
                  readOnly
                  required
                  type="email"
                  value={form.email}
                />
              </div>
            </div>

            <div>
              <label className="form-label" htmlFor="admin-user-full-name">
                {t("admin.users.editor.username")}
              </label>
              <div className="input-shell">
                <input
                  autoComplete="name"
                  id="admin-user-full-name"
                  onChange={() => undefined}
                  placeholder={t("admin.users.editor.displayName")}
                  readOnly
                  type="text"
                  value={form.full_name}
                />
              </div>
            </div>
          </div>

          <div>
            <label className="form-label" htmlFor="admin-user-role">
              {t("admin.users.editor.staffAccess")}
            </label>
            <div className="input-shell">
              <select
                className="w-full border-0 bg-transparent text-white outline-0"
                disabled={form.is_superuser}
                id="admin-user-role"
                onChange={(event) =>
                  onChange({ ...form, role: event.target.value as UserRole })
                }
                value={form.role}
              >
                <option className="bg-slate-950 text-white" value="user">
                  {t("admin.common.user")}
                </option>
                <option
                  className="bg-slate-950 text-white"
                  value="ekyc_reviewer"
                >
                  {t("admin.common.staffReviewer")}
                </option>
              </select>
            </div>
            {form.is_superuser ? (
              <p className="mt-2 text-xs font-semibold text-amber-200">
                {t("admin.users.editor.inheritedReviewAccess")}
              </p>
            ) : null}
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <ToggleField
              checked={form.is_active}
              label={t("admin.common.active")}
              onChange={(checked) => onChange({ ...form, is_active: checked })}
            />
            <ToggleField
              checked={form.is_superuser}
              label={t("admin.common.systemAdmin")}
              onChange={(checked) =>
                onChange({
                  ...form,
                  is_superuser: checked,
                  role: checked ? "user" : form.role,
                })
              }
            />
          </div>

          <div className="flex flex-col-reverse gap-3 pt-2 sm:flex-row sm:justify-end">
            <button
              className="secondary-button justify-center"
              disabled={isSaving}
              onClick={onCancel}
              type="button"
            >
              {t("admin.common.cancel")}
            </button>
            <button
              className="primary-button justify-center"
              disabled={isSaving}
              type="submit"
            >
              {isSaving ? (
                <Loader2 className="animate-spin" size={17} />
              ) : (
                <ShieldCheck size={17} />
              )}
              {t("admin.common.saveChanges")}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}

function ToggleField({
  checked,
  label,
  onChange,
}: {
  checked: boolean;
  label: string;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="flex min-h-14 cursor-pointer items-center justify-between gap-3 rounded-lg border border-white/10 bg-slate-950/50 px-4">
      <span className="text-sm font-black text-slate-100">{label}</span>
      <input
        checked={checked}
        className="h-5 w-5 accent-cyan-400"
        onChange={(event) => onChange(event.target.checked)}
        type="checkbox"
      />
    </label>
  );
}
