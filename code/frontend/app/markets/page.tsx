"use client";

import Image from "next/image";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  ArrowDownRight,
  ArrowUpRight,
  BarChart3,
  Bell,
  CandlestickChart,
  RefreshCw,
  Search,
  Star,
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { useLanguage } from "@/contexts/LanguageContext";
import { Header } from "@/components/site/Header";
import { AppHeader } from "@/components/site/AppHeader";

type TickerResponse = {
  symbol: string;
  lastPrice: string;
  priceChangePercent: string;
  quoteVolume: string;
  volume: string;
  highPrice: string;
  lowPrice: string;
  count: number;
};

type MarketCoin = {
  symbol: string;
  name: string;
  pair: string;
  icon: string;
  price: number;
  change: number;
  quoteVolume: number;
  baseVolume: number;
  high: number;
  low: number;
  trades: number;
  category: string;
  featured?: boolean;
};

const binanceSymbols = [
  "BTCUSDT",
  "ETHUSDT",
  "BNBUSDT",
  "SOLUSDT",
  "XRPUSDT",
  "DOGEUSDT",
  "ADAUSDT",
  "USDCUSDT",
];

const coinMeta: Record<
  string,
  Pick<MarketCoin, "symbol" | "name" | "icon" | "category" | "featured">
> = {
  BTCUSDT: {
    symbol: "BTC",
    name: "Bitcoin",
    icon: "/icons/bitcoin.png",
    category: "Layer 1",
    featured: true,
  },
  ETHUSDT: {
    symbol: "ETH",
    name: "Ethereum",
    icon: "/icons/ethereum.png",
    category: "Layer 1",
    featured: true,
  },
  BNBUSDT: {
    symbol: "BNB",
    name: "BNB",
    icon: "/icons/bnb.png",
    category: "BSC",
    featured: true,
  },
  SOLUSDT: {
    symbol: "SOL",
    name: "Solana",
    icon: "/icons/solana.png",
    category: "Solana",
  },
  XRPUSDT: {
    symbol: "XRP",
    name: "XRP",
    icon: "/icons/xrp.png",
    category: "Payments",
  },
  DOGEUSDT: {
    symbol: "DOGE",
    name: "Dogecoin",
    icon: "/icons/dogecoin.png",
    category: "Meme",
  },
  ADAUSDT: {
    symbol: "ADA",
    name: "Cardano",
    icon: "/icons/cardano.png",
    category: "Layer 1",
  },
  USDCUSDT: {
    symbol: "USDC",
    name: "USD Coin",
    icon: "/icons/xrp.png",
    category: "Stablecoin",
  },
};

