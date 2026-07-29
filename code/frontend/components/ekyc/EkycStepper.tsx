"use client";

import { useLanguage } from "@/contexts/LanguageContext";
import { motion } from "framer-motion";
import { CheckCircle2, FileScan, Hourglass, ScanFace } from "lucide-react";

type EkycStepperProps = {
  currentStep: 1 | 2 | 3;
  documentCompleted: boolean;
  videoCompleted: boolean;
  processingCompleted: boolean;
  canAccessStep?: (step: 1 | 2 | 3) => boolean;
  onStepSelect?: (step: 1 | 2 | 3) => void;
};

export function EkycStepper({
  currentStep,
  documentCompleted,
  videoCompleted,
  processingCompleted,
  canAccessStep,
  onStepSelect,
}: EkycStepperProps) {
  const { t } = useLanguage();
  const steps = [
    {
      step: 1 as const,
      label: t("ekyc.stepper.step1"),
      description: t("ekyc.stepper.documentVerification"),
      icon: FileScan,
      completed: documentCompleted,
      active: currentStep === 1,
    },
    {
      step: 2 as const,
      label: t("ekyc.stepper.step2"),
      description: t("ekyc.stepper.faceVoiceChallenge"),
      icon: ScanFace,
      completed: videoCompleted,
      active: currentStep === 2,
    },
    {
      step: 3 as const,
      label: t("ekyc.stepper.step3"),
      description: t("ekyc.stepper.reviewProcessing"),
      icon: Hourglass,
      completed: processingCompleted,
      active: currentStep === 3,
    },
  ];

  return (
    <div className="glass-panel p-4">
      <div className="grid gap-3 md:grid-cols-3">
        {steps.map((step, index) => {
          const Icon = step.icon;
          const accessible = canAccessStep?.(step.step) ?? true;
          return (
            <motion.button
              aria-current={step.active ? "step" : undefined}
              aria-disabled={!accessible}
              className={`step-card ${step.active ? "active" : ""} ${step.completed ? "completed" : ""} ${accessible ? "clickable" : "locked"}`}
              disabled={!accessible}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              onClick={() => onStepSelect?.(step.step)}
              transition={{ delay: index * 0.08 }}
              key={step.label}
              type="button"
            >
              <span className={step.completed || step.active ? "step-index active" : "step-index"}>
                {step.completed ? <CheckCircle2 size={18} /> : index + 1}
              </span>
              <Icon className="text-cyan-200" size={20} />
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-sm font-bold text-white">{step.label}</p>
                  {step.active ? (
                    <span className="current-step-pill">
                      {t("ekyc.stepper.current")}
                    </span>
                  ) : null}
                </div>
                <p className="text-xs text-slate-400">{step.description}</p>
              </div>
            </motion.button>
          );
        })}
      </div>
    </div>
  );
}
