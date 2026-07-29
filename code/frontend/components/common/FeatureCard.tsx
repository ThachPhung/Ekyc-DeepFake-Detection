"use client";

import { motion } from "framer-motion";
import {
  Activity,
  BrainCircuit,
  LucideIcon,
  PieChart,
  ShieldCheck,
} from "lucide-react";

type FeatureCardProps = {
  title: string;
  description: string;
  icon: "activity" | "brain" | "pie" | "shield";
  tone: "cyan" | "violet" | "amber" | "emerald";
};

const icons: Record<FeatureCardProps["icon"], LucideIcon> = {
  activity: Activity,
  brain: BrainCircuit,
  pie: PieChart,
  shield: ShieldCheck,
};

export function FeatureCard({ title, description, icon, tone }: FeatureCardProps) {
  const Icon = icons[icon];

  return (
    <motion.article
      className={`glass-panel feature-card tone-${tone} p-5`}
      initial={{ opacity: 0, y: 18 }}
      transition={{ duration: 0.35 }}
      viewport={{ once: true, margin: "-80px" }}
      whileHover={{ y: -8, scale: 1.015 }}
      whileInView={{ opacity: 1, y: 0 }}
    >
      <div className="feature-icon">
        <Icon size={30} strokeWidth={1.8} />
      </div>
      <h3 className="mt-4 text-lg font-bold text-white">{title}</h3>
      <p className="mt-2 text-sm leading-6 text-slate-300">{description}</p>
      <span className="feature-arrow">-&gt;</span>
    </motion.article>
  );
}
