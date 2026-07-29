"use client";

import Link from "next/link";
import Image from "next/image";
import { ReactNode } from "react";
import { motion } from "framer-motion";
import { LanguageDropdown } from "@/components/i18n/LanguageDropdown";
import { useLanguage } from "@/contexts/LanguageContext";
import {
  BadgeCheck,
  BrainCircuit,
  CandlestickChart,
  LockKeyhole,
  ShieldCheck,
  TrendingUp,
} from "lucide-react";

type AuthLayoutProps = {
  eyebrow?: string;
  heading: string;
  subheading: string;
  cardTitle?: string;
  children: ReactNode;
};

export function AuthLayout({
  eyebrow,
  heading,
  subheading,
  cardTitle,
  children,
}: AuthLayoutProps) {
  const { t } = useLanguage();
  const defaultCardTitle =
    heading === "Welcome Back" || heading === t("auth.login.heading")
      ? t("auth.layout.defaultSignInCardTitle")
      : t("auth.layout.defaultCreateCardTitle");

  return (
    <main className="min-h-screen overflow-hidden bg-[#050816] text-white">
      <div className="auth-bg" />
      <div className="absolute right-4 top-4 z-20 sm:right-6 sm:top-6">
        <LanguageDropdown />
      </div>
      <div className="relative z-10 grid min-h-screen lg:grid-cols-[0.95fr_1.05fr]">
        <section className="hidden border-r border-white/10 px-8 py-8 lg:flex lg:flex-col">
          <Link className="flex items-center gap-3" href="/">
            <Image
              alt="VinTrade AI"
              className="h-14 w-auto"
              height={80}
              src="/assets/logo/vintrade-logo.svg"
              width={322}
            />
          </Link>
          <div className="flex flex-1 items-center py-8">
            <motion.div
              animate={{ opacity: 1, y: 0 }}
              className="w-full"
              initial={{ opacity: 0, y: 22 }}
              transition={{ duration: 0.55 }}
            >
              <span className="micro-badge">
                <span className="status-dot cyan" />
                {t("auth.layout.liveMarketIntelligence")}
              </span>
              <h1 className="mt-5 max-w-xl text-6xl font-black leading-tight tracking-normal">
                {t("auth.layout.heroTitle")}
              </h1>
              <p className="mt-5 max-w-lg text-lg leading-8 text-slate-300">
                {t("auth.layout.heroDescription")}
              </p>
              <AuthTradingPreview />
            </motion.div>
          </div>
          <div className="grid grid-cols-3 gap-3 text-xs text-slate-300">
            <span className="micro-badge">
              <LockKeyhole size={13} />
              {t("auth.layout.secureLogin")}
            </span>
            <span className="micro-badge">
              <ShieldCheck size={13} />
              {t("auth.layout.encryptedData")}
            </span>
            <span className="micro-badge">
              <BadgeCheck size={13} />
              {t("auth.layout.protection")}
            </span>
          </div>
        </section>

        <section className="flex min-h-screen items-center justify-center px-4 py-8 sm:px-6 lg:px-10">
          <motion.div
            animate={{ opacity: 1, x: 0 }}
            className="w-full max-w-[560px]"
            initial={{ opacity: 0, x: 22 }}
            transition={{ duration: 0.55 }}
          >
            <div className="mb-8 text-center">
              <Link className="mb-8 inline-flex items-center gap-3 lg:hidden" href="/">
                <Image
                  alt="VinTrade AI"
                  className="h-14 w-auto"
                  height={80}
                  src="/assets/logo/vintrade-logo.svg"
                  width={322}
                />
              </Link>
              {eyebrow ? (
                <p className="text-sm font-bold uppercase tracking-[0.25em] text-cyan-300">
                  {eyebrow}
                </p>
              ) : null}
              <h1 className="mt-4 text-4xl font-black tracking-normal">{heading}</h1>
              <p className="mx-auto mt-3 max-w-md text-slate-300">{subheading}</p>
            </div>
            <div className="glass-panel auth-card p-5 sm:p-8">
              <h2 className="mb-6 text-center text-xl font-bold">
                {cardTitle ?? defaultCardTitle}
              </h2>
              <div className="space-y-6">{children}</div>
            </div>
          </motion.div>
        </section>
      </div>
    </main>
  );
}

function AuthTradingPreview() {
  const { t } = useLanguage();

  return (
    <div className="auth-terminal mt-8">
      <div className="auth-terminal-top">
        <div className="flex items-center gap-3">
          <span className="asset-token">
            <Image
              alt="Bitcoin logo"
              className="h-7 w-7 rounded-full object-contain"
              height={28}
              src="/icons/bitcoin.png"
              width={28}
            />
          </span>
          <div>
            <p className="text-xs text-slate-400">
              {t("auth.layout.perpetualMarket")}
            </p>
            <strong>BTC / USDT</strong>
          </div>
        </div>
        <span className="status-pill success">{t("auth.layout.live")}</span>
      </div>
      <svg className="mt-5 h-64 w-full" viewBox="0 0 560 250" preserveAspectRatio="none">
        <defs>
          <linearGradient id="authDashboardLine" x1="0" x2="1" y1="0" y2="0">
            <stop stopColor="#22d3ee" />
            <stop offset=".5" stopColor="#8b5cf6" />
            <stop offset="1" stopColor="#21f6a4" />
          </linearGradient>
        </defs>
        {[0, 1, 2, 3, 4].map((line) => (
          <line
            key={line}
            stroke="#24304f"
            strokeDasharray="6 8"
            x1="18"
            x2="542"
            y1={36 + line * 42}
            y2={36 + line * 42}
          />
        ))}
        <path
          d="M12 188 C62 132 92 164 126 118 S202 68 244 96 306 160 362 88 462 48 548 68"
          fill="none"
          stroke="url(#authDashboardLine)"
          strokeLinecap="round"
          strokeWidth="5"
        />
        {[38, 78, 118, 158, 198, 238, 278, 318, 358, 398, 438, 478, 518].map(
          (x, index) => (
            <rect
              fill={index % 2 ? "#a855f7" : "#22d3ee"}
              height={34 + ((index * 19) % 90)}
              key={x}
              opacity="0.72"
              rx="3"
              width="13"
              x={x}
              y={230 - (34 + ((index * 19) % 90))}
            />
          ),
        )}
      </svg>
      <motion.div
        animate={{ y: [0, -8, 0] }}
        className="auth-ai-widget"
        transition={{ duration: 4.2, repeat: Infinity, ease: "easeInOut" }}
      >
        <BrainCircuit size={18} />
        <div>
          <span>{t("auth.layout.aiSignal")}</span>
          <strong>{t("auth.layout.breakoutProbability")}</strong>
        </div>
      </motion.div>
      <div className="auth-terminal-grid">
        <span>
          <CandlestickChart size={14} /> {t("auth.layout.depthStrong")}
        </span>
        <span>
          <TrendingUp size={14} /> {t("auth.layout.momentumBullish")}
        </span>
        <span>
          <ShieldCheck size={14} /> {t("auth.layout.riskControlled")}
        </span>
      </div>
    </div>
  );
}
