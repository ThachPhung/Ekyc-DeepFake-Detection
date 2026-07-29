"use client";

import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { EkycStepper } from "@/components/ekyc/EkycStepper";
import { FaceCaptureRecorder } from "@/components/ekyc/FaceCaptureRecorder";
import { UploadCard } from "@/components/ekyc/UploadCard";
import { AppHeader } from "@/components/site/AppHeader";
import { useLanguage } from "@/contexts/LanguageContext";
import { ApiError } from "@/lib/api";
import {
  createEkycRequest,
  getEkycRequest,
  getMyEkycStatus,
  getMyVerifiedIdentity,
  type EkycDocumentType,
  type EkycRequestResponse,
  type EkycRequestStatus,
  type MyVerifiedIdentityResponse,
} from "@/services/ekyc.service";
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  FileCheck2,
  Loader2,
  RefreshCcw,
  ScanFace,
  Send,
  ShieldAlert,
  Upload,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

const terminalStatuses: EkycRequestStatus[] = [
  "SUCCESS",
  "FAILED",
  "MANUAL_REVIEW",
];
const POLL_INTERVAL_ACTIVE_MS = 6000;
const POLL_INTERVAL_HIDDEN_MS = 15000;
const POLL_INTERVAL_MAX_MS = 30000;

type VerificationStep = 1 | 2 | 3;

type LocalVoiceChallenge = {
  displayDigits: string[];
  displayText: string;
};

const documentTypeOptions: Array<{
  value: EkycDocumentType;
}> = [
  { value: "CCCD" },
  { value: "GPLX" },
  { value: "HOCHIEU" },
];

function getDocumentTypeOption(documentType: EkycDocumentType) {
  return (
    documentTypeOptions.find((option) => option.value === documentType) ??
    documentTypeOptions[0]
  );
}

