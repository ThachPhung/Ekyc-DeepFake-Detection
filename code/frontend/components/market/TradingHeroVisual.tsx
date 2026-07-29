"use client";

import { motion } from "framer-motion";
import { Activity, BrainCircuit, ShieldCheck, TrendingUp } from "lucide-react";
import { candleSeries } from "@/app/data/market";
import { useLanguage } from "@/contexts/LanguageContext";

export function TradingHeroVisual() {
  const { t } = useLanguage();

  return (
    <motion.div
      animate={{ opacity: 1, y: 0 }}
      className="relative z-10 flex min-h-[500px] items-center justify-center lg:min-h-[650px]"
      initial={{ opacity: 0, y: 24 }}
      transition={{ duration: 0.7, ease: "easeOut" }}
    >
      <div className="hero-orbit" />
      <div className="trading-visual pro-hero-visual">
        <div className="visual-grid" />
        <div className="market-ticker">
          {["BTC +2.45%", "ETH +1.67%", "BNB +0.84%", "SOL +4.18%", "XRP -0.74%", "DOGE +1.12%", "ADA -0.38%"].map(
            (item) => (
              <span key={item}>{item}</span>
            ),
          )}
        </div>

        <motion.div
          animate={{ y: [0, -12, 0] }}
          className="floating-widget btc-widget"
          transition={{ duration: 5, repeat: Infinity, ease: "easeInOut" }}
        >
          <span className="widget-label">BTC / USDT</span>
          <strong>$67,842.31</strong>
          <span className="text-emerald-300">+2.45%</span>
        </motion.div>

        <motion.div
          animate={{ y: [0, 10, 0] }}
          className="floating-widget confidence-widget"
          transition={{ duration: 5.8, repeat: Infinity, ease: "easeInOut" }}
        >
          <BrainCircuit size={18} />
          <span>{t("market.visual.aiConfidence")}</span>
          <strong>92%</strong>
        </motion.div>

        <motion.div
          animate={{ scale: [1, 1.04, 1], opacity: [0.88, 1, 0.88] }}
          className="ai-core"
          transition={{ duration: 3.8, repeat: Infinity, ease: "easeInOut" }}
        >
          <div className="ai-mark">AI</div>
        </motion.div>

        <svg
          aria-label={t("market.visual.chartLabel")}
          className="hero-chart"
          role="img"
          viewBox="0 0 460 300"
        >
          <defs>
            <linearGradient id="heroArea" x1="0" x2="0" y1="0" y2="1">
              <stop stopColor="#22d3ee" stopOpacity="0.28" />
              <stop offset="1" stopColor="#7c3aed" stopOpacity="0" />
            </linearGradient>
            <linearGradient id="heroLine" x1="0" x2="1" y1="0" y2="0">
              <stop stopColor="#22d3ee" />
              <stop offset=".48" stopColor="#8b5cf6" />
              <stop offset="1" stopColor="#ec4899" />
            </linearGradient>
          </defs>
          {[0, 1, 2, 3, 4, 5].map((line) => (
            <line
              key={line}
              stroke="#233457"
              strokeDasharray="5 9"
              strokeWidth="1"
              x1="18"
              x2="444"
              y1={44 + line * 35}
              y2={44 + line * 35}
            />
          ))}
          <path
            d="M22 216 C68 180 86 202 116 150 S178 116 212 128 266 168 304 92 374 52 436 70"
            fill="none"
            stroke="url(#heroLine)"
            strokeLinecap="round"
            strokeWidth="4"
          />
          <path
            d="M22 216 C68 180 86 202 116 150 S178 116 212 128 266 168 304 92 374 52 436 70 L436 244 L22 244 Z"
            fill="url(#heroArea)"
          />
          {candleSeries.map((candle, index) => {
            const up = candle.close < candle.open;
            const bodyY = Math.min(candle.open, candle.close);
            const bodyHeight = Math.abs(candle.close - candle.open) || 8;
            return (
              <motion.g
                initial={{ opacity: 0, y: 18 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.035, duration: 0.35 }}
                key={candle.x}
              >
                <line
                  stroke={up ? "#21f6a4" : "#fb4d7d"}
                  strokeWidth="2"
                  x1={candle.x}
                  x2={candle.x}
                  y1={candle.high}
                  y2={candle.low}
                />
                <rect
                  fill={up ? "#21f6a4" : "#fb4d7d"}
                  height={bodyHeight}
                  rx="3"
                  width="12"
                  x={candle.x - 6}
                  y={bodyY}
                />
                <rect
                  fill={up ? "#22d3ee" : "#7c3aed"}
                  height={candle.volume * 0.38}
                  opacity=".62"
                  rx="2"
                  width="10"
                  x={candle.x - 5}
                  y={276 - candle.volume * 0.38}
                />
              </motion.g>
            );
          })}
        </svg>

        <motion.div
          animate={{ x: [0, 8, 0] }}
          className="signal-card pro-signal-card"
          transition={{ duration: 4.6, repeat: Infinity, ease: "easeInOut" }}
        >
          <div className="flex items-center gap-2">
            <TrendingUp size={16} />
            <span>{t("market.visual.aiSignal")}</span>
          </div>
          <strong>{t("market.visual.longBtc")}</strong>
          <small>{t("market.visual.tradeSetup")}</small>
        </motion.div>

        <div className="indicator-stack">
          <span><Activity size={14} /> RSI 62.8</span>
          <span><ShieldCheck size={14} /> {t("market.visual.riskLow")}</span>
          <span><BrainCircuit size={14} /> {t("market.visual.patternBreakout")}</span>
        </div>
      </div>
    </motion.div>
  );
}
