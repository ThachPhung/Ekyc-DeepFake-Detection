"use client";

import Image from "next/image";
import { useMemo, useState } from "react";
import {
  ArrowDownRight,
  ArrowUpRight,
  BookOpen,
  ChevronRight,
  Newspaper,
  WalletCards,
} from "lucide-react";
import { marketAssets, type MarketAsset } from "@/app/data/market";
import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { MarketChart } from "@/components/market/MarketChart";
import { AppHeader } from "@/components/site/AppHeader";
import { useLanguage } from "@/contexts/LanguageContext";

const marketNewsKeys = [
  "trading.news.bitcoin",
  "trading.news.ethereum",
  "trading.news.macro",
];

export default function TradingPage() {
  const { t } = useLanguage();
  const [selectedAsset, setSelectedAsset] = useState(marketAssets[0]);
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [quantity, setQuantity] = useState("");
  const [notice, setNotice] = useState("");

  const selectedPrice = useMemo(
    () => Number(selectedAsset.price.replace(/[$,]/g, "")) || 0,
    [selectedAsset.price],
  );
  const estimatedTotal = (Number(quantity) || 0) * selectedPrice;

  function submitDemoOrder() {
    if (!quantity || Number(quantity) <= 0) {
      setNotice(t("trading.invalidQuantity"));
      return;
    }

    setNotice(
      t("trading.orderPreview", {
        quantity,
        side: t(side === "buy" ? "trading.buy" : "trading.sell"),
        symbol: selectedAsset.symbol,
      }),
    );
  }

  return (
    <ProtectedRoute>
      <main className="min-h-screen overflow-hidden bg-[#030712] text-white">
        <div className="vintrade-bg" />
        <AppHeader />

        <section className="relative z-10 mx-auto grid max-w-[1480px] gap-6 px-4 py-8 sm:px-6 lg:grid-cols-[1.1fr_0.9fr] lg:px-8">
          <div className="flex min-h-[390px] flex-col justify-center rounded-2xl border border-white/5 bg-slate-950/20 p-6 sm:p-10">
            <span className="micro-badge w-fit">
              <span className="status-dot cyan" />
              {t("trading.badge")}
            </span>
            <h1 className="mt-6 max-w-3xl text-5xl font-black leading-[1.05] tracking-normal sm:text-6xl">
              {t("trading.titlePrefix")}{" "}
              <span className="gradient-text">{t("trading.titleHighlight")}</span>
            </h1>
            <p className="mt-5 max-w-2xl text-base leading-7 text-slate-300">
              {t("trading.description")}
            </p>

            <div className="mt-10 grid gap-4 sm:grid-cols-2">
              <div className="rounded-xl border border-white/10 bg-white/[0.04] p-5">
                <div className="flex items-center gap-2 text-sm font-bold text-slate-400">
                  <WalletCards size={17} className="text-cyan-200" />
                  {t("trading.estimatedBalance")}
                </div>
                <strong className="mt-3 block text-3xl font-black">$0.00</strong>
                <p className="mt-2 text-sm text-slate-500">
                  {t("trading.balanceDescription")}
                </p>
              </div>
              <div className="rounded-xl border border-white/10 bg-white/[0.04] p-5">
                <p className="text-sm font-bold text-slate-400">
                  {t("trading.todayPnl")}
                </p>
                <strong className="mt-3 block text-3xl font-black text-slate-100">
                  $0.00
                </strong>
                <p className="mt-2 text-sm text-slate-500">
                  0.00% {t("trading.today")}
                </p>
              </div>
            </div>

            <div className="mt-5 flex flex-col gap-3 sm:flex-row">
              <a className="primary-button justify-center" href="#trade">
                {t("trading.tradeNow")}
              </a>
              <button className="secondary-button justify-center" type="button">
                <BookOpen size={16} />
                {t("trading.tradingGuide")}
              </button>
            </div>
          </div>

          <div className="grid gap-5">
            <section className="glass-panel overflow-hidden">
              <div className="flex items-center justify-between border-b border-white/10 px-5 py-4">
                <div>
                  <h2 className="text-lg font-black">
                    {t("trading.popularMarkets")}
                  </h2>
                  <p className="mt-1 text-xs text-slate-400">
                    {t("trading.demoPrices")}
                  </p>
                </div>
                <a
                  className="inline-flex items-center gap-1 text-sm font-bold text-cyan-200"
                  href="#markets"
                >
                  {t("trading.viewAll")} <ChevronRight size={15} />
                </a>
              </div>
              <div className="divide-y divide-white/5">
                {marketAssets.slice(0, 5).map((asset) => (
                  <MarketRow
                    asset={asset}
                    key={asset.symbol}
                    onSelect={() => {
                      setSelectedAsset(asset);
                      setNotice("");
                    }}
                    selected={selectedAsset.symbol === asset.symbol}
                  />
                ))}
              </div>
            </section>

            <section className="glass-panel p-5">
              <div className="mb-4 flex items-center gap-2">
                <Newspaper size={18} className="text-violet-300" />
                <h2 className="text-lg font-black">{t("trading.marketNews")}</h2>
              </div>
              <div className="grid gap-3">
                {marketNewsKeys.map((headlineKey) => (
                  <article
                    className="rounded-lg border border-white/10 bg-slate-950/40 p-3 text-sm font-semibold leading-6 text-slate-200"
                    key={headlineKey}
                  >
                    {t(headlineKey)}
                  </article>
                ))}
              </div>
            </section>
          </div>
        </section>

        <section
          className="relative z-10 mx-auto grid max-w-[1480px] gap-5 px-4 pb-10 sm:px-6 lg:grid-cols-[1fr_360px] lg:px-8"
          id="trade"
        >
          <div id="markets">
            <MarketChart asset={selectedAsset} />
          </div>

          <section className="glass-panel p-5">
            <div className="flex items-center gap-3 border-b border-white/10 pb-4">
              <span className="asset-token">
                <Image
                  alt={`${selectedAsset.name} logo`}
                  height={28}
                  src={selectedAsset.icon}
                  width={28}
                />
              </span>
              <div>
                <h2 className="font-black">
                  {selectedAsset.symbol} / USDT
                </h2>
                <p className="text-xs text-slate-400">{selectedAsset.name}</p>
              </div>
              <strong className="ml-auto text-lg">{selectedAsset.price}</strong>
            </div>

            <div className="mt-5 grid grid-cols-2 gap-2 rounded-lg bg-slate-950/70 p-1">
              {(["buy", "sell"] as const).map((orderSide) => (
                <button
                  className={`rounded-md px-4 py-3 text-sm font-black transition ${
                    side === orderSide
                      ? orderSide === "buy"
                        ? "bg-emerald-500 text-slate-950"
                        : "bg-rose-500 text-white"
                      : "text-slate-400 hover:text-white"
                  }`}
                  key={orderSide}
                  onClick={() => {
                    setSide(orderSide);
                    setNotice("");
                  }}
                  type="button"
                >
                  {t(orderSide === "buy" ? "trading.buy" : "trading.sell")}
                </button>
              ))}
            </div>

            <label className="mt-5 block">
              <span className="form-label">{t("trading.orderType")}</span>
              <div className="input-shell">
                <input disabled value={t("trading.marketOrder")} />
              </div>
            </label>
            <label className="mt-4 block">
              <span className="form-label">
                {t("trading.quantity", { symbol: selectedAsset.symbol })}
              </span>
              <div className="input-shell">
                <input
                  inputMode="decimal"
                  min="0"
                  onChange={(event) => {
                    setQuantity(event.target.value);
                    setNotice("");
                  }}
                  placeholder="0.00"
                  type="number"
                  value={quantity}
                />
              </div>
            </label>

            <div className="mt-4 rounded-lg border border-white/10 bg-slate-950/50 p-4">
              <div className="flex justify-between text-sm text-slate-400">
                <span>{t("trading.marketPrice")}</span>
                <strong className="text-white">{selectedAsset.price}</strong>
              </div>
              <div className="mt-3 flex justify-between text-sm text-slate-400">
                <span>{t("trading.estimatedTotal")}</span>
                <strong className="text-white">
                  ${estimatedTotal.toLocaleString("en-US", { maximumFractionDigits: 2 })}
                </strong>
              </div>
            </div>

            {notice ? (
              <p className="mt-4 rounded-lg border border-cyan-300/20 bg-cyan-400/10 p-3 text-sm font-semibold leading-6 text-cyan-100">
                {notice}
              </p>
            ) : null}

            <button
              className={`mt-5 w-full justify-center ${
                side === "buy" ? "primary-button" : "secondary-button"
              }`}
              onClick={submitDemoOrder}
              type="button"
            >
              {t("trading.previewOrder", {
                side: t(side === "buy" ? "trading.buy" : "trading.sell").toLowerCase(),
              })}
            </button>
            <p className="mt-3 text-center text-xs leading-5 text-slate-500">
              {t("trading.demoOnly")}
            </p>
          </section>
        </section>
      </main>
    </ProtectedRoute>
  );
}

