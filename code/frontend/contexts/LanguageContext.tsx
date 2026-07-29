"use client";

import {
  defaultLocale,
  localeOptions,
  messages,
  type Locale,
  type MessageValues,
} from "@/lib/i18n/messages";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

const LOCALE_STORAGE_KEY = "vintrade_locale";

type LanguageContextValue = {
  locale: Locale;
  localeOptions: typeof localeOptions;
  setLocale: (locale: Locale) => void;
  t: (key: string, values?: MessageValues) => string;
};

const LanguageContext = createContext<LanguageContextValue | null>(null);

function isLocale(value: string | null): value is Locale {
  return Boolean(value && value in messages);
}

function readMessage(locale: Locale, key: string) {
  const keys = key.split(".");
  let current: unknown = messages[locale];

  for (const item of keys) {
    if (!current || typeof current !== "object" || !(item in current)) {
      return null;
    }
    current = (current as Record<string, unknown>)[item];
  }

  return typeof current === "string" ? current : null;
}

function applyValues(message: string, values?: MessageValues) {
  if (!values) {
    return message;
  }

  return Object.entries(values).reduce(
    (result, [key, value]) => result.replaceAll(`{${key}}`, String(value)),
    message,
  );
}

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(defaultLocale);

  useEffect(() => {
    const storedLocale = window.localStorage.getItem(LOCALE_STORAGE_KEY);
    let timeoutId: number | null = null;

    if (isLocale(storedLocale)) {
      timeoutId = window.setTimeout(() => {
        setLocaleState(storedLocale);
      }, 0);
    }

    return () => {
      if (timeoutId !== null) {
        window.clearTimeout(timeoutId);
      }
    };
  }, []);

  useEffect(() => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, locale);
    document.documentElement.lang = locale;
  }, [locale]);

  const setLocale = useCallback((nextLocale: Locale) => {
    setLocaleState(nextLocale);
  }, []);

  const t = useCallback(
    (key: string, values?: MessageValues) => {
      const message =
        readMessage(locale, key) ?? readMessage(defaultLocale, key) ?? key;
      return applyValues(message, values);
    },
    [locale],
  );

  const value = useMemo(
    () => ({
      locale,
      localeOptions,
      setLocale,
      t,
    }),
    [locale, setLocale, t],
  );

  return (
    <LanguageContext.Provider value={value}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useLanguage() {
  const context = useContext(LanguageContext);
  if (!context) {
    throw new Error("useLanguage must be used inside LanguageProvider");
  }
  return context;
}
