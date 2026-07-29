"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { Bell, CheckCheck, ChevronDown, Inbox, LogOut, UserRound } from "lucide-react";
import { LanguageDropdown } from "@/components/i18n/LanguageDropdown";
import { useAuth } from "@/contexts/AuthContext";
import { useLanguage } from "@/contexts/LanguageContext";
import {
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  type NotificationItem,
} from "@/services/notifications.service";

const appMenuItems = [
  { labelKey: "header.menu.trading", href: "/trading" },
  { labelKey: "header.menu.markets", href: "/markets" },
  { labelKey: "header.menu.ekyc", href: "/ekyc" },
  { labelKey: "header.menu.portfolio", href: "#" },
  { labelKey: "header.menu.aiSignals", href: "#" },
];

type AppHeaderProps = {
  focusMode?: boolean;
};

export function AppHeader({ focusMode = false }: AppHeaderProps) {
  const pathname = usePathname();
  const { logout, user } = useAuth();
  const { t } = useLanguage();
  const [isAccountMenuOpen, setIsAccountMenuOpen] = useState(false);
  const [isNotificationMenuOpen, setIsNotificationMenuOpen] = useState(false);
  const [isLoadingNotifications, setIsLoadingNotifications] = useState(false);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const accountMenuRef = useRef<HTMLDivElement>(null);
  const notificationMenuRef = useRef<HTMLDivElement>(null);
  const isSystemAdmin = Boolean(user?.is_superuser);
  const canReviewEkyc =
    isSystemAdmin || user?.role === "ekyc_reviewer";
  const showNotifications = Boolean(user && !isSystemAdmin && !focusMode);
  const menuItems = [
    ...(isSystemAdmin ? [] : appMenuItems),
    ...(isSystemAdmin
      ? [
          { labelKey: "header.menu.overview", href: "/admin" },
          { labelKey: "header.menu.adminUsers", href: "/admin/users" },
          { labelKey: "header.menu.auditLogs", href: "/admin/audit-logs" },
          { labelKey: "header.menu.settings", href: "/admin/settings" },
        ]
      : []),
    ...(canReviewEkyc ? [{ labelKey: "header.menu.adminEkyc", href: "/admin/ekyc" }] : []),
  ];
  const displayName =
    user?.full_name?.trim() || user?.email?.split("@")[0] || t("common.userAccount");

  const refreshNotifications = useCallback(async () => {
    if (!showNotifications) {
      setNotifications([]);
      setUnreadCount(0);
      return;
    }

    setIsLoadingNotifications(true);
    try {
      const response = await listNotifications({ limit: 5 });
      setNotifications(response.data);
      setUnreadCount(response.unread_count);
    } catch {
      setNotifications([]);
      setUnreadCount(0);
    } finally {
      setIsLoadingNotifications(false);
    }
  }, [showNotifications]);

  useEffect(() => {
    function closeMenus(event: MouseEvent) {
      if (
        accountMenuRef.current &&
        !accountMenuRef.current.contains(event.target as Node)
      ) {
        setIsAccountMenuOpen(false);
      }
      if (
        notificationMenuRef.current &&
        !notificationMenuRef.current.contains(event.target as Node)
      ) {
        setIsNotificationMenuOpen(false);
      }
    }

    document.addEventListener("mousedown", closeMenus);
    return () => document.removeEventListener("mousedown", closeMenus);
  }, []);

  useEffect(() => {
    void Promise.resolve().then(refreshNotifications);
  }, [refreshNotifications]);

  const openNotificationMenu = () => {
    setIsNotificationMenuOpen((current) => !current);
    setIsAccountMenuOpen(false);
    if (!isNotificationMenuOpen) {
      refreshNotifications();
    }
  };

  const getNotificationHref = (notification: NotificationItem) => {
    const href = notification.data?.href;
    return typeof href === "string" && href.startsWith("/") ? href : "/notifications";
  };

  const handleNotificationClick = async (notification: NotificationItem) => {
    if (!notification.read_at) {
      try {
        await markNotificationRead(notification.id);
      } catch {
        // Keep navigation available even if the read-state update fails.
      }
    }
    setIsNotificationMenuOpen(false);
  };

  const markAllRead = async () => {
    try {
      await markAllNotificationsRead();
      setUnreadCount(0);
      setNotifications((current) =>
        current.map((notification) => ({
          ...notification,
          read_at: notification.read_at ?? new Date().toISOString(),
        })),
      );
    } catch {
      await refreshNotifications();
    }
  };

  return (
    <>
      <header className="fixed inset-x-0 top-0 z-50 border-b border-cyan-300/15 bg-[#050816]/82 shadow-[0_12px_60px_rgba(0,0,0,0.28)] backdrop-blur-2xl">
        <div className="mx-auto flex h-20 max-w-[1480px] items-center justify-between px-4 sm:px-6 lg:px-8">
          <Link className="flex items-center gap-3" href="/trading">
            <Image
              alt="VinTrade AI"
              className="h-12 w-auto drop-shadow-[0_0_18px_rgba(34,211,238,0.25)]"
              height={80}
              src="/assets/logo/vintrade-logo.svg"
              width={322}
            />
          </Link>

          {focusMode ? (
            <div className="hidden items-center gap-2 rounded-full border border-emerald-300/20 bg-emerald-400/[0.06] px-4 py-2 text-sm font-semibold text-emerald-100 lg:flex">
              <span className="status-dot" />
              {t("ekyc.hero.focusMode")}
            </div>
          ) : (
            <nav className="hidden items-center gap-1 rounded-full border border-white/10 bg-white/[0.04] p-1 text-sm font-semibold text-slate-200 lg:flex">
              {menuItems.map((item) => (
                <Link
                  className={`rounded-full px-4 py-2 transition hover:bg-cyan-400/10 hover:text-cyan-200 ${
                    item.href !== "#" &&
                    !item.href.includes("#") &&
                    pathname === item.href
                      ? "bg-cyan-400/10 text-cyan-200"
                      : ""
                  }`}
                  href={item.href}
                  key={item.labelKey}
                >
                  {t(item.labelKey)}
                </Link>
              ))}
            </nav>
          )}

          <div className="flex items-center gap-3">
            <LanguageDropdown />
            {showNotifications ? (
              <div className="relative" ref={notificationMenuRef}>
                <button
                  aria-expanded={isNotificationMenuOpen}
                  aria-haspopup="menu"
                  className="relative grid h-11 w-11 place-items-center rounded-lg border border-white/10 bg-white/[0.04] text-slate-100 transition hover:border-cyan-300/35 hover:bg-cyan-400/10"
                  onClick={openNotificationMenu}
                  title={t("header.notifications.tooltip")}
                  type="button"
                >
                  <Bell size={18} className="text-cyan-200" />
                  {unreadCount > 0 ? (
                    <span className="absolute -right-1 -top-1 min-w-5 rounded-full bg-rose-500 px-1.5 py-0.5 text-center text-[11px] font-black leading-none text-white shadow-lg">
                      {unreadCount > 9 ? "9+" : unreadCount}
                    </span>
                  ) : null}
                </button>

                {isNotificationMenuOpen ? (
                  <div
                    className="absolute right-0 top-[calc(100%+10px)] z-50 w-[340px] overflow-hidden rounded-xl border border-white/10 bg-[#0a1022]/98 p-2 shadow-2xl backdrop-blur-xl"
                    role="menu"
                  >
                    <div className="flex items-center justify-between px-2 py-2">
                      <p className="text-sm font-black text-slate-100">
                        {t("header.notifications.title")}
                      </p>
                      {unreadCount > 0 ? (
                        <button
                          className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs font-bold text-cyan-200 transition hover:bg-cyan-400/10"
                          onClick={markAllRead}
                          type="button"
                        >
                          <CheckCheck size={14} />
                          {t("header.notifications.markAllRead")}
                        </button>
                      ) : null}
                    </div>

                    <div className="max-h-[360px] overflow-y-auto py-1">
                      {isLoadingNotifications ? (
                        <div className="flex items-center gap-2 px-3 py-4 text-sm font-semibold text-slate-300">
                          <Inbox size={17} className="text-cyan-200" />
                          {t("header.notifications.loading")}
                        </div>
                      ) : notifications.length ? (
                        notifications.map((notification) => (
                          <Link
                            className={`block rounded-lg px-3 py-3 transition hover:bg-cyan-400/10 ${
                              notification.read_at
                                ? "text-slate-300"
                                : "bg-cyan-400/[0.06] text-slate-100"
                            }`}
                            href={getNotificationHref(notification)}
                            key={notification.id}
                            onClick={() => handleNotificationClick(notification)}
                            role="menuitem"
                          >
                            <div className="flex items-start gap-2">
                              {!notification.read_at ? (
                                <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-cyan-300" />
                              ) : (
                                <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-white/20" />
                              )}
                              <div className="min-w-0">
                                <p className="truncate text-sm font-black">
                                  {notification.title}
                                </p>
                                <p className="mt-1 line-clamp-2 text-xs font-semibold leading-5 text-slate-400">
                                  {notification.message}
                                </p>
                              </div>
                            </div>
                          </Link>
                        ))
                      ) : (
                        <div className="px-3 py-5 text-center text-sm font-semibold text-slate-400">
                          <Inbox className="mx-auto mb-2 text-cyan-200" size={20} />
                          {t("header.notifications.empty")}
                        </div>
                      )}
                    </div>

                    <Link
                      className="mt-1 block rounded-lg border border-white/10 px-3 py-2 text-center text-sm font-black text-cyan-100 transition hover:bg-cyan-400/10"
                      href="/notifications"
                      onClick={() => setIsNotificationMenuOpen(false)}
                      role="menuitem"
                    >
                      {t("header.notifications.viewAll")}
                    </Link>
                  </div>
                ) : null}
              </div>
            ) : null}

            <div className="relative" ref={accountMenuRef}>
              <button
                aria-expanded={isAccountMenuOpen}
                aria-haspopup="menu"
                className="flex h-11 max-w-[240px] items-center gap-2 rounded-lg border border-white/10 bg-white/[0.04] px-4 text-sm font-bold text-slate-100 transition hover:border-cyan-300/35 hover:bg-cyan-400/10"
                onClick={() => setIsAccountMenuOpen((current) => !current)}
                type="button"
              >
                <UserRound size={17} className="shrink-0 text-cyan-200" />
                <span className="truncate">{displayName}</span>
                <ChevronDown
                  className={`shrink-0 transition ${
                    isAccountMenuOpen ? "rotate-180" : ""
                  }`}
                  size={16}
                />
              </button>

              {isAccountMenuOpen ? (
                <div
                  className="absolute right-0 top-[calc(100%+10px)] z-50 w-52 overflow-hidden rounded-xl border border-white/10 bg-[#0a1022]/98 p-2 shadow-2xl backdrop-blur-xl"
                  role="menu"
                >
                  <Link
                    className="flex items-center gap-3 rounded-lg px-3 py-3 text-sm font-bold text-slate-200 transition hover:bg-cyan-400/10 hover:text-cyan-100"
                    href="/profile"
                    onClick={() => setIsAccountMenuOpen(false)}
                    role="menuitem"
                  >
                    <UserRound size={17} />
                    {t("header.actions.viewProfile")}
                  </Link>
                  <button
                    className="flex w-full items-center gap-3 rounded-lg px-3 py-3 text-left text-sm font-bold text-rose-200 transition hover:bg-rose-500/10 hover:text-rose-100"
                    onClick={logout}
                    role="menuitem"
                    type="button"
                  >
                    <LogOut size={17} />
                    {t("header.actions.logout")}
                  </button>
                </div>
              ) : null}
            </div>
          </div>
        </div>
      </header>
      <div className="h-20" aria-hidden="true" />
    </>
  );
}
