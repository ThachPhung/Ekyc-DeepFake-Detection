"use client";

import Image from "next/image";
import { useLanguage } from "@/contexts/LanguageContext";

export function Footer() {
  const { t } = useLanguage();

  return (
    <footer className="relative z-10 border-t border-white/10 bg-[#050816]/70">
      <div className="mx-auto flex max-w-[1480px] flex-col gap-5 px-4 py-7 text-sm text-slate-400 sm:px-6 lg:flex-row lg:items-center lg:justify-between lg:px-8">
        <div className="flex items-center gap-3">
          <Image
            alt="VinTrade AI"
            className="h-10 w-auto"
            height={96}
            src="/assets/logo/vintrade-icon.svg"
            width={96}
          />
          <div>
            <p className="font-bold text-white">VinTrade AI</p>
            <p>{t("footer.description")}</p>
          </div>
        </div>
        <div className="flex flex-wrap gap-5">
          <span>{t("footer.bankSecurity")}</span>
          <span>{t("footer.encryption")}</span>
          <span>{t("footer.trustedUsers")}</span>
        </div>
        <p>{t("footer.copyright")}</p>
      </div>
    </footer>
  );
}
