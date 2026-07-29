"use client";

import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { AppHeader } from "@/components/site/AppHeader";
import { useLanguage } from "@/contexts/LanguageContext";
import { ApiError } from "@/lib/api";
import {
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  type NotificationItem,
} from "@/services/notifications.service";
import { Bell, CheckCheck, Inbox, Loader2, RefreshCcw } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

const FILTERS = [
  { labelKey: "notificationsPage.filters.all", value: "all" },
  { labelKey: "notificationsPage.filters.unread", value: "unread" },
  { labelKey: "notificationsPage.filters.ekyc", value: "ekyc" },
  { labelKey: "notificationsPage.filters.system", value: "system" },
] as const;

type FilterValue = (typeof FILTERS)[number]["value"];

function formatError(error: unknown, fallback: string) {
  if (error instanceof ApiError || error instanceof Error) {
    return error.message;
  }
  return fallback;
}

function formatDate(value: string, locale: string) {
  return new Intl.DateTimeFormat(locale, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function notificationHref(notification: NotificationItem) {
  const href = notification.data?.href;
  return typeof href === "string" && href.startsWith("/") ? href : "#";
}

function isEkycNotification(notification: NotificationItem) {
  return notification.type.startsWith("ekyc_");
}

export default function NotificationsPage() {
  const { locale, t } = useLanguage();
  const [activeFilter, setActiveFilter] = useState<FilterValue>("all");
  const [errorMessage, setErrorMessage] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isMarkingAll, setIsMarkingAll] = useState(false);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);

  const loadNotifications = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage("");
    try {
      const response = await listNotifications({
        limit: 100,
        unreadOnly: activeFilter === "unread",
      });
      setNotifications(response.data);
      setUnreadCount(response.unread_count);
    } catch (error) {
      setErrorMessage(
        formatError(error, t("notificationsPage.errors.loadFailed")),
      );
      setNotifications([]);
      setUnreadCount(0);
    } finally {
      setIsLoading(false);
    }
  }, [activeFilter, t]);

  useEffect(() => {
    void Promise.resolve().then(loadNotifications);
  }, [loadNotifications]);

  const visibleNotifications = useMemo(() => {
    if (activeFilter === "ekyc") {
      return notifications.filter(isEkycNotification);
    }
    if (activeFilter === "system") {
      return notifications.filter((notification) => !isEkycNotification(notification));
    }
    return notifications;
  }, [activeFilter, notifications]);

  const readNotification = async (notification: NotificationItem) => {
    if (notification.read_at) {
      return;
    }
    try {
      const updatedNotification = await markNotificationRead(notification.id);
      setNotifications((current) =>
        current.map((item) =>
          item.id === notification.id ? updatedNotification : item,
        ),
      );
      setUnreadCount((current) => Math.max(current - 1, 0));
    } catch (error) {
      setErrorMessage(
        formatError(error, t("notificationsPage.errors.loadFailed")),
      );
    }
  };

  const markAllRead = async () => {
    setIsMarkingAll(true);
    setErrorMessage("");
    try {
      await markAllNotificationsRead();
      setUnreadCount(0);
      setNotifications((current) =>
        current.map((notification) => ({
          ...notification,
          read_at: notification.read_at ?? new Date().toISOString(),
        })),
      );
    } catch (error) {
      setErrorMessage(
        formatError(error, t("notificationsPage.errors.loadFailed")),
      );
    } finally {
      setIsMarkingAll(false);
    }
  };

  return (
    <ProtectedRoute>
      <main className="min-h-screen bg-[#030712] text-white">
        <div className="vintrade-bg" />
        <AppHeader />

        <section className="relative z-10 mx-auto max-w-[1120px] px-4 py-8 sm:px-6 lg:px-8">
          <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <p className="text-xs font-black uppercase tracking-[0.26em] text-cyan-200">
                {t("notificationsPage.eyebrow")}
              </p>
              <h1 className="mt-2 text-3xl font-black text-white">
                {t("notificationsPage.title")}
              </h1>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <button
                className="inline-flex h-10 items-center gap-2 rounded-lg border border-white/10 bg-white/[0.04] px-3 text-sm font-bold text-slate-100 transition hover:border-cyan-300/35 hover:bg-cyan-400/10 disabled:cursor-not-allowed disabled:opacity-60"
                disabled={isLoading}
                onClick={loadNotifications}
                type="button"
              >
                <RefreshCcw size={16} />
                {t("notificationsPage.refresh")}
              </button>
              <button
                className="inline-flex h-10 items-center gap-2 rounded-lg border border-cyan-300/30 bg-cyan-400/10 px-3 text-sm font-bold text-cyan-100 transition hover:border-cyan-200/60 hover:bg-cyan-400/15 disabled:cursor-not-allowed disabled:opacity-60"
                disabled={isMarkingAll || unreadCount === 0}
                onClick={markAllRead}
                type="button"
              >
                {isMarkingAll ? (
                  <Loader2 className="animate-spin" size={16} />
                ) : (
                  <CheckCheck size={16} />
                )}
                {t("notificationsPage.markAllRead")}
              </button>
            </div>
          </div>

          <div className="mb-5 flex flex-wrap gap-2">
            {FILTERS.map((filter) => (
              <button
                className={`h-10 rounded-lg border px-4 text-sm font-black transition ${
                  activeFilter === filter.value
                    ? "border-cyan-300/50 bg-cyan-400/15 text-cyan-100"
                    : "border-white/10 bg-white/[0.04] text-slate-300 hover:border-cyan-300/35 hover:bg-cyan-400/10"
                }`}
                key={filter.value}
                onClick={() => setActiveFilter(filter.value)}
                type="button"
              >
                {t(filter.labelKey)}
              </button>
            ))}
          </div>

          {errorMessage ? (
            <div className="mb-4 rounded-lg border border-rose-400/25 bg-rose-500/10 px-4 py-3 text-sm font-bold text-rose-100">
              {errorMessage}
            </div>
          ) : null}

          <div className="glass-panel overflow-hidden">
            <div className="flex items-center justify-between border-b border-white/10 px-5 py-4">
              <div className="flex items-center gap-3">
                <span className="grid h-10 w-10 place-items-center rounded-lg bg-cyan-400/10 text-cyan-200">
                  <Bell size={18} />
                </span>
                <div>
                  <p className="text-sm font-black text-white">
                    {t("notificationsPage.inbox")}
                  </p>
                  <p className="text-xs font-semibold text-slate-400">
                    {t("notificationsPage.unreadCount", { count: unreadCount })}
                  </p>
                </div>
              </div>
            </div>

            {isLoading ? (
              <div className="grid min-h-[260px] place-items-center px-4 py-12">
                <div className="flex items-center gap-3 text-sm font-bold text-cyan-100">
                  <Loader2 className="animate-spin" size={18} />
                  {t("notificationsPage.loading")}
                </div>
              </div>
            ) : visibleNotifications.length ? (
              <div className="divide-y divide-white/10">
                {visibleNotifications.map((notification) => {
                  const href = notificationHref(notification);
                  const content = (
                    <div className="flex gap-4 px-5 py-4 transition hover:bg-cyan-400/[0.06]">
                      <span
                        className={`mt-2 h-2.5 w-2.5 shrink-0 rounded-full ${
                          notification.read_at ? "bg-white/20" : "bg-cyan-300"
                        }`}
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
                          <p className="font-black text-white">{notification.title}</p>
                          <p className="text-xs font-semibold text-slate-500">
                            {formatDate(
                              notification.created_at,
                              locale === "vi" ? "vi-VN" : "en-US",
                            )}
                          </p>
                        </div>
                        <p className="mt-2 text-sm font-semibold leading-6 text-slate-300">
                          {notification.message}
                        </p>
                      </div>
                    </div>
                  );

                  if (href === "#") {
                    return (
                      <button
                        className="block w-full text-left"
                        key={notification.id}
                        onClick={() => readNotification(notification)}
                        type="button"
                      >
                        {content}
                      </button>
                    );
                  }

                  return (
                    <Link
                      href={href}
                      key={notification.id}
                      onClick={() => readNotification(notification)}
                    >
                      {content}
                    </Link>
                  );
                })}
              </div>
            ) : (
              <div className="grid min-h-[260px] place-items-center px-4 py-12 text-center">
                <div>
                  <Inbox className="mx-auto text-cyan-200" size={34} />
                  <p className="mt-3 text-sm font-black text-white">
                    {t("notificationsPage.empty")}
                  </p>
                </div>
              </div>
            )}
          </div>
        </section>
      </main>
    </ProtectedRoute>
  );
}
