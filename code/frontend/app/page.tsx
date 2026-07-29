"use client";

import { FeatureCard } from "@/components/common/FeatureCard";
import { StatCard } from "@/components/common/StatCard";
import { MarketChart } from "@/components/market/MarketChart";
import { MarketTable } from "@/components/market/MarketTable";
import { TradingHeroVisual } from "@/components/market/TradingHeroVisual";
import { Footer } from "@/components/site/Footer";
import { Header } from "@/components/site/Header";
import { useLanguage } from "@/contexts/LanguageContext";
import { features, marketStats } from "@/app/data/market";

const trustBadgeKeys = [
  "publicHome.trustBadges.realtimeData",
  "publicHome.trustBadges.aiSignals",
  "publicHome.trustBadges.secureSafe",
  "publicHome.trustBadges.monitoring",
];

const statLabelKeys = [
  "publicHome.stats.totalMarketCap",
  "publicHome.stats.volume24h",
  "publicHome.stats.activeUsers",
  "publicHome.stats.aiSignalsToday",
];

const featureKeys = [
  {
    descriptionKey: "publicHome.features.realtimeDescription",
    titleKey: "publicHome.features.realtimeTitle",
  },
  {
    descriptionKey: "publicHome.features.riskDescription",
    titleKey: "publicHome.features.riskTitle",
  },
  {
    descriptionKey: "publicHome.features.portfolioDescription",
    titleKey: "publicHome.features.portfolioTitle",
  },
  {
    descriptionKey: "publicHome.features.ekycDescription",
    titleKey: "publicHome.features.ekycTitle",
  },
];

export default function Home() {
  const { t } = useLanguage();

  return (
    <main className="min-h-screen overflow-hidden bg-[#030712] text-white">
      <div className="vintrade-bg" />
      <Header />

      <section className="relative mx-auto grid w-full max-w-[1480px] gap-8 px-4 pb-8 pt-8 sm:px-6 lg:grid-cols-[1.03fr_0.97fr] lg:px-8 lg:pb-12">
        <div className="z-10 flex flex-col justify-center py-8 lg:min-h-[620px]">
          <div className="mb-5 flex flex-wrap gap-3">
            {trustBadgeKeys.map((badgeKey) => (
              <span className="micro-badge" key={badgeKey}>
                <span className="status-dot cyan" />
                {t(badgeKey)}
              </span>
            ))}
          </div>

          <h1 className="max-w-4xl text-5xl font-black leading-[1.04] tracking-normal text-white sm:text-6xl lg:text-7xl">
            {t("publicHome.titlePrefix")}{" "}
            <span className="gradient-text">{t("publicHome.titleHighlight")}</span>
          </h1>
          <p className="mt-6 max-w-2xl text-base leading-8 text-slate-300 sm:text-lg">
            {t("publicHome.description")}
          </p>

          <div className="mt-8 flex flex-col gap-4 sm:flex-row">
            <a className="primary-button" href="/register">
              {t("publicHome.startDemo")}
              <span aria-hidden="true">-&gt;</span>
            </a>
            <a className="secondary-button" href="#market">
              {t("publicHome.viewMarket")}
              <span aria-hidden="true">&gt;</span>
            </a>
          </div>
        </div>

        <TradingHeroVisual />
      </section>

      <section className="relative z-10 mx-auto grid max-w-[1480px] gap-4 px-4 sm:grid-cols-2 sm:px-6 lg:grid-cols-4 lg:px-8">
        {marketStats.map((stat, index) => (
          <StatCard
            key={stat.label}
            {...stat}
            label={t(statLabelKeys[index])}
          />
        ))}
      </section>

      <section
        id="market"
        className="relative z-10 mx-auto grid max-w-[1480px] gap-5 px-4 py-8 sm:px-6 lg:grid-cols-[0.92fr_1.08fr] lg:px-8"
      >
        <MarketTable />
        <MarketChart />
      </section>

      <section className="relative z-10 mx-auto max-w-[1480px] px-4 pb-10 sm:px-6 lg:px-8">
        <div className="section-title">
          <span />
          <h2>{t("publicHome.featureTitle")}</h2>
          <span />
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {features.map((feature, index) => (
            <FeatureCard
              key={feature.title}
              {...feature}
              description={t(featureKeys[index].descriptionKey)}
              title={t(featureKeys[index].titleKey)}
            />
          ))}
        </div>
      </section>

      <Footer />
    </main>
  );
}