function MarketRow({
  asset,
  onSelect,
  selected,
}: {
  asset: MarketAsset;
  onSelect: () => void;
  selected: boolean;
}) {
  const isUp = asset.change >= 0;

  return (
    <button
      className={`grid w-full grid-cols-[1fr_auto_auto] items-center gap-4 px-5 py-4 text-left transition ${
        selected ? "bg-cyan-400/10" : "hover:bg-white/[0.04]"
      }`}
      onClick={onSelect}
      type="button"
    >
      <span className="flex min-w-0 items-center gap-3">
        <Image
          alt={`${asset.name} logo`}
          className="h-8 w-8 rounded-full object-contain"
          height={32}
          src={asset.icon}
          width={32}
        />
        <span className="min-w-0">
          <strong className="block text-sm">{asset.symbol}</strong>
          <span className="block truncate text-xs text-slate-500">{asset.name}</span>
        </span>
      </span>
      <strong className="text-sm">{asset.price}</strong>
      <span
        className={`inline-flex items-center text-sm font-black ${
          isUp ? "text-emerald-300" : "text-rose-300"
        }`}
      >
        {isUp ? <ArrowUpRight size={15} /> : <ArrowDownRight size={15} />}
        {isUp ? "+" : ""}
        {asset.change.toFixed(2)}%
      </span>
    </button>
  );
}