function formatMessage(error: unknown, fallback: string) {
  if (error instanceof ApiError) {
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return fallback;
}

function formatDisplayDate(value?: string | null, locale = "en-US") {
  if (!value) {
    return "-";
  }
  return new Date(value).toLocaleDateString(locale);
}

function isTerminal(status: EkycRequestStatus | undefined) {
  return status ? terminalStatuses.includes(status) : false;
}

function generateLocalVoiceChallenge(length = 6): LocalVoiceChallenge {
  const displayDigits = Array.from({ length }, () =>
    String(Math.floor(Math.random() * 10)),
  );

  return {
    displayDigits,
    displayText: displayDigits.join(" "),
  };
}

function ekycStateSnapshot(state: EkycRequestResponse | null) {
  if (!state) {
    return "";
  }

  return JSON.stringify({
    document_confirmed_at: state.document_confirmed_at,
    document_confirmed_fields: state.document_confirmed_fields,
    error_message: state.error_message,
    face_decision: state.face_decision,
    face_similarity: state.face_similarity,
    model_version: state.model_version,
    ocr_result: state.ocr_result,
    processed_at: state.processed_at,
    request_id: state.request_id,
    status: state.status,
    updated_at: state.updated_at,
    video_error_message: state.video_error_message,
    video_processed_at: state.video_processed_at,
    video_result: state.video_result,
    video_status: state.video_status,
  });
}

function resultMessage(
  requestState: EkycRequestResponse,
  t: (key: string) => string,
) {
  if (requestState.status === "SUCCESS") {
    return t("ekyc.messages.resultSuccess");
  }
  if (requestState.status === "MANUAL_REVIEW") {
    return t("ekyc.messages.resultManualReview");
  }
  if (requestState.status === "FAILED") {
    return t("ekyc.messages.resultFailed");
  }
  return t("ekyc.messages.resultProcessing");
}

function getProcessingTone(status?: EkycRequestStatus) {
  if (status === "SUCCESS") {
    return "success";
  }
  if (status === "FAILED") {
    return "danger";
  }
  return "default";
}

export default function EkycPage() {
  const { locale, t } = useLanguage();
  const [documentType, setDocumentType] = useState<EkycDocumentType>("CCCD");
  const [frontFile, setFrontFile] = useState<File | null>(null);
  const [backFile, setBackFile] = useState<File | null>(null);
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [requestState, setRequestState] = useState<EkycRequestResponse | null>(
    null,
  );
  const [isAlreadyVerified, setIsAlreadyVerified] = useState(false);
  const [verifiedAt, setVerifiedAt] = useState<string | null>(null);
  const [verifiedIdentity, setVerifiedIdentity] =
    useState<MyVerifiedIdentityResponse | null>(null);
  const [isLoadingStatus, setIsLoadingStatus] = useState(true);
  const [errorMessage, setErrorMessage] = useState("");
  const [successMessage, setSuccessMessage] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [voiceChallenge, setVoiceChallenge] = useState<LocalVoiceChallenge | null>(
    null,
  );
  const [currentStep, setCurrentStep] = useState<VerificationStep>(1);
  const activeStepRef = useRef<HTMLElement | null>(null);
  const hasRenderedInitialStepRef = useRef(false);

  const selectedDocumentOption = getDocumentTypeOption(documentType);
  const selectedDocumentKey = `ekyc.documentTypes.${selectedDocumentOption.value}`;
  const selectedDocument = {
    backTitle: t(`${selectedDocumentKey}.backTitle`),
    frontTitle: t(`${selectedDocumentKey}.frontTitle`),
    label: t(`${selectedDocumentKey}.label`),
    shortLabel: t(`${selectedDocumentKey}.shortLabel`),
    stepDescription: t(`${selectedDocumentKey}.stepDescription`),
  };
  const dateLocale = locale === "vi" ? "vi-VN" : "en-US";
  const hasDocumentFiles = Boolean(frontFile && backFile);
  const hasSubmittedRequest = Boolean(requestState);
  const requestStateSnapshot = useMemo(
    () => ekycStateSnapshot(requestState),
    [requestState],
  );
  const processingCompleted = Boolean(
    requestState && isTerminal(requestState.status),
  );

  const progress = useMemo(() => {
    if (isAlreadyVerified || requestState?.status === "SUCCESS") {
      return 100;
    }
    if (processingCompleted) {
      return 100;
    }
    if (hasSubmittedRequest) {
      return 86;
    }
    if (currentStep === 3 && videoFile) {
      return 78;
    }
    if (videoFile) {
      return 66;
    }
    if (hasDocumentFiles) {
      return 45;
    }
    if (frontFile || backFile) {
      return 20;
    }
    return 0;
  }, [
    backFile,
    frontFile,
    hasDocumentFiles,
    hasSubmittedRequest,
    currentStep,
    isAlreadyVerified,
    processingCompleted,
    requestState?.status,
    videoFile,
  ]);

  useEffect(() => {
    let isMounted = true;

    async function loadMyStatus() {
      try {
        const [status, identity] = await Promise.all([
          getMyEkycStatus(),
          getMyVerifiedIdentity(),
        ]);
        if (!isMounted) {
          return;
        }
        setIsAlreadyVerified(status.is_verified);
        setVerifiedAt(status.verified_at ?? null);
        setVerifiedIdentity(identity.is_verified ? identity : null);
        if (status.is_verified) {
          setCurrentStep(3);
        }
        if (status.latest_request && !status.is_verified) {
          setRequestState(status.latest_request);
          setCurrentStep(3);
        }
      } catch (error) {
        if (isMounted) {
          setErrorMessage(
            formatMessage(error, t("ekyc.messages.loadStatusFailed")),
          );
        }
      } finally {
        if (isMounted) {
          setIsLoadingStatus(false);
        }
      }
    }

    loadMyStatus();

    return () => {
      isMounted = false;
    };
  }, [t]);

  useEffect(() => {
    const requestId = requestState?.request_id;
    const requestStatus = requestState?.status;
    if (!requestId || isTerminal(requestStatus)) {
      return;
    }

    let cancelled = false;
    let timeoutId: number | null = null;
    let nextDelay =
      document.visibilityState === "visible"
        ? POLL_INTERVAL_ACTIVE_MS
        : POLL_INTERVAL_HIDDEN_MS;
    let previousSnapshot = requestStateSnapshot;

    const scheduleNextPoll = (delay: number) => {
      if (cancelled) {
        return;
      }
      timeoutId = window.setTimeout(runPoll, delay);
    };

    const runPoll = async () => {
      try {
        const nextState = await getEkycRequest(requestId);
        const nextSnapshot = ekycStateSnapshot(nextState);
        const stateChanged = previousSnapshot !== nextSnapshot;

        previousSnapshot = nextSnapshot;
        nextDelay = isTerminal(nextState.status)
          ? POLL_INTERVAL_ACTIVE_MS
          : stateChanged
            ? POLL_INTERVAL_ACTIVE_MS
            : Math.min(nextDelay + POLL_INTERVAL_ACTIVE_MS, POLL_INTERVAL_MAX_MS);

        setRequestState((currentState) =>
          ekycStateSnapshot(currentState) === nextSnapshot ? currentState : nextState,
        );
        if (nextState.status === "SUCCESS") {
          setIsAlreadyVerified(true);
          setVerifiedAt(nextState.processed_at ?? nextState.updated_at ?? null);
        }
        if (isTerminal(nextState.status)) {
          setSuccessMessage("");
          return;
        }
      } catch (error) {
        nextDelay = Math.min(nextDelay + POLL_INTERVAL_ACTIVE_MS, POLL_INTERVAL_MAX_MS);
        setErrorMessage(
          formatMessage(error, t("ekyc.messages.refreshStatusFailed")),
        );
      }

      const visibilityDelay =
        document.visibilityState === "visible"
          ? nextDelay
          : Math.max(nextDelay, POLL_INTERVAL_HIDDEN_MS);
      scheduleNextPoll(visibilityDelay);
    };

    scheduleNextPoll(nextDelay);

    return () => {
      cancelled = true;
      if (timeoutId !== null) {
        window.clearTimeout(timeoutId);
      }
    };
  }, [requestStateSnapshot, requestState?.request_id, requestState?.status, t]);

  function resetVoiceChallenge() {
    setVoiceChallenge(generateLocalVoiceChallenge());
  }

  useEffect(() => {
    if (isLoadingStatus) {
      return;
    }
    if (!hasRenderedInitialStepRef.current) {
      hasRenderedInitialStepRef.current = true;
      return;
    }

    window.setTimeout(() => {
      activeStepRef.current?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    }, 0);
  }, [currentStep, isLoadingStatus]);

  function resetFlow() {
    setFrontFile(null);
    setBackFile(null);
    setVideoFile(null);
    setRequestState(null);
    setVoiceChallenge(null);
    setCurrentStep(1);
    setErrorMessage("");
    setSuccessMessage("");
  }

  function resetDocumentFiles() {
    setFrontFile(null);
    setBackFile(null);
    setVideoFile(null);
    setRequestState(null);
    setVoiceChallenge(null);
    setCurrentStep(1);
    setErrorMessage("");
    setSuccessMessage("");
  }

  function handleDocumentTypeChange(nextType: EkycDocumentType) {
    if (nextType === documentType) {
      return;
    }
    setDocumentType(nextType);
    resetDocumentFiles();
  }

  function canAccessStep(step: VerificationStep) {
    if (hasSubmittedRequest || isAlreadyVerified) {
      return step === 3;
    }
    if (step === 1) {
      return true;
    }
    if (step === 2) {
      return hasDocumentFiles;
    }
    return Boolean(videoFile);
  }

  function handleStepSelect(step: VerificationStep) {
    if (!canAccessStep(step)) {
      return;
    }
    setErrorMessage("");
    setSuccessMessage("");
    setCurrentStep(step);
  }

  function handleNextFromDocuments() {
    setErrorMessage("");
    setSuccessMessage("");
    if (!hasDocumentFiles) {
      setErrorMessage(t("ekyc.messages.missingDocumentImages"));
      return;
    }
    if (!voiceChallenge) {
      resetVoiceChallenge();
    }
    setCurrentStep(2);
  }

  async function handleVoiceCapture(file: File | null) {
    if (!file) {
      setVideoFile(null);
      return;
    }

    setErrorMessage("");
    setSuccessMessage("");
    setVideoFile(file);
    setCurrentStep(3);
  }

  function handleVoiceSessionExpired() {
    setVideoFile(null);
    resetVoiceChallenge();
    setErrorMessage(t("ekyc.messages.sessionExpired"));
  }

  function handleVoiceRetry() {
    setVideoFile(null);
    setErrorMessage("");
    setSuccessMessage("");
    resetVoiceChallenge();
  }

  async function handleSubmitEkycSession(capturedVideoFile = videoFile) {
    if (
      !frontFile ||
      !backFile ||
      !capturedVideoFile ||
      !voiceChallenge?.displayText ||
      isSubmitting
    ) {
      if (!capturedVideoFile || !voiceChallenge?.displayText) {
        setErrorMessage(t("ekyc.messages.completeVoiceBeforeSubmit"));
      }
      return;
    }

    setErrorMessage("");
    setSuccessMessage("");
    setIsSubmitting(true);

    try {
      const response = await createEkycRequest({
        frontImage: frontFile,
        backImage: backFile,
        videoFile: capturedVideoFile,
        documentType,
        voiceChallengeText: voiceChallenge.displayText,
      });
      setRequestState(response);
      setCurrentStep(3);
      setSuccessMessage(t("ekyc.messages.submitReceived"));
    } catch (error) {
      setErrorMessage(formatMessage(error, t("ekyc.messages.submitFailed")));
    } finally {
      setIsSubmitting(false);
    }
  }

  const verifiedIdentityDetails = verifiedIdentity
    ? [
        {
          label: t("ekyc.fields.documentType"),
          value: t(
            `ekyc.documentTypes.${
              getDocumentTypeOption(verifiedIdentity.document_type ?? documentType)
                .value
            }.shortLabel`,
          ),
        },
        {
          label: t("ekyc.fields.documentNumber"),
          value: verifiedIdentity.identity_number || "-",
        },
        { label: t("ekyc.fields.fullName"), value: verifiedIdentity.full_name || "-" },
        {
          label: t("ekyc.fields.dateOfBirth"),
          value: verifiedIdentity.birth_date || "-",
        },
        { label: t("ekyc.fields.gender"), value: verifiedIdentity.gender || "-" },
        {
          label: t("ekyc.fields.nationality"),
          value: verifiedIdentity.nationality || "-",
        },
        {
          label: t("ekyc.fields.issuedDate"),
          value: verifiedIdentity.issued_date || "-",
        },
        {
          label: t("ekyc.fields.expiryDate"),
          value: verifiedIdentity.expired_date || "-",
        },
      ]
    : [];
  const reviewChecklist = [
    t("ekyc.review.frontImage"),
    t("ekyc.review.backImage"),
    t("ekyc.review.faceVoiceVideo"),
  ];

  return (
    <ProtectedRoute>
      <main className="min-h-screen overflow-hidden bg-[#030712] text-white">
        <div className="vintrade-bg" />
        <AppHeader focusMode />
        <section className="relative z-10 mx-auto max-w-[1120px] px-4 py-6 sm:px-6 lg:px-8">
          <div className="mb-6 grid gap-5 lg:grid-cols-[minmax(0,1fr)_320px] lg:items-start">
            <div className="glass-panel p-5 sm:p-6">
              <span className="micro-badge">
                <span className="status-dot cyan" />
                {t("ekyc.hero.badge")}
              </span>
              <h1 className="mt-4 text-3xl font-black leading-[1.2] tracking-normal sm:text-4xl">
                {t("ekyc.hero.title")}
              </h1>
              <p className="mt-2 max-w-2xl text-sm text-slate-300">
                {t("ekyc.hero.description")}
              </p>
            </div>
            <div className="glass-panel min-w-64 p-4 sm:p-5">
              <div className="flex items-center justify-between text-sm text-slate-300">
                <span>{t("ekyc.hero.progress")}</span>
                <strong className="text-cyan-200">{progress}%</strong>
              </div>
              <div className="mt-3 h-3 overflow-hidden rounded-full bg-slate-900">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-emerald-400 via-cyan-400 to-violet-500 transition-all duration-500"
                  style={{ width: `${progress}%` }}
                />
              </div>
              <div className="mt-4 grid gap-3">
                <div className="rounded-xl border border-white/10 bg-slate-950/35 px-4 py-3">
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                    {t("ekyc.hero.currentPhaseLabel")}
                  </p>
                  <p className="mt-1 text-sm font-bold text-white">
                    {t(`ekyc.stepper.step${currentStep}`)} •{" "}
                    {t(
                      currentStep === 1
                        ? "ekyc.stepper.documentVerification"
                        : currentStep === 2
                          ? "ekyc.stepper.faceVoiceChallenge"
                          : "ekyc.stepper.reviewProcessing",
                    )}
                  </p>
                </div>
              </div>
            </div>
          </div>

          <EkycStepper
            currentStep={currentStep}
            documentCompleted={hasDocumentFiles}
            videoCompleted={Boolean(videoFile) || hasSubmittedRequest}
            processingCompleted={processingCompleted || isAlreadyVerified}
            canAccessStep={canAccessStep}
            onStepSelect={handleStepSelect}
          />

          {errorMessage ? (
            <div className="mt-5 rounded-lg border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm font-semibold text-rose-100">
              {errorMessage}
            </div>
          ) : null}
          {successMessage && !processingCompleted ? (
            <div className="mt-5 rounded-lg border border-emerald-400/30 bg-emerald-500/10 px-4 py-3 text-sm font-semibold text-emerald-100">
              {successMessage}
            </div>
          ) : null}

          {isLoadingStatus ? (
            <section className="glass-panel mt-6 p-6">
              <div className="flex items-center gap-3 text-sm font-semibold text-slate-200">
                <Loader2 className="animate-spin text-cyan-200" size={20} />
                {t("ekyc.loadingStatus")}
              </div>
            </section>
          ) : isAlreadyVerified ? (
            <section className="glass-panel mt-6 p-6">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <span className="status-pill success">
                    {t("ekyc.verified.badge")}
                  </span>
                  <h2 className="mt-4 text-2xl font-black">
                    {t("ekyc.verified.title")}
                  </h2>
                  <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-300">
                    {t("ekyc.verified.description")}
                    {verifiedAt
                      ? ` ${t("ekyc.verified.verifiedAt", {
                          date: new Date(verifiedAt).toLocaleString(dateLocale),
                        })}`
                      : ""}
                  </p>
                </div>
                <div className="result-score">
                  <CheckCircle2 size={34} />
                </div>
              </div>
              {verifiedIdentityDetails.length > 0 ? (
                <dl className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  {verifiedIdentityDetails.map((item) => (
                    <div
                      className="rounded-lg border border-white/10 bg-slate-950/40 px-4 py-3"
                      key={item.label}
                    >
                      <dt className="text-xs font-semibold uppercase tracking-normal text-slate-400">
                        {item.label}
                      </dt>
                      <dd className="mt-1 break-words text-sm font-bold text-slate-100">
                        {item.value}
                      </dd>
                    </div>
                  ))}
                </dl>
              ) : null}
              {verifiedIdentity?.verified_at ? (
                <p className="mt-4 text-xs font-semibold text-slate-400">
                  {t("ekyc.verified.updatedOn", {
                    date: formatDisplayDate(
                      verifiedIdentity.verified_at,
                      dateLocale,
                    ),
                  })}
                </p>
              ) : null}
            </section>
          ) : (
            <div className="mt-6 grid gap-5">
              {currentStep === 1 ? (
                <section className="grid gap-5" ref={activeStepRef}>
                  <div className="glass-panel p-5">
                    <div className="mb-5">
                      <label className="form-label" htmlFor="ekyc-document-type">
                        {t("ekyc.fields.documentType")}
                      </label>
                      <div className="input-shell mt-2 min-h-12">
                        <select
                          className="w-full border-0 bg-transparent text-white outline-0"
                          disabled={isSubmitting}
                          id="ekyc-document-type"
                          onChange={(event) =>
                            handleDocumentTypeChange(
                              event.target.value as EkycDocumentType,
                            )
                          }
                          value={documentType}
                        >
                          {documentTypeOptions.map((option) => {
                            const optionKey = `ekyc.documentTypes.${option.value}`;
                            return (
                              <option
                                className="bg-slate-950 text-white"
                                key={option.value}
                                value={option.value}
                              >
                                {t(`${optionKey}.label`)}
                              </option>
                            );
                          })}
                        </select>
                      </div>
                    </div>
                    <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
                      <div>
                        <span className="status-pill">
                          {t("ekyc.sections.documentUpload")}
                        </span>
                        <h2 className="mt-4 text-2xl font-black">
                          {t("ekyc.sections.documentUploadTitle")}
                        </h2>
                        <p className="mt-2 text-sm leading-6 text-slate-300">
                          {selectedDocument.stepDescription}
                        </p>
                      </div>
                      <div className="result-score">
                        <Upload size={34} />
                      </div>
                    </div>
                  </div>

                  <div className="grid gap-5 md:grid-cols-2">
                    <UploadCard
                      accent="cyan"
                      disabled={isSubmitting}
                      file={frontFile}
                      key={`${documentType}-front`}
                      maxFileSizeMb={5}
                      onFileChange={(file) => {
                        setFrontFile(file);
                        if (!file && !hasSubmittedRequest) {
                          setVideoFile(null);
                          setCurrentStep(1);
                        }
                        setErrorMessage("");
                        setSuccessMessage("");
                      }}
                      title={selectedDocument.frontTitle}
                    />
                    <UploadCard
                      accent="violet"
                      disabled={isSubmitting}
                      file={backFile}
                      key={`${documentType}-back`}
                      maxFileSizeMb={5}
                      onFileChange={(file) => {
                        setBackFile(file);
                        if (!file && !hasSubmittedRequest) {
                          setVideoFile(null);
                          setCurrentStep(1);
                        }
                        setErrorMessage("");
                        setSuccessMessage("");
                      }}
                      title={selectedDocument.backTitle}
                    />
                  </div>
                  <div className="flex justify-end">
                    <button
                      className="primary-button justify-center disabled:cursor-not-allowed disabled:opacity-50"
                      disabled={!hasDocumentFiles || isSubmitting}
                      onClick={handleNextFromDocuments}
                      type="button"
                    >
                      {t("ekyc.actions.continueToFaceVoice")}
                      <ArrowRight size={16} />
                    </button>
                  </div>
                </section>
              ) : null}

              {currentStep === 2 ? (
                <section className="glass-panel p-5" ref={activeStepRef}>
                  <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
                    <div>
                      <span className="status-pill">
                        {t("ekyc.sections.videoRequired")}
                      </span>
                      <h2 className="mt-4 text-2xl font-black">
                        {t("ekyc.sections.videoTitle")}
                      </h2>
                      <p className="mt-2 max-w-xl text-sm leading-5 text-slate-300">
                        {t("ekyc.sections.videoDescription")}
                      </p>
                    </div>
                    <div className="result-score">
                      <ScanFace size={34} />
                    </div>
                  </div>

                  <div className="mt-5">
                    <FaceCaptureRecorder
                      backDisabled={isSubmitting}
                      capturedFile={videoFile}
                      challengeLoading={false}
                      disabled={isSubmitting}
                      expiresAt={null}
                      key={voiceChallenge?.displayText ?? "local-voice-challenge"}
                      onCapture={(file) => {
                        void handleVoiceCapture(file);
                      }}
                      onBackToDocuments={() => handleStepSelect(1)}
                      onError={(message) => setErrorMessage(message)}
                      onRetry={handleVoiceRetry}
                      onSessionExpired={handleVoiceSessionExpired}
                      voiceChallengeDigits={voiceChallenge?.displayDigits ?? []}
                      voiceChallengeHint=""
                      voiceChallengeText={voiceChallenge?.displayText ?? ""}
                    />
                  </div>

                  <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:items-center">
                    {isSubmitting ? (
                      <div className="flex items-center gap-2 text-sm font-semibold text-cyan-100">
                        <Loader2 className="animate-spin" size={16} />
                        {t("ekyc.messages.submittingForProcessing")}
                      </div>
                    ) : null}
                  </div>
                </section>
              ) : null}

              {currentStep === 3 && (requestState || videoFile) ? (
                <section className="glass-panel p-5" ref={activeStepRef}>
                  {requestState ? (
                    <>
                      {requestState.status === "SUCCESS" ? (
                        <div className="flex min-h-[220px] flex-col">
                          <div>
                            <span className="status-pill success">
                              {t("ekyc.status.success")}
                            </span>
                            <h2 className="mt-4 text-3xl font-black">
                              {t("ekyc.sections.successTitle")}
                            </h2>
                            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-300">
                              {t("ekyc.sections.successDescription")}
                            </p>
                          </div>
                          <div className="mt-auto flex justify-end pt-8">
                            <div
                              className="result-score"
                              style={{ height: 112, width: 112 }}
                            >
                              <CheckCircle2 size={72} />
                            </div>
                          </div>
                        </div>
                      ) : (
                        <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
                          <div>
                            <span
                              className={`status-pill ${
                                getProcessingTone(requestState.status) === "danger"
                                  ? "danger"
                                  : getProcessingTone(requestState.status) === "success"
                                    ? "success"
                                    : ""
                              }`}
                            >
                              {requestState.status}
                            </span>
                            <h2 className="mt-4 text-2xl font-black">
                              {isTerminal(requestState.status)
                                ? t("ekyc.sections.verificationResult")
                                : t("ekyc.sections.processingTitle")}
                            </h2>
                            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-300">
                              {resultMessage(requestState, t)}
                            </p>
                          </div>
                          <div className="result-score">
                            {requestState.status === "FAILED" ? (
                              <ShieldAlert size={34} />
                            ) : isTerminal(requestState.status) ? (
                              <FileCheck2 size={34} />
                            ) : (
                              <ScanFace size={34} />
                            )}
                          </div>
                        </div>
                      )}

                      {requestState.status === "FAILED" ? (
                        <button
                          className="secondary-button mt-5 justify-center"
                          onClick={resetFlow}
                          type="button"
                        >
                          <RefreshCcw size={16} />
                          {t("ekyc.actions.startNewVerification")}
                        </button>
                      ) : null}
                    </>
                  ) : (
                    <>
                      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_300px]">
                        <div className="rounded-2xl border border-white/10 bg-slate-950/30 p-5">
                          <span className="status-pill">
                            {t("ekyc.sections.readyToSubmit")}
                          </span>
                          <h2 className="mt-4 text-2xl font-black">
                            {t("ekyc.sections.reviewTitle")}
                          </h2>
                          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-300">
                            {t("ekyc.sections.reviewDescription")}
                          </p>
                          <div className="mt-5 grid gap-3">
                            {reviewChecklist.map((item) => (
                              <div
                                className="flex items-center gap-3 rounded-lg border border-white/8 bg-white/[0.03] px-4 py-2.5"
                                key={item}
                              >
                                <CheckCircle2
                                  className="shrink-0 text-emerald-300"
                                  size={18}
                                />
                                <span className="text-sm font-semibold text-slate-100">
                                  {item}
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                        <div className="rounded-2xl border border-cyan-300/16 bg-slate-950/40 p-5">
                          <div className="mt-5 grid gap-3">
                            <button
                              className="secondary-button justify-center disabled:cursor-not-allowed disabled:opacity-50"
                              disabled={isSubmitting}
                              onClick={() => handleStepSelect(2)}
                              type="button"
                            >
                              <ArrowLeft size={16} />
                              {t("ekyc.actions.backToVideo")}
                            </button>
                            <button
                              className="primary-button justify-center disabled:cursor-not-allowed disabled:opacity-50"
                              disabled={
                                !frontFile ||
                                !backFile ||
                                !videoFile ||
                                !voiceChallenge?.displayText ||
                                isSubmitting
                              }
                              onClick={() => handleSubmitEkycSession()}
                              type="button"
                            >
                              {isSubmitting ? (
                                <Loader2 className="animate-spin" size={16} />
                              ) : (
                                <Send size={16} />
                              )}
                              {isSubmitting
                                ? t("ekyc.actions.submittingApplication")
                                : t("ekyc.actions.submitApplication")}
                            </button>
                          </div>
                        </div>
                      </div>
                    </>
                  )}
                </section>
              ) : null}
            </div>
          )}
        </section>
      </main>
    </ProtectedRoute>
  );
}