const fallbackCoins: MarketCoin[] = [
  {
    symbol: "BTC",
    name: "Bitcoin",
    pair: "BTCUSDT",
    icon: "/icons/bitcoin.png",
    price: 60574.96,
    change: 2.86,
    quoteVolume: 37990000000,
    baseVolume: 627135,
    high: 61240,
    low: 58320,
    trades: 1422034,
    category: "Layer 1",
    featured: true,
  },
  {
    symbol: "ETH",
    name: "Ethereum",
    pair: "ETHUSDT",
    icon: "/icons/ethereum.png",
    price: 1629.61,
    change: 2.92,
    quoteVolume: 10800000000,
    baseVolume: 6627501,
    high: 1668,
    low: 1540,
    trades: 1012218,
    category: "Layer 1",
    featured: true,
  },
  {
    symbol: "BNB",
    name: "BNB",
    pair: "BNBUSDT",
    icon: "/icons/bnb.png",
    price: 552.82,
    change: 0.62,
    quoteVolume: 1300000000,
    baseVolume: 2351525,
    high: 560.4,
    low: 538.2,
    trades: 422091,
    category: "BSC",
    featured: true,
  },
  {
    symbol: "SOL",
    name: "Solana",
    pair: "SOLUSDT",
    icon: "/icons/solana.png",
    price: 78.37,
    change: 5.14,
    quoteVolume: 2710000000,
    baseVolume: 34579303,
    high: 82.1,
    low: 73.4,
    trades: 582119,
    category: "Solana",
  },
  {
    symbol: "XRP",
    name: "XRP",
    pair: "XRPUSDT",
    icon: "/icons/xrp.png",
    price: 0.61,
    change: -0.74,
    quoteVolume: 1860000000,
    baseVolume: 3049180327,
    high: 0.64,
    low: 0.59,
    trades: 318552,
    category: "Payments",
  },
  {
    symbol: "DOGE",
    name: "Dogecoin",
    pair: "DOGEUSDT",
    icon: "/icons/dogecoin.png",
    price: 0.13,
    change: 1.12,
    quoteVolume: 1090000000,
    baseVolume: 8384615384,
    high: 0.14,
    low: 0.12,
    trades: 280144,
    category: "Meme",
  },
  {
    symbol: "ADA",
    name: "Cardano",
    pair: "ADAUSDT",
    icon: "/icons/cardano.png",
    price: 0.42,
    change: -0.38,
    quoteVolume: 612450000,
    baseVolume: 1458214285,
    high: 0.44,
    low: 0.41,
    trades: 192087,
    category: "Layer 1",
  },
];

const mainTabs = [
  "market.tabs.overview",
  "market.tabs.tradingData",
  "market.tabs.aiPicks",
  "market.tabs.tokenUnlocks",
];
const categoryTabs = [
  "all",
  "Layer 1",
  "BSC",
  "Solana",
  "Payments",
  "Meme",
  "Stablecoin",
];

