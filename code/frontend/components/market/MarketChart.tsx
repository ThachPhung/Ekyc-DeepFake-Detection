"use client";

import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import Image from "next/image";
import { Activity, Crosshair, Maximize2 } from "lucide-react";
import { chartSeries, type MarketAsset } from "@/app/data/market";
import { useLanguage } from "@/contexts/LanguageContext";

const ranges = ["1H", "1D", "1W", "1M", "1Y", "ALL"];

export function MarketChart({ asset }: { asset?: MarketAsset }) {
  const { t } = useLanguage();
  const [activeRange, setActiveRange] = useState("1D");
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const displayedAsset = asset ?? {
    symbol: "BTC",
    name: "Bitcoin",
    icon: "/icons/bitcoin.png",
    price: "$67,842.31",
    change: 2.45,
    volume: "$32.45B",
  };
  const numericPrice =
    Number(displayedAsset.price.replace(/[$,]/g, "")) || 0;

  const chart = useMemo(() => {
    const max = Math.max(...chartSeries);
    const min = Math.min(...chartSeries);
    const points = chartSeries.map((value, index) => {
      const x = 22 + (index / (chartSeries.length - 1)) * 506;
      const y = 230 - ((value - min) / (max - min || 1)) * 176;
      return { x, y, value };
    });
    return {
      line: points.map((point) => `${point.x},${point.y}`).join(" "),
      points,
    };
  }, []);

  const hoverPoint = hoverIndex === null ? null : chart.points[hoverIndex];

  return (
    <motion.section
      className="glass-panel market-chart-panel p-5"
      initial={{ opacity: 0, y: 18 }}
      transition={{ duration: 0.45 }}
      viewport={{ once: true, margin: "-100px" }}
      whileInView={{ opacity: 1, y: 0 }}
    >
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
        <div>
          <div className="flex items-center gap-3">
            <span className="asset-token">
              <Image
                alt={`${displayedAsset.name} logo`}
                className="h-7 w-7 rounded-full object-contain"
                height={28}
                src={displayedAsset.icon}
                width={28}
              />
            </span>
            <div>
              <h2 className="font-bold">{displayedAsset.symbol} / USDT</h2>
              <p className="text-xs text-slate-400">
                {displayedAsset.name} {t("market.marketSuffix")}
              </p>
            </div>
          </div>
          <div className="mt-5 flex flex-wrap items-end gap-3">
            <strong className="text-3xl font-black">{displayedAsset.price}</strong>
            <span
              className={`pb-1 font-bold ${
                displayedAsset.change >= 0
                  ? "text-emerald-300"
                  : "text-rose-300"
              }`}
            >
              {displayedAsset.change >= 0 ? "+" : ""}
              {displayedAsset.change.toFixed(2)}%
            </span>
            <span className="pb-1 text-sm text-slate-400">
              Vol {displayedAsset.volume}
            </span>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs font-bold text-slate-300">
          <button
            className="chart-icon-button"
            type="button"
            aria-label={t("market.chart.crosshair")}
          >
            <Crosshair size={15} />
          </button>
          <button
            className="chart-icon-button"
            type="button"
            aria-label={t("market.chart.maximize")}
          >
            <Maximize2 size={15} />
          </button>
          {ranges.map((range) => (
            <button
              className={`time-filter ${range === activeRange ? "active" : ""}`}
              key={range}
              onClick={() => setActiveRange(range)}
              type="button"
            >
              {range}
            </button>
          ))}
        </div>
      </div>

      <div className="relative mt-4">
        {hoverPoint && (
          <div
            className="chart-tooltip"
            style={{
              left: `min(calc(${(hoverPoint.x / 550) * 100}% + 8px), calc(100% - 150px))`,
              top: `${Math.max(12, hoverPoint.y - 56)}px`,
            }}
          >
            <span>{displayedAsset.symbol} / USDT</span>
            <strong>
              $
              {(numericPrice * (0.985 + hoverPoint.value / 10000)).toLocaleString(
                "en-US",
                { maximumFractionDigits: 2 },
              )}
            </strong>
            <small>{t("market.chart.aiConfidence", { value: 91 })}</small>
          </div>
        )}
        <svg className="h-[360px] w-full" viewBox="0 0 550 310" preserveAspectRatio="none">
          <defs>
            <linearGradient id="chartFill" x1="0" x2="0" y1="0" y2="1">
              <stop stopColor="#22d3ee" stopOpacity="0.34" />
              <stop offset="1" stopColor="#8b5cf6" stopOpacity="0" />
            </linearGradient>
            <linearGradient id="chartStroke" x1="0" x2="1" y1="0" y2="0">
              <stop stopColor="#22d3ee" />
              <stop offset="0.55" stopColor="#2563eb" />
              <stop offset="1" stopColor="#a855f7" />
            </linearGradient>
          </defs>
          {[0, 1, 2, 3, 4].map((line) => (
            <line
              key={line}
              stroke="#26324f"
              strokeDasharray="6 8"
              x1="18"
              x2="532"
              y1={52 + line * 44}
              y2={52 + line * 44}
            />
          ))}
          {[0, 1, 2, 3, 4, 5].map((line) => (
            <line
              key={line}
              opacity=".42"
              stroke="#1b2748"
              x1={28 + line * 96}
              x2={28 + line * 96}
              y1="42"
              y2="282"
            />
          ))}
          <polygon fill="url(#chartFill)" points={`22,260 ${chart.line} 528,260`} />
          <motion.polyline
            fill="none"
            initial={{ pathLength: 0 }}
            points={chart.line}
            stroke="url(#chartStroke)"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="5"
            transition={{ duration: 1.1, ease: "easeOut" }}
            viewport={{ once: true }}
            whileInView={{ pathLength: 1 }}
          />
          {chart.points.map((point, index) => {
            const height = 34 + ((point.value + index * 11) % 98);
            return (
              <rect
                fill={index % 3 === 0 ? "#22d3ee" : "#7c3aed"}
                height={height}
                key={`${point.value}-${index}`}
                opacity={hoverIndex === index ? "0.95" : "0.54"}
                rx="3"
                width="9"
                x={point.x - 4}
                y={292 - height}
              />
            );
          })}
          {chart.points.map((point, index) => (
            <rect
              fill="transparent"
              height="260"
              key={`hit-${index}`}
              onMouseEnter={() => setHoverIndex(index)}
              onMouseLeave={() => setHoverIndex(null)}
              width="24"
              x={point.x - 12}
              y="34"
            />
          ))}
          {hoverPoint && (
            <g>
              <line
                stroke="#22d3ee"
                strokeDasharray="4 6"
                strokeWidth="1.5"
                x1={hoverPoint.x}
                x2={hoverPoint.x}
                y1="42"
                y2="292"
              />
              <circle cx={hoverPoint.x} cy={hoverPoint.y} fill="#050816" r="7" stroke="#22d3ee" strokeWidth="3" />
            </g>
          )}
        </svg>
        <div className="chart-footer">
          <span>00:00</span>
          <span>04:00</span>
          <span>08:00</span>
          <span>12:00</span>
          <span>16:00</span>
          <span>20:00</span>
        </div>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        {["Order Flow +18%", "Liquidity Strong", "AI Volatility Low"].map((label) => (
          <div className="chart-metric" key={label}>
            <Activity size={15} />
            {label}
          </div>
        ))}
      </div>
    </motion.section>
  );
}
