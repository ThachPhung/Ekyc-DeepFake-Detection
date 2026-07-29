"use client";

import { motion } from "framer-motion";
import Image from "next/image";
import { ArrowDownRight, ArrowUpRight, RadioTower } from "lucide-react";
import { marketAssets } from "@/app/data/market";
import { useLanguage } from "@/contexts/LanguageContext";

export function MarketTable() {
  const { t } = useLanguage();

  return (
    <motion.section
      className="glass-panel market-table-panel overflow-hidden"
      initial={{ opacity: 0, y: 18 }}
      transition={{ duration: 0.45 }}
      viewport={{ once: true, margin: "-100px" }}
      whileInView={{ opacity: 1, y: 0 }}
    >
      <div className="flex items-center justify-between border-b border-white/10 px-5 py-4">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-bold">{t("market.overview")}</h2>
          <span className="live-badge">
            <RadioTower size={12} />
            {t("market.live")}
          </span>
        </div>
        <a className="text-sm font-semibold text-cyan-300 hover:text-cyan-100" href="#">
          {t("market.viewAll")}
        </a>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] text-left text-sm">
          <thead className="bg-indigo-950/25 text-xs uppercase text-slate-400">
            <tr>
              <th className="px-5 py-4 font-semibold">{t("market.asset")}</th>
              <th className="px-5 py-4 font-semibold">{t("market.price")}</th>
              <th className="px-5 py-4 font-semibold">{t("market.change24h")}</th>
              <th className="px-5 py-4 font-semibold">{t("market.volume")}</th>
              <th className="px-5 py-4 font-semibold">{t("market.trend")}</th>
              <th className="px-5 py-4 font-semibold">{t("market.status")}</th>
            </tr>
          </thead>
          <tbody>
            {marketAssets.map((asset, index) => {
              const isUp = asset.change > 0;
              return (
                <motion.tr
                  className="market-row border-t border-white/5"
                  initial={{ opacity: 0, x: -12 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: index * 0.035 }}
                  key={asset.symbol}
                >
                  <td className="px-5 py-4">
                    <div className="flex items-center gap-3">
                      <span className="asset-token">
                        <Image
                          alt={`${asset.name} logo`}
                          className="h-7 w-7 rounded-full object-contain"
                          height={28}
                          src={asset.icon}
                          width={28}
                        />
                      </span>
                      <div>
                        <p className="font-bold text-white">{asset.name}</p>
                        <p className="text-xs text-slate-400">{asset.symbol}</p>
                      </div>
                    </div>
                  </td>
                  <td className="px-5 py-4 font-bold text-white">{asset.price}</td>
                  <td
                    className={`px-5 py-4 font-bold ${
                      isUp ? "text-emerald-300" : "text-rose-300"
                    }`}
                  >
                    <span className="inline-flex items-center gap-1">
                      {isUp ? <ArrowUpRight size={15} /> : <ArrowDownRight size={15} />}
                      {isUp ? "+" : ""}
                      {asset.change.toFixed(2)}%
                    </span>
                  </td>
                  <td className="px-5 py-4 font-semibold text-slate-200">
                    {asset.volume}
                  </td>
                  <td className="px-5 py-4">
                    <MiniSparkline up={isUp} seed={index + 1} />
                  </td>
                  <td className="px-5 py-4">
                    <span className={`status-pill ${isUp ? "success" : "danger"}`}>
                      {isUp ? t("market.up") : t("market.down")}
                    </span>
                  </td>
                </motion.tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </motion.section>
  );
}

function MiniSparkline({ up, seed }: { up: boolean; seed: number }) {
  const points = Array.from({ length: 8 }, (_, index) => {
    const x = index * 16;
    const base = up ? 34 - index * 2.8 : 15 + index * 2.6;
    const wave = ((index * seed * 7) % 13) - 6;
    return `${x},${Math.max(5, Math.min(40, base + wave))}`;
  }).join(" ");

  return (
    <svg className="h-10 w-32" viewBox="0 0 112 44" preserveAspectRatio="none">
      <polyline
        fill="none"
        points={points}
        stroke={up ? "#21f6a4" : "#fb7185"}
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="3"
      />
    </svg>
  );
}