export default function MarketsPage() {
  const { locale, t } = useLanguage();
  const [coins, setCoins] = useState<MarketCoin[]>(fallbackCoins);
  const [activeCategory, setActiveCategory] = useState("all");
  const [search, setSearch] = useState("");
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [error, setError] = useState("");

  const refreshMarketData = useCallback(async () => {
    setIsRefreshing(true);
    setError("");

    try {
      const params = new URLSearchParams({
        symbols: JSON.stringify(binanceSymbols),
      });
      const response = await fetch(
        `https://api.binance.com/api/v3/ticker/24hr?${params.toString()}`,
        { cache: "no-store" },
      );

      if (!response.ok) {
        throw new Error("Unable to fetch Binance market data");
      }

      const payload = (await response.json()) as TickerResponse[];
      const nextCoins = payload
        .map((ticker) => {
          const meta = coinMeta[ticker.symbol];
          if (!meta) return null;

          return {
            ...meta,
            pair: ticker.symbol,
            price: Number(ticker.lastPrice),
            change: Number(ticker.priceChangePercent),
            quoteVolume: Number(ticker.quoteVolume),
            baseVolume: Number(ticker.volume),
            high: Number(ticker.highPrice),
            low: Number(ticker.lowPrice),
            trades: ticker.count,
          } satisfies MarketCoin;
        })
        .filter((coin): coin is MarketCoin => Boolean(coin));

      if (nextCoins.length) {
        setCoins(nextCoins);
      }
      setLastUpdated(new Date());
    } catch {
      setError(t("market.demoDataWarning"));
    } finally {
      setIsRefreshing(false);
    }
  }, [t]);

  useEffect(() => {
    void Promise.resolve().then(refreshMarketData);
    const intervalId = window.setInterval(() => {
      void refreshMarketData();
    }, 30000);

    return () => window.clearInterval(intervalId);
  }, [refreshMarketData]);

  const filteredCoins = useMemo(() => {
    const normalizedSearch = search.trim().toLowerCase();

    return coins.filter((coin) => {
      const matchesCategory =
        activeCategory === "all" || coin.category === activeCategory;
      const matchesSearch =
        !normalizedSearch ||
        coin.symbol.toLowerCase().includes(normalizedSearch) ||
        coin.name.toLowerCase().includes(normalizedSearch) ||
        coin.pair.toLowerCase().includes(normalizedSearch);

      return matchesCategory && matchesSearch;
    });
  }, [activeCategory, coins, search]);

  const popularCoins = [...coins]
    .filter((coin) => coin.featured)
    .sort((a, b) => b.quoteVolume - a.quoteVolume)
    .slice(0, 3);
  const newCoins = [...coins].slice(-3).reverse();
  const gainers = [...coins].sort((a, b) => b.change - a.change).slice(0, 3);
  const volumeLeaders = [...coins].sort((a, b) => b.quoteVolume - a.quoteVolume).slice(0, 3);

  return (
    <>
      <main className="min-h-screen bg-[#10141d] text-white">
        <MarketPageHeader />

        <section className="mx-auto w-full max-w-[1280px] px-4 py-7 sm:px-6 lg:px-8">
          <div className="flex flex-col gap-4 border-b border-white/10 pb-5 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <div className="flex flex-wrap gap-6 text-lg font-black text-slate-500">
                {mainTabs.map((tab, index) => (
                  <button
                    className={`relative py-2 transition hover:text-white ${
                      index === 0 ? "text-white" : ""
                    }`}
                    key={tab}
                    type="button"
                  >
                    {t(tab)}
                    {index === 0 ? (
                      <span className="absolute inset-x-0 -bottom-1 mx-auto h-1 w-8 rounded-full bg-yellow-400" />
                    ) : null}
                  </button>
                ))}
              </div>
              <p className="mt-4 max-w-3xl text-sm leading-6 text-slate-400">
                {t("market.pageDescription")}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2 text-xs font-bold text-slate-400">
              <span className="rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2">
                {t("market.apiSource")}
              </span>
              <span className="rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2">
                {lastUpdated
                  ? t("market.updatedAt", {
                      time: lastUpdated.toLocaleTimeString(locale),
                    })
                  : t("market.loadingData")}
              </span>
            </div>
          </div>

          <div className="mt-6 grid gap-4 lg:grid-cols-4">
            <MarketSummaryCard
              title={t("market.summary.popular")}
              coins={popularCoins}
              icon={<Star size={15} />}
            />
            <MarketSummaryCard
              title={t("market.summary.new")}
              coins={newCoins}
              icon={<Bell size={15} />}
            />
            <MarketSummaryCard
              title={t("market.summary.topGainers")}
              coins={gainers}
              icon={<ArrowUpRight size={15} />}
            />
            <MarketSummaryCard
              title={t("market.summary.volumeLeaders")}
              coins={volumeLeaders}
              icon={<BarChart3 size={15} />}
            />
          </div>

          <div className="mt-8 flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex flex-wrap gap-5 text-sm font-bold text-slate-400">
              {[
                "market.tabs.watchlist",
                "market.tabs.crypto",
                "market.tabs.spot",
                "market.tabs.futures",
                "market.tabs.tradfi",
                "market.tabs.alpha",
              ].map(
                (tab, index) => (
                  <button
                    className={`relative py-2 transition hover:text-white ${
                      index === 1 ? "text-white" : ""
                    }`}
                    key={tab}
                    type="button"
                  >
                    {t(tab)}
                    {index === 1 ? (
                      <span className="absolute inset-x-0 -bottom-1 mx-auto h-1 w-6 rounded-full bg-yellow-400" />
                    ) : null}
                  </button>
                ),
              )}
            </div>

            <div className="flex items-center gap-2">
              <label className="flex h-11 min-w-0 items-center gap-2 rounded-lg border border-white/10 bg-white/[0.04] px-3 text-slate-300 focus-within:border-yellow-300/60">
                <Search size={18} />
                <input
                  className="w-full min-w-0 bg-transparent text-sm font-semibold text-white outline-none placeholder:text-slate-500 sm:w-64"
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder={t("market.searchPlaceholder")}
                  value={search}
                />
              </label>
              <button
                className="grid h-11 w-11 place-items-center rounded-lg border border-white/10 bg-white/[0.04] text-yellow-300 transition hover:border-yellow-300/50 hover:bg-yellow-300/10 disabled:opacity-60"
                disabled={isRefreshing}
                onClick={refreshMarketData}
                title={t("market.refreshPrices")}
                type="button"
              >
                <RefreshCw className={isRefreshing ? "animate-spin" : ""} size={18} />
              </button>
            </div>
          </div>

          <div className="mt-4 flex gap-2 overflow-x-auto pb-2">
            {categoryTabs.map((category) => (
              <button
                className={`h-9 shrink-0 rounded-lg px-4 text-sm font-black transition ${
                  activeCategory === category
                    ? "bg-slate-700 text-white"
                    : "text-slate-400 hover:bg-white/[0.04] hover:text-white"
                }`}
                key={category}
                onClick={() => setActiveCategory(category)}
                type="button"
              >
                {category === "all" ? t("market.categories.all") : category}
              </button>
            ))}
          </div>

          <section className="mt-4">
            <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <h1 className="text-lg font-black">
                  {t("market.liquidityTitle")}
                </h1>
                <p className="mt-2 max-w-4xl text-xs leading-5 text-slate-500">
                  {t("market.liquidityDescription")}
                </p>
              </div>
              {error ? (
                <p className="rounded-lg border border-yellow-300/20 bg-yellow-300/10 px-3 py-2 text-xs font-bold text-yellow-100">
                  {error}
                </p>
              ) : null}
            </div>

            <div className="overflow-x-auto rounded-lg border border-white/10 bg-[#10141d]">
              <table className="w-full min-w-[920px] text-left text-sm">
                <thead className="border-b border-white/10 text-xs font-bold text-slate-500">
                  <tr>
                    <th className="px-4 py-4">{t("market.table.name")}</th>
                    <th className="px-4 py-4 text-right">{t("market.price")}</th>
                    <th className="px-4 py-4 text-right">24h</th>
                    <th className="px-4 py-4 text-right">{t("market.volume")} 24h</th>
                    <th className="px-4 py-4 text-right">{t("market.table.highLow24h")}</th>
                    <th className="px-4 py-4 text-right">{t("market.table.trades")}</th>
                    <th className="px-4 py-4 text-right">{t("market.table.actions")}</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredCoins.map((coin) => (
                    <MarketTableRow coin={coin} key={coin.pair} />
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </section>
      </main>
    </>
  );
}

function MarketPageHeader() {
  const { isAuthenticated, isLoading } = useAuth();

  if (!isLoading && isAuthenticated) {
    return <AppHeader />;
  }

  return <Header />;
}

function MarketSummaryCard({
  coins,
  icon,
  title,
}: {
  coins: MarketCoin[];
  icon: ReactNode;
  title: string;
}) {
  const { t } = useLanguage();

  return (
    <section className="rounded-lg border border-slate-700 bg-[#121722] p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-xs font-black">
          <span className="text-yellow-300">{icon}</span>
          {title}
        </h2>
        <button className="text-xs font-bold text-slate-300 hover:text-white" type="button">
          {t("market.summary.more")}
        </button>
      </div>
      <div className="grid gap-3">
        {coins.map((coin) => (
          <div className="grid grid-cols-[1fr_auto_auto] items-center gap-3" key={coin.pair}>
            <span className="flex min-w-0 items-center gap-2">
              <Image
                alt={`${coin.name} logo`}
                className="h-6 w-6 rounded-full object-contain"
                height={24}
                src={coin.icon}
                width={24}
              />
              <strong className="truncate text-sm">{coin.symbol}</strong>
            </span>
            <strong className="text-sm">{formatPrice(coin.price)}</strong>
            <span className={`text-sm font-black ${coin.change >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
              {coin.change >= 0 ? "+" : ""}
              {coin.change.toFixed(2)}%
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}

function MarketTableRow({ coin }: { coin: MarketCoin }) {
  const { t } = useLanguage();
  const isUp = coin.change >= 0;

  return (
    <tr className="border-b border-white/[0.04] transition hover:bg-white/[0.03]">
      <td className="px-4 py-5">
        <div className="flex items-center gap-3">
          <Image
            alt={`${coin.name} logo`}
            className="h-8 w-8 rounded-full object-contain"
            height={32}
            src={coin.icon}
            width={32}
          />
          <div className="min-w-0">
            <strong className="text-base">{coin.symbol}</strong>
            <span className="ml-1 text-sm text-slate-500">{coin.name}</span>
            <p className="mt-1 text-xs font-bold text-slate-600">{coin.pair}</p>
          </div>
        </div>
      </td>
      <td className="px-4 py-5 text-right">
        <strong className="block text-base">{formatPrice(coin.price)}</strong>
        <span className="text-xs text-slate-500">{formatPrice(coin.price, 6)}</span>
      </td>
      <td className={`px-4 py-5 text-right font-black ${isUp ? "text-emerald-400" : "text-rose-400"}`}>
        <span className="inline-flex items-center justify-end gap-1">
          {isUp ? <ArrowUpRight size={16} /> : <ArrowDownRight size={16} />}
          {isUp ? "+" : ""}
          {coin.change.toFixed(2)}%
        </span>
      </td>
      <td className="px-4 py-5 text-right font-bold">{formatCompactUsd(coin.quoteVolume)}</td>
      <td className="px-4 py-5 text-right text-slate-300">
        <strong>{formatPrice(coin.high)}</strong>
        <span className="mx-1 text-slate-600">/</span>
        <strong>{formatPrice(coin.low)}</strong>
      </td>
      <td className="px-4 py-5 text-right font-bold">{formatCompactNumber(coin.trades)}</td>
      <td className="px-4 py-5">
        <div className="flex justify-end gap-2 text-slate-300">
          <button
            className="grid h-9 w-9 place-items-center rounded-lg border border-white/10 transition hover:border-yellow-300/50 hover:text-yellow-300"
            title={t("market.actions.viewChart")}
            type="button"
          >
            <CandlestickChart size={17} />
          </button>
          <button
            className="grid h-9 w-9 place-items-center rounded-lg border border-white/10 transition hover:border-cyan-300/50 hover:text-cyan-300"
            title={t("market.actions.watch")}
            type="button"
          >
            <Star size={17} />
          </button>
        </div>
      </td>
    </tr>
  );
}

function formatPrice(value: number, maximumFractionDigits = value >= 1 ? 2 : 6) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits,
  }).format(value);
}

function formatCompactUsd(value: number) {
  return `$${formatCompactValue(value)}`;
}

function formatCompactNumber(value: number) {
  return formatCompactValue(value);
}

function formatCompactValue(value: number) {
  const sign = value < 0 ? "-" : "";
  const absoluteValue = Math.abs(value);
  const units = [
    { suffix: "T", value: 1_000_000_000_000 },
    { suffix: "B", value: 1_000_000_000 },
    { suffix: "M", value: 1_000_000 },
    { suffix: "K", value: 1_000 },
  ];
  const unit = units.find((item) => absoluteValue >= item.value);

  if (!unit) {
    return `${sign}${trimTrailingZeros(absoluteValue.toFixed(2))}`;
  }

  const scaled = absoluteValue / unit.value;
  return `${sign}${trimTrailingZeros(scaled.toFixed(2))}${unit.suffix}`;
}

function trimTrailingZeros(value: string) {
  return value.replace(/\.0+$/, "").replace(/(\.\d*[1-9])0+$/, "$1");
}
