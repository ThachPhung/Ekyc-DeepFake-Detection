"use client";

import { motion } from "framer-motion";
import { ArrowUpRight } from "lucide-react";
import type { MarketStat } from "@/app/data/market";

const toneStroke: Record<MarketStat["tone"], string> = {
  amber: "#f59e0b",
  cyan: "#22d3ee",
  fuchsia: "#a855f7",
  violet: "#8b5cf6",
};

export function StatCard({ label, value, change, points, tone }: MarketStat) {
  const gradientId = `stat-gradient-${label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
  const max = Math.max(...points);
  const min = Math.min(...points);
  const coordinates = points
    .map((point, index) => {
      const x = (index / (points.length - 1)) * 240;
      const y = 70 - ((point - min) / (max - min || 1)) * 54;
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <motion.article
      className={`glass-panel stat-card tone-${tone} p-5`}
      initial={{ opacity: 0, y: 18 }}
      transition={{ duration: 0.36 }}
      viewport={{ once: true, margin: "-80px" }}
      whileHover={{ y: -6, scale: 1.012 }}
      whileInView={{ opacity: 1, y: 0 }}
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold text-slate-300">{label}</p>
          <strong className="mt-2 block text-3xl font-black text-white">{value}</strong>
        </div>
        <span className="inline-flex items-center gap-1 rounded-full border border-emerald-400/30 bg-emerald-400/10 px-2.5 py-1 text-sm font-black text-emerald-300">
          <ArrowUpRight size={15} />
          {change}
        </span>
      </div>
      <svg className="mt-4 h-20 w-full overflow-visible" viewBox="0 0 240 82" preserveAspectRatio="none">
        <defs>
          <linearGradient id={gradientId} x1="0" x2="1" y1="0" y2="0">
            <stop stopColor={toneStroke[tone]} stopOpacity=".2" />
            <stop offset=".55" stopColor={toneStroke[tone]} />
            <stop offset="1" stopColor="#22d3ee" />
          </linearGradient>
        </defs>
        <polyline
          fill="none"
          opacity=".18"
          points={coordinates}
          stroke={toneStroke[tone]}
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="10"
        />
        <motion.polyline
          fill="none"
          initial={{ pathLength: 0 }}
          points={coordinates}
          stroke={`url(#${gradientId})`}
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="4"
          transition={{ duration: 1.1, ease: "easeOut" }}
          viewport={{ once: true }}
          whileInView={{ pathLength: 1 }}
        />
        <circle cx="232" cy="16" fill={toneStroke[tone]} r="4" />
      </svg>
    </motion.article>
  );
}
