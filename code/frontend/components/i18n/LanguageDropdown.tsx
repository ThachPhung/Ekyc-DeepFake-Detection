"use client";

import { useLanguage } from "@/contexts/LanguageContext";
import type { Locale } from "@/lib/i18n/messages";
import { ChevronDown } from "lucide-react";
import { useEffect, useRef, useState } from "react";

const orderedLocales: Locale[] = ["vi", "en"];

export function LanguageDropdown() {
  const { locale, localeOptions, setLocale, t } = useLanguage();
  const [isOpen, setIsOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const currentLocale = localeOptions[locale];

  useEffect(() => {
    function closeMenu(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }

    document.addEventListener("mousedown", closeMenu);
    return () => document.removeEventListener("mousedown", closeMenu);
  }, []);

  function handleSelect(nextLocale: Locale) {
    setLocale(nextLocale);
    setIsOpen(false);
  }

  return (
    <div className="relative" ref={menuRef}>
      <button
        aria-expanded={isOpen}
        aria-haspopup="menu"
        aria-label={t("language.label")}
        className="flex h-11 items-center gap-2 rounded-lg border border-white/10 bg-white/[0.04] px-3 text-sm font-bold text-slate-100 transition hover:border-cyan-300/35 hover:bg-cyan-400/10"
        onClick={() => setIsOpen((current) => !current)}
        title={t("language.label")}
        type="button"
      >
        <span className="text-base leading-none" aria-hidden="true">
          {currentLocale.flag}
        </span>
        <span className="hidden sm:inline">{currentLocale.shortLabel}</span>
        <ChevronDown
          className={`shrink-0 transition ${isOpen ? "rotate-180" : ""}`}
          size={15}
        />
      </button>

      {isOpen ? (
        <div
          className="absolute right-0 top-[calc(100%+10px)] z-50 w-44 overflow-hidden rounded-xl border border-white/10 bg-[#0a1022]/98 p-2 shadow-2xl backdrop-blur-xl"
          role="menu"
        >
          {orderedLocales.map((item) => {
            const option = localeOptions[item];
            const selected = item === locale;

            return (
              <button
                className={`flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm font-bold transition ${
                  selected
                    ? "bg-cyan-400/10 text-cyan-100"
                    : "text-slate-200 hover:bg-cyan-400/10 hover:text-cyan-100"
                }`}
                key={item}
                onClick={() => handleSelect(item)}
                role="menuitem"
                title={t("language.switchTo", { language: option.label })}
                type="button"
              >
                <span className="text-base leading-none" aria-hidden="true">
                  {option.flag}
                </span>
                <span>{option.label}</span>
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
