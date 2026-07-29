"use client";

import Image from "next/image";
import Link from "next/link";
import { UserRound } from "lucide-react";
import { LanguageDropdown } from "@/components/i18n/LanguageDropdown";
import { useAuth } from "@/contexts/AuthContext";
import { useLanguage } from "@/contexts/LanguageContext";

const menuItems = [
  { href: "/#market", labelKey: "header.menu.market" },
  { href: "#", labelKey: "header.menu.aiSignals" },
  { href: "#", labelKey: "header.menu.portfolio" },
  { href: "#", labelKey: "header.menu.security" },
  { href: "#", labelKey: "header.menu.pricing" },
];

export function Header() {
  const { isAuthenticated, isLoading, user } = useAuth();
  const { t } = useLanguage();

  return (
    <>
      <header className="fixed inset-x-0 top-0 z-50 border-b border-white/10 bg-[#050816]/72 shadow-[0_12px_60px_rgba(0,0,0,0.28)] backdrop-blur-2xl">
        <div className="mx-auto flex h-20 max-w-[1480px] items-center justify-between px-4 sm:px-6 lg:px-8">
          <Link className="flex items-center gap-3" href="/">
            <Image
              alt="VinTrade AI"
              className="h-12 w-auto drop-shadow-[0_0_18px_rgba(34,211,238,0.25)]"
              height={80}
              src="/assets/logo/vintrade-logo.svg"
              width={322}
            />
          </Link>

          <nav className="hidden items-center gap-1 rounded-full border border-white/10 bg-white/[0.04] p-1 text-sm font-semibold text-slate-200 lg:flex">
            {menuItems.map((item) => (
              <a
                className="rounded-full px-4 py-2 transition hover:bg-cyan-400/10 hover:text-cyan-200"
                href={item.href}
                key={item.labelKey}
              >
                {t(item.labelKey)}
              </a>
            ))}
          </nav>

          <div className="flex items-center gap-3">
            <LanguageDropdown />
            {!isLoading && isAuthenticated ? (
              <>
                <div className="hidden max-w-[220px] items-center gap-2 rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2 text-sm text-slate-200 md:flex">
                  <UserRound size={16} className="text-cyan-200" />
                  <span className="truncate">
                    {user?.full_name?.trim() ||
                      user?.email?.split("@")[0] ||
                      t("common.userAccount")}
                  </span>
                </div>
                <Link className="primary-button h-11 px-6" href="/trading">
                  {t("header.menu.trading")}
                </Link>
              </>
            ) : !isLoading ? (
              <>
                <Link
                  className="secondary-button hidden h-11 px-6 sm:inline-flex"
                  href="/login"
                >
                  {t("header.actions.login")}
                </Link>
                <Link className="primary-button h-11 px-6" href="/register">
                  {t("header.actions.getStarted")}
                </Link>
              </>
            ) : null}
          </div>
        </div>
      </header>
      <div className="h-20" aria-hidden="true" />
    </>
  );
}
