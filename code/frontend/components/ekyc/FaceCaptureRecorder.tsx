"use client";

import { useLanguage } from "@/contexts/LanguageContext";
import {
  ArrowLeft,
  Camera,
  Check,
  Loader2,
  Mic,
  RefreshCcw,
  RotateCcw,
  Video,
  VideoOff,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

const MODEL_URL =
  "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task";
const WASM_URL = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@latest/wasm";
const FACE_STABLE_MS = 3200;
const MIN_VOICE_RECORDING_MS = 3200;
const MAX_RECORDING_MS = 35000;
const CAPTURE_SESSION_TIMEOUT_MS = 60 * 1000;
const MIN_FACE_COVERAGE = 0.075;
const MIN_FACE_BRIGHTNESS = 58;
const MAX_FACE_BRIGHTNESS = 218;
const MIN_FACE_SHARPNESS = 5.5;
const FRAME_QUALITY_INTERVAL_MS = 180;
const MIN_SPEECH_RMS_THRESHOLD = 0.035;
const SPEECH_NOISE_MULTIPLIER = 2.4;
const MIN_SPEECH_SAMPLES = 14;
const MIN_SPEECH_SPAN_MS = 900;
const SPEECH_END_SILENCE_MS = 700;
const MIN_MOUTH_OPEN_RATIO = 0.16;
const MIN_MOUTH_OPEN_SAMPLES = 4;
const MIN_MOUTH_OPEN_SPAN_MS = 450;
const CHALLENGE_REQUEST_RETRY_MS = 2000;

type Landmark = {
  x: number;
  y: number;
};

type CapturePhase = "idle" | "aligning" | "recording" | "captured";

type FaceBounds = {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
};

type FaceState = {
  found: boolean;
  ready: boolean;
  instruction: string;
  detail: string;
  phase: CapturePhase;
  metrics?: {
    bounds: FaceBounds;
    faceCoverage: number;
    brightness: number | null;
    sharpness: number | null;
    mouthOpenRatio: number | null;
    mouthOpen: boolean;
  } | null;
};

type FrameQuality = {
  brightness: number;
  sharpness: number;
};

type FaceCaptureRecorderProps = {
  capturedFile: File | null;
  backDisabled?: boolean;
  disabled?: boolean;
  challengeLoading?: boolean;
  voiceChallengeText?: string;
  voiceChallengeDigits?: string[];
  voiceChallengeHint?: string;
  remainingAttempts?: number;
  expiresAt?: string | null;
  onCapture: (file: File | null) => void;
  onBackToDocuments?: () => void;
  onError?: (message: string) => void;
  onRequestVoiceChallenge?: () => Promise<boolean>;
  onRetry?: () => void;
  onSessionExpired?: () => void;
};

type FaceLandmarkerInstance = {
  detectForVideo: (
    video: HTMLVideoElement,
    timestamp: number,
  ) => { faceLandmarks?: Landmark[][] };
  close: () => void;
};

const defaultFaceState: FaceState = {
  found: false,
  ready: false,
  instruction: "Start camera to detect face",
  detail: "Keep your face inside the guide.",
  phase: "idle",
  metrics: null,
};

const expiredFaceState: FaceState = {
  ...defaultFaceState,
  instruction: "Session expired",
  detail: "The camera was closed. Press Start camera to try again.",
};

function getSupportedMimeType() {
  if (typeof MediaRecorder === "undefined") {
    return "";
  }

  const mimeTypes = [
    "video/mp4;codecs=avc1.42E01E",
    "video/mp4;codecs=h264",
    "video/mp4",
  ];

  return mimeTypes.find((type) => MediaRecorder.isTypeSupported(type)) ?? "";
}

function getExtensionFromMimeType(type: string) {
  return type.includes("mp4") ? "mp4" : "webm";
}

function getBounds(landmarks: Landmark[]) {
  return landmarks.reduce(
    (bounds, point) => ({
      minX: Math.min(bounds.minX, point.x),
      maxX: Math.max(bounds.maxX, point.x),
      minY: Math.min(bounds.minY, point.y),
      maxY: Math.max(bounds.maxY, point.y),
    }),
    { minX: 1, maxX: 0, minY: 1, maxY: 0 },
  );
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function distance(a: Landmark | undefined, b: Landmark | undefined) {
  if (!a || !b) {
    return 0;
  }

  return Math.hypot(a.x - b.x, a.y - b.y);
}

function analyzeMouthOpen(landmarks: Landmark[]) {
  const upperInnerLip = landmarks[13];
  const lowerInnerLip = landmarks[14];
  const leftCorner = landmarks[61];
  const rightCorner = landmarks[291];
  const mouthWidth = distance(leftCorner, rightCorner);

  if (!mouthWidth) {
    return {
      mouthOpenRatio: null,
      mouthOpen: false,
    };
  }

  const mouthOpenRatio = distance(upperInnerLip, lowerInnerLip) / mouthWidth;
  return {
    mouthOpenRatio,
    mouthOpen: mouthOpenRatio >= MIN_MOUTH_OPEN_RATIO,
  };
}

function analyzeFrameQuality(
  video: HTMLVideoElement,
  bounds: FaceBounds,
  canvas: HTMLCanvasElement,
): FrameQuality | null {
  if (!video.videoWidth || !video.videoHeight) {
    return null;
  }

  const sampleSize = 72;
  const paddingX = (bounds.maxX - bounds.minX) * 0.22;
  const paddingY = (bounds.maxY - bounds.minY) * 0.18;
  const minX = clamp(bounds.minX - paddingX, 0, 1);
  const maxX = clamp(bounds.maxX + paddingX, 0, 1);
  const minY = clamp(bounds.minY - paddingY, 0, 1);
  const maxY = clamp(bounds.maxY + paddingY, 0, 1);
  const sourceX = minX * video.videoWidth;
  const sourceY = minY * video.videoHeight;
  const sourceWidth = Math.max((maxX - minX) * video.videoWidth, 1);
  const sourceHeight = Math.max((maxY - minY) * video.videoHeight, 1);
  const ctx = canvas.getContext("2d", { willReadFrequently: true });

  if (!ctx) {
    return null;
  }

  canvas.width = sampleSize;
  canvas.height = sampleSize;
  ctx.drawImage(
    video,
    sourceX,
    sourceY,
    sourceWidth,
    sourceHeight,
    0,
    0,
    sampleSize,
    sampleSize,
  );

  const { data } = ctx.getImageData(0, 0, sampleSize, sampleSize);
  const gray = new Float32Array(sampleSize * sampleSize);
  let brightnessTotal = 0;

  for (let i = 0, j = 0; i < data.length; i += 4, j += 1) {
    const luminance = data[i] * 0.2126 + data[i + 1] * 0.7152 + data[i + 2] * 0.0722;
    gray[j] = luminance;
    brightnessTotal += luminance;
  }

  let edgeTotal = 0;
  let edgeSamples = 0;
  for (let y = 1; y < sampleSize - 1; y += 1) {
    for (let x = 1; x < sampleSize - 1; x += 1) {
      const index = y * sampleSize + x;
      const laplacian =
        gray[index - sampleSize] +
        gray[index - 1] +
        gray[index + 1] +
        gray[index + sampleSize] -
        gray[index] * 4;
      edgeTotal += Math.abs(laplacian);
      edgeSamples += 1;
    }
  }

  return {
    brightness: brightnessTotal / gray.length,
    sharpness: edgeSamples ? edgeTotal / edgeSamples : 0,
  };
}

function analyzeFace(
  landmarks: Landmark[] | undefined,
  phase: CapturePhase,
  voiceChallengeVisible: boolean,
  quality: FrameQuality | null,
): FaceState {
  if (!landmarks?.length) {
    return {
      ...defaultFaceState,
      instruction: "No face detected",
      detail: "Move into view and face the camera.",
      phase,
    };
  }

  const bounds = getBounds(landmarks);
  const width = bounds.maxX - bounds.minX;
  const height = bounds.maxY - bounds.minY;
  const centerX = bounds.minX + width / 2;
  const centerY = bounds.minY + height / 2;
  const faceCoverage = width * height;
  const mouth = analyzeMouthOpen(landmarks);

  const warnings = [];
  if (bounds.minX < 0.06) warnings.push("Move right");
  if (bounds.maxX > 0.94) warnings.push("Move left");
  if (bounds.minY < 0.08) warnings.push("Move down");
  if (bounds.maxY > 0.96) warnings.push("Move up");
  if (width < 0.22 || faceCoverage < MIN_FACE_COVERAGE) warnings.push("Move closer");
  if (width > 0.62 || height > 0.82) warnings.push("Move back");
  if (quality && quality.brightness < MIN_FACE_BRIGHTNESS) warnings.push("Add more light");
  if (quality && quality.brightness > MAX_FACE_BRIGHTNESS) warnings.push("Reduce glare");
  if (quality && quality.sharpness < MIN_FACE_SHARPNESS) warnings.push("Hold steady");

  const centered =
    centerX > 0.32 &&
    centerX < 0.68 &&
    centerY > 0.28 &&
    centerY < 0.72 &&
    width >= 0.22 &&
    faceCoverage >= MIN_FACE_COVERAGE &&
    width <= 0.62 &&
    bounds.minX >= 0.06 &&
    bounds.maxX <= 0.94 &&
    bounds.minY >= 0.08 &&
    bounds.maxY <= 0.96 &&
    (!quality ||
      (quality.brightness >= MIN_FACE_BRIGHTNESS &&
        quality.brightness <= MAX_FACE_BRIGHTNESS &&
        quality.sharpness >= MIN_FACE_SHARPNESS));

  const warning = warnings[0] ?? "";
  const ready = centered && !warning;

  return {
    found: true,
    ready,
    instruction:
      warning ||
      (phase === "recording" && voiceChallengeVisible
        ? "Read phrase aloud"
        : "Look at the camera"),
    detail: ready
      ? phase === "recording" && voiceChallengeVisible
        ? mouth.mouthOpen
          ? "Read each digit clearly until recording finishes."
          : "Read each digit clearly and naturally."
        : "Hold still while we prepare recording."
      : "Center your face before recording.",
    phase,
    metrics: {
      bounds,
      faceCoverage,
      brightness: quality?.brightness ?? null,
      sharpness: quality?.sharpness ?? null,
      mouthOpenRatio: mouth.mouthOpenRatio,
      mouthOpen: mouth.mouthOpen,
    },
  };
}

function drawFaceGuide(
  ctx: CanvasRenderingContext2D,
  rect: DOMRect,
  state: FaceState,
) {
  const guide = {
    x: rect.width * 0.23,
    y: rect.height * 0.12,
    width: rect.width * 0.54,
    height: rect.height * 0.58,
  };
  const isHardError =
    state.instruction === "Only one face please" ||
    state.instruction === "Face detector unavailable";
  const color = isHardError
    ? "rgba(251, 113, 133, 0.96)"
    : state.ready
      ? "rgba(110, 231, 183, 0.98)"
      : state.found
        ? "rgba(251, 191, 36, 0.96)"
        : "rgba(148, 163, 184, 0.8)";
  const glow = isHardError
    ? "rgba(251, 113, 133, 0.22)"
    : state.ready
      ? "rgba(16, 185, 129, 0.22)"
      : state.found
        ? "rgba(245, 158, 11, 0.22)"
        : "rgba(15, 23, 42, 0.42)";
  const centerX = guide.x + guide.width / 2;
  const centerY = guide.y + guide.height / 2;
  const cornerRadius = Math.min(guide.width, guide.height) * 0.12;
  const cornerLength = Math.min(guide.width, guide.height) * 0.18;

  const drawCornerFrame = (lineWidth: number, strokeStyle: string) => {
    ctx.strokeStyle = strokeStyle;
    ctx.lineWidth = lineWidth;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";

    ctx.beginPath();
    ctx.moveTo(guide.x, guide.y + cornerRadius + cornerLength);
    ctx.lineTo(guide.x, guide.y + cornerRadius);
    ctx.quadraticCurveTo(guide.x, guide.y, guide.x + cornerRadius, guide.y);
    ctx.lineTo(guide.x + cornerRadius + cornerLength, guide.y);

    ctx.moveTo(guide.x + guide.width - cornerRadius - cornerLength, guide.y);
    ctx.lineTo(guide.x + guide.width - cornerRadius, guide.y);
    ctx.quadraticCurveTo(
      guide.x + guide.width,
      guide.y,
      guide.x + guide.width,
      guide.y + cornerRadius,
    );
    ctx.lineTo(guide.x + guide.width, guide.y + cornerRadius + cornerLength);

    ctx.moveTo(guide.x, guide.y + guide.height - cornerRadius - cornerLength);
    ctx.lineTo(guide.x, guide.y + guide.height - cornerRadius);
    ctx.quadraticCurveTo(
      guide.x,
      guide.y + guide.height,
      guide.x + cornerRadius,
      guide.y + guide.height,
    );
    ctx.lineTo(
      guide.x + cornerRadius + cornerLength,
      guide.y + guide.height,
    );

    ctx.moveTo(
      guide.x + guide.width - cornerRadius - cornerLength,
      guide.y + guide.height,
    );
    ctx.lineTo(guide.x + guide.width - cornerRadius, guide.y + guide.height);
    ctx.quadraticCurveTo(
      guide.x + guide.width,
      guide.y + guide.height,
      guide.x + guide.width,
      guide.y + guide.height - cornerRadius,
    );
    ctx.lineTo(
      guide.x + guide.width,
      guide.y + guide.height - cornerRadius - cornerLength,
    );
    ctx.stroke();
  };

  ctx.save();
  ctx.beginPath();
  ctx.fillStyle = "rgba(2, 6, 23, 0.28)";
  ctx.ellipse(
    centerX,
    centerY,
    guide.width * 0.34,
    guide.height * 0.42,
    0,
    0,
    Math.PI * 2,
  );
  ctx.fill();

  drawCornerFrame(16, glow);
  drawCornerFrame(3.5, color);

  ctx.strokeStyle = "rgba(255, 255, 255, 0.12)";
  ctx.lineWidth = 1.2;
  ctx.beginPath();
  ctx.ellipse(
    centerX,
    centerY,
    guide.width * 0.28,
    guide.height * 0.34,
    0,
    0,
    Math.PI * 2,
  );
  ctx.stroke();
  ctx.restore();
}

export function FaceCaptureRecorder({
  capturedFile,
  backDisabled = false,
  challengeLoading = false,
  disabled = false,
  expiresAt = null,
  voiceChallengeText = "",
  voiceChallengeDigits = [],
  voiceChallengeHint = "",
  remainingAttempts,
  onCapture,
  onBackToDocuments,
  onError,
  onRequestVoiceChallenge,
  onRetry,
  onSessionExpired,
}: FaceCaptureRecorderProps) {
  const { t } = useLanguage();
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const qualityCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const capturePanelRef = useRef<HTMLDivElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const animationRef = useRef<number>(0);
  const faceLandmarkerRef = useRef<FaceLandmarkerInstance | null>(null);
  const faceStateRef = useRef<FaceState>(defaultFaceState);
  const captureStartedAtRef = useRef(0);
  const validFaceStartedAtRef = useRef(0);
  const recordingStartedAtRef = useRef(0);
  const voiceChallengeRevealedAtRef = useRef(0);
  const lastQualityAnalyzedAtRef = useRef(0);
  const latestFrameQualityRef = useRef<FrameQuality | null>(null);
  const savingRef = useRef(false);
  const completedSessionRef = useRef(false);
  const ignoreNextSaveRef = useRef(false);
  const audioContextRef = useRef<AudioContext | null>(null);
  const audioAnalyserRef = useRef<AnalyserNode | null>(null);
  const audioDataRef = useRef<Uint8Array<ArrayBuffer> | null>(null);
  const speechSamplesRef = useRef(0);
  const speechStartedAtRef = useRef(0);
  const lastSpeechAtRef = useRef(0);
  const mouthOpenSamplesRef = useRef(0);
  const mouthOpenedAtRef = useRef(0);
  const noiseFloorRef = useRef(0.012);
  const lastFaceUiUpdateRef = useRef(0);
  const sessionTimeoutRef = useRef<number | null>(null);
  const maxRecordingTimeoutRef = useRef<number | null>(null);
  const onErrorRef = useRef(onError);
  const onCaptureRef = useRef(onCapture);
  const onRequestVoiceChallengeRef = useRef(onRequestVoiceChallenge);
  const onRetryRef = useRef(onRetry);
  const onSessionExpiredRef = useRef(onSessionExpired);
  const requestChallengeInFlightRef = useRef(false);
  const lastChallengeRequestAtRef = useRef(0);

  const [cameraReady, setCameraReady] = useState(false);
  const [, setRecording] = useState(false);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState("Camera idle");
  const [faceState, setFaceState] = useState(defaultFaceState);
  const [sessionExpired, setSessionExpired] = useState(false);
  const [remainingSeconds, setRemainingSeconds] = useState(60);
  const [showVoiceChallenge, setShowVoiceChallenge] = useState(false);
  const [readyHoldProgress, setReadyHoldProgress] = useState(0);

  const translateCaptureText = (value: string) => {
    const map: Record<string, string> = {
      "Camera idle": "ekyc.capture.cameraIdle",
      "Start camera to detect face": "ekyc.capture.startDetectFace",
      "Keep your face inside the guide.": "ekyc.capture.keepFaceInside",
      "Session expired": "ekyc.capture.sessionExpiredTitle",
      "The camera was closed. Press Start camera to try again.":
        "ekyc.capture.cameraClosedRetry",
      "No face detected": "ekyc.capture.noFaceDetected",
      "Move into view and face the camera.": "ekyc.capture.moveIntoView",
      "Read phrase aloud": "ekyc.capture.readPhraseAloud",
      "Look at the camera": "ekyc.capture.lookAtCamera",
      "Read each digit clearly until recording finishes.":
        "ekyc.capture.readDigitsClearly",
      "Read each digit clearly and naturally.":
        "ekyc.capture.readNaturally",
      "Hold still while we prepare recording.": "ekyc.capture.holdStill",
      "Center your face before recording.": "ekyc.capture.centerFace",
      "Only one face please": "ekyc.capture.onlyOneFace",
      "Move other faces out of the frame before recording.":
        "ekyc.capture.removeOtherFaces",
      "Move right": "ekyc.capture.moveRight",
      "Move left": "ekyc.capture.moveLeft",
      "Move down": "ekyc.capture.moveDown",
      "Move up": "ekyc.capture.moveUp",
      "Move closer": "ekyc.capture.moveCloser",
      "Move back": "ekyc.capture.moveBack",
      "Add more light": "ekyc.capture.addLight",
      "Reduce glare": "ekyc.capture.reduceGlare",
      "Hold steady": "ekyc.capture.holdSteady",
      "Loading face detector": "ekyc.capture.loadingDetector",
      "Face detector ready": "ekyc.capture.detectorReady",
      "Face detector unavailable": "ekyc.capture.detectorUnavailable",
      "Center your face in the guide": "ekyc.capture.centerInGuide",
      "Recording stopped": "ekyc.capture.recordingStopped",
      "Saving recording": "ekyc.capture.savingRecording",
      "Recording failed": "ekyc.capture.recordingFailed",
      "Face and voice video ready": "ekyc.capture.videoReady",
      "Face and voice captured": "ekyc.capture.captured",
      "Press Submit for processing or Retry to start again.":
        "ekyc.capture.submitOrRetry",
      "Capture stopped": "ekyc.capture.recordingStopped",
      "Please retry the face capture.": "ekyc.capture.retryFaceCapture",
      "We could not clearly confirm the spoken challenge. Please read the digits again while facing the camera.":
        "ekyc.capture.mouthNotVisible",
    };

    return map[value] ? t(map[value]) : value;
  };

  const captureMetaText = () => {
    if (capturedFile) {
      return t("ekyc.capture.captureComplete");
    }
    if (sessionExpired) {
      return t("ekyc.capture.sessionTimedOut");
    }
    if (cameraReady) {
      const base = t("ekyc.capture.timeLeft", { seconds: remainingSeconds });
      return typeof remainingAttempts === "number"
        ? `${base} | ${t("ekyc.capture.attemptsLeft", {
            attempts: remainingAttempts,
          })}`
        : base;
    }
    return t("ekyc.capture.noCapture");
  };

  const displayDigits =
    voiceChallengeDigits.length > 0
      ? voiceChallengeDigits
      : voiceChallengeText.trim()
        ? voiceChallengeText.trim().split(/\s+/)
        : [];
  const challengeReady = displayDigits.length > 0;
  const voiceSessionExpiresAtMs = expiresAt ? Date.parse(expiresAt) : Number.NaN;
  const captureChecks = [
    {
      label: t("ekyc.capture.centered"),
      active: Boolean(faceState.metrics?.faceCoverage) && faceState.found,
    },
    {
      label: t("ekyc.capture.goodLight"),
      active:
        faceState.metrics?.brightness !== null &&
        faceState.metrics?.brightness !== undefined &&
        faceState.metrics.brightness >= MIN_FACE_BRIGHTNESS &&
        faceState.metrics.brightness <= MAX_FACE_BRIGHTNESS,
    },
    {
      label: t("ekyc.capture.sharp"),
      active:
        faceState.metrics?.sharpness !== null &&
        faceState.metrics?.sharpness !== undefined &&
        faceState.metrics.sharpness >= MIN_FACE_SHARPNESS,
    },
    {
      label: t("ekyc.capture.oneFace"),
      active: faceState.instruction !== "Only one face please",
    },
  ];

  useEffect(() => {
    onErrorRef.current = onError;
  }, [onError]);

  useEffect(() => {
    onCaptureRef.current = onCapture;
  }, [onCapture]);

  useEffect(() => {
    onRequestVoiceChallengeRef.current = onRequestVoiceChallenge;
  }, [onRequestVoiceChallenge]);

  useEffect(() => {
    onRetryRef.current = onRetry;
  }, [onRetry]);

  useEffect(() => {
    onSessionExpiredRef.current = onSessionExpired;
  }, [onSessionExpired]);

  useEffect(() => {
    return () => {
      stopCameraTracks();
      clearCaptureSessionTimeout();
      clearMaxRecordingTimeout();
      cancelAnimationFrame(animationRef.current);
      faceLandmarkerRef.current?.close();
      if (recorderRef.current && recorderRef.current.state !== "inactive") {
        ignoreNextSaveRef.current = true;
        recorderRef.current.stop();
      }
    };
    // Cleanup should run only when this recorder instance unmounts.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!cameraReady) {
      return;
    }

    let disposed = false;

    async function loadFaceLandmarker() {
      if (faceLandmarkerRef.current) {
        return faceLandmarkerRef.current;
      }

      setStatus("Loading face detector");
      const { FaceLandmarker, FilesetResolver } = await import(
        "@mediapipe/tasks-vision"
      );
      const vision = await FilesetResolver.forVisionTasks(WASM_URL);
      const options = {
        baseOptions: {
          modelAssetPath: MODEL_URL,
          delegate: "GPU",
        },
        runningMode: "VIDEO",
        numFaces: 2,
        minFaceDetectionConfidence: 0.55,
        minFacePresenceConfidence: 0.55,
        minTrackingConfidence: 0.55,
      } as const;

      try {
        faceLandmarkerRef.current = await FaceLandmarker.createFromOptions(
          vision,
          options,
        );
      } catch {
        faceLandmarkerRef.current = await FaceLandmarker.createFromOptions(
          vision,
          {
            ...options,
            baseOptions: {
              modelAssetPath: MODEL_URL,
              delegate: "CPU",
            },
          },
        );
      }

      setStatus("Face detector ready");
      return faceLandmarkerRef.current;
    }

    const draw = async () => {
      const canvas = canvasRef.current;
      const video = videoRef.current;
      const ctx = canvas?.getContext("2d");

      if (!canvas || !ctx || !video) {
        animationRef.current = requestAnimationFrame(draw);
        return;
      }

      const rect = canvas.getBoundingClientRect();
      const scale = window.devicePixelRatio || 1;
      canvas.width = Math.floor(rect.width * scale);
      canvas.height = Math.floor(rect.height * scale);
      ctx.setTransform(scale, 0, 0, scale, 0, 0);
      ctx.clearRect(0, 0, rect.width, rect.height);
      drawFaceGuide(ctx, rect, faceStateRef.current);

      try {
        const landmarker = await loadFaceLandmarker();
        if (!disposed && video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) {
          const now = performance.now();
          const results = landmarker.detectForVideo(video, now);
          const faces = results.faceLandmarks ?? [];
          const face = faces[0];
          const phase: CapturePhase = recordingStartedAtRef.current
            ? "recording"
            : "aligning";
          const faceBounds = face?.length ? getBounds(face) : null;
          if (!qualityCanvasRef.current) {
            qualityCanvasRef.current = document.createElement("canvas");
          }
          let frameQuality = latestFrameQualityRef.current;
          if (faceBounds && face) {
            if (now - lastQualityAnalyzedAtRef.current >= FRAME_QUALITY_INTERVAL_MS) {
              lastQualityAnalyzedAtRef.current = now;
              frameQuality = analyzeFrameQuality(
                video,
                faceBounds,
                qualityCanvasRef.current,
              );
              latestFrameQualityRef.current = frameQuality;
            }
          } else {
            frameQuality = null;
            latestFrameQualityRef.current = null;
          }
          const nextState =
            faces.length > 1
              ? {
                  ...defaultFaceState,
                  found: true,
                  instruction: "Only one face please",
                  detail: "Move other faces out of the frame before recording.",
                  phase,
                }
              : analyzeFace(face, phase, showVoiceChallenge, frameQuality);

          handleCaptureProgress(nextState);
          faceStateRef.current = nextState;

          if (face?.length && nextState.metrics) {
            const { bounds } = nextState.metrics;
            const x = (1 - bounds.maxX) * rect.width;
            const y = bounds.minY * rect.height;
            const width = (bounds.maxX - bounds.minX) * rect.width;
            const height = (bounds.maxY - bounds.minY) * rect.height;
            const centerX = x + width / 2;
            const centerY = y + height / 2;
            const isHardError = nextState.instruction === "Only one face please";
            const outlineColor = isHardError
              ? "#fb7185"
              : nextState.ready
                ? "#6ee7b7"
                : "#fbbf24";

            ctx.save();
            ctx.strokeStyle = outlineColor;
            ctx.lineWidth = 3;
            ctx.setLineDash(nextState.ready ? [] : [8, 6]);
            ctx.beginPath();
            ctx.ellipse(
              centerX,
              centerY,
              Math.max(width * 0.34, 22),
              Math.max(height * 0.42, 28),
              0,
              0,
              Math.PI * 2,
            );
            ctx.stroke();

            ctx.setLineDash([]);
            ctx.strokeStyle = "rgba(255,255,255,0.16)";
            ctx.lineWidth = 1.2;
            ctx.beginPath();
            ctx.ellipse(
              centerX,
              centerY,
              Math.max(width * 0.4, 28),
              Math.max(height * 0.48, 36),
              0,
              0,
              Math.PI * 2,
            );
            ctx.stroke();
            ctx.restore();
          }

          if (performance.now() - lastFaceUiUpdateRef.current > 120) {
            lastFaceUiUpdateRef.current = performance.now();
            setFaceState(nextState);
          }
        }
      } catch (error) {
        const message =
          error instanceof Error ? error.message : "Face detector unavailable";
        const nextState = {
          ...defaultFaceState,
          instruction: "Face detector unavailable",
          detail: message,
        };
        faceStateRef.current = nextState;
        setFaceState(nextState);
        onErrorRef.current?.(message);
      }

      animationRef.current = requestAnimationFrame(draw);
    };

    cancelAnimationFrame(animationRef.current);
    draw();

    return () => {
      disposed = true;
      cancelAnimationFrame(animationRef.current);
    };
    // The draw loop intentionally reads mutable refs so it can run continuously
    // without restarting the camera detector on each UI state update.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cameraReady, showVoiceChallenge]);

  useEffect(() => {
    if (!cameraReady) {
      return;
    }

    function updateRemainingTime() {
      const elapsedMs = captureStartedAtRef.current
        ? performance.now() - captureStartedAtRef.current
        : 0;
      const captureRemainingMs = CAPTURE_SESSION_TIMEOUT_MS - elapsedMs;
      const sessionRemainingMs = Number.isFinite(voiceSessionExpiresAtMs)
        ? voiceSessionExpiresAtMs - Date.now()
        : captureRemainingMs;
      const nextSeconds = Math.max(
        0,
        Math.ceil(Math.min(captureRemainingMs, sessionRemainingMs) / 1000),
      );
      setRemainingSeconds(nextSeconds);
      if (nextSeconds <= 0) {
        expireCaptureSession();
      }
    }

    updateRemainingTime();
    const intervalId = window.setInterval(updateRemainingTime, 500);
    return () => window.clearInterval(intervalId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cameraReady]);

  function stopCameraTracks() {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    cleanupAudioAnalysis();
  }

  function cleanupAudioAnalysis() {
    audioAnalyserRef.current?.disconnect();
    audioAnalyserRef.current = null;
    audioDataRef.current = null;
    const audioContext = audioContextRef.current;
    audioContextRef.current = null;
    if (audioContext && audioContext.state !== "closed") {
      void audioContext.close().catch(() => undefined);
    }
  }

  function setupAudioAnalysis(stream: MediaStream) {
    cleanupAudioAnalysis();
    const AudioContextConstructor =
      window.AudioContext ||
      (window as typeof window & { webkitAudioContext?: typeof AudioContext })
        .webkitAudioContext;
    if (!AudioContextConstructor) {
      return;
    }

    const audioContext = new AudioContextConstructor();
    const analyser = audioContext.createAnalyser();
    analyser.fftSize = 1024;
    analyser.smoothingTimeConstant = 0.25;
    audioContext.createMediaStreamSource(stream).connect(analyser);
    audioContextRef.current = audioContext;
    audioAnalyserRef.current = analyser;
    audioDataRef.current = new Uint8Array(analyser.fftSize);
  }

  function readMicRms() {
    const analyser = audioAnalyserRef.current;
    const data = audioDataRef.current;
    if (!analyser || !data) {
      return null;
    }

    analyser.getByteTimeDomainData(data);
    let sumSquares = 0;
    for (const value of data) {
      const centered = (value - 128) / 128;
      sumSquares += centered * centered;
    }
    return Math.sqrt(sumSquares / data.length);
  }

  function sampleAmbientNoise() {
    const rms = readMicRms();
    if (rms === null) {
      return;
    }
    noiseFloorRef.current = noiseFloorRef.current * 0.92 + rms * 0.08;
  }

  function recordSpeechSample(now: number) {
    const rms = readMicRms();
    if (rms === null) {
      return;
    }

    const speechThreshold = Math.max(
      MIN_SPEECH_RMS_THRESHOLD,
      noiseFloorRef.current * SPEECH_NOISE_MULTIPLIER,
    );
    if (rms >= speechThreshold) {
      if (!speechStartedAtRef.current) {
        speechStartedAtRef.current = now;
      }
      lastSpeechAtRef.current = now;
      speechSamplesRef.current += 1;
    }
  }

  function hasDetectedSpeech(now: number) {
    return (
      speechSamplesRef.current >= MIN_SPEECH_SAMPLES &&
      speechStartedAtRef.current > 0 &&
      now - speechStartedAtRef.current >= MIN_SPEECH_SPAN_MS
    );
  }

  function recordMouthOpenSample(now: number, mouthOpen: boolean) {
    if (!mouthOpen) {
      return;
    }

    if (!mouthOpenedAtRef.current) {
      mouthOpenedAtRef.current = now;
    }
    mouthOpenSamplesRef.current += 1;
  }

  function hasDetectedMouthOpen(now: number) {
    return (
      mouthOpenSamplesRef.current >= MIN_MOUTH_OPEN_SAMPLES &&
      mouthOpenedAtRef.current > 0 &&
      now - mouthOpenedAtRef.current >= MIN_MOUTH_OPEN_SPAN_MS
    );
  }

  function clearCaptureSessionTimeout() {
    if (sessionTimeoutRef.current) {
      window.clearTimeout(sessionTimeoutRef.current);
      sessionTimeoutRef.current = null;
    }
  }

  function clearMaxRecordingTimeout() {
    if (maxRecordingTimeoutRef.current) {
      window.clearTimeout(maxRecordingTimeoutRef.current);
      maxRecordingTimeoutRef.current = null;
    }
  }

  function startCaptureSessionTimeout() {
    clearCaptureSessionTimeout();
    const sessionRemainingMs = Number.isFinite(voiceSessionExpiresAtMs)
      ? voiceSessionExpiresAtMs - Date.now()
      : CAPTURE_SESSION_TIMEOUT_MS;
    sessionTimeoutRef.current = window.setTimeout(() => {
      expireCaptureSession();
    }, Math.max(0, Math.min(CAPTURE_SESSION_TIMEOUT_MS, sessionRemainingMs)));
  }

  function expireCaptureSession() {
    ignoreNextSaveRef.current = true;
    if (recorderRef.current && recorderRef.current.state !== "inactive") {
      recorderRef.current.stop();
    }
    recorderRef.current = null;
    onCaptureRef.current(null);
    onSessionExpiredRef.current?.();
    setSessionExpired(true);
    closeCamera(expiredFaceState);
    setStatus("Session expired");
    onErrorRef.current?.(
      "Face capture session timed out. Please press Retry, then start the camera again.",
    );
  }

  async function startCamera() {
    if (disabled) {
      return;
    }
    if (Number.isFinite(voiceSessionExpiresAtMs) && voiceSessionExpiresAtMs <= Date.now()) {
      onSessionExpiredRef.current?.();
      setSessionExpired(true);
      setStatus("Session expired");
      onErrorRef.current?.("Voice challenge expired. Please wait for a new code and try again.");
      return;
    }

    try {
      setSessionExpired(false);
      resetRecordingState();
      onCaptureRef.current(null);
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          width: { ideal: 640 },
          height: { ideal: 480 },
          frameRate: { ideal: 20, max: 24 },
          facingMode: "user",
        },
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

      streamRef.current = stream;
      setupAudioAnalysis(stream);
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }
      setCameraReady(true);
      setRemainingSeconds(60);
      captureStartedAtRef.current = performance.now();
      setStatus("Center your face in the guide");
      startCaptureSessionTimeout();
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Camera or microphone permission was blocked";
      setStatus(`Permission blocked: ${message}`);
      onErrorRef.current?.(`Camera or microphone blocked: ${message}`);
    }
  }

  function handleStartCameraClick() {
    void startCamera();
    window.setTimeout(() => {
      capturePanelRef.current?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    }, 50);
  }

  function resetRecordingState(nextState = defaultFaceState) {
    validFaceStartedAtRef.current = 0;
    captureStartedAtRef.current = 0;
    recordingStartedAtRef.current = 0;
    voiceChallengeRevealedAtRef.current = 0;
    requestChallengeInFlightRef.current = false;
    lastChallengeRequestAtRef.current = 0;
    chunksRef.current = [];
    speechSamplesRef.current = 0;
    speechStartedAtRef.current = 0;
    lastSpeechAtRef.current = 0;
    mouthOpenSamplesRef.current = 0;
    mouthOpenedAtRef.current = 0;
    noiseFloorRef.current = 0.012;
    completedSessionRef.current = false;
    savingRef.current = false;
    setShowVoiceChallenge(false);
    setReadyHoldProgress(0);
    faceStateRef.current = nextState;
    clearMaxRecordingTimeout();
    setFaceState(nextState);
    setRecording(false);
    setSaving(false);
  }

  function closeCamera(nextState = defaultFaceState) {
    if (recorderRef.current && recorderRef.current.state !== "inactive") {
      ignoreNextSaveRef.current = true;
      recorderRef.current.stop();
    }
    recorderRef.current = null;
    stopCameraTracks();
    clearCaptureSessionTimeout();
    clearMaxRecordingTimeout();
    cancelAnimationFrame(animationRef.current);
    setCameraReady(false);
    setRecording(false);
    resetRecordingState(nextState);
  }

  function retryCapture() {
    setSessionExpired(false);
    ignoreNextSaveRef.current = true;
    if (recorderRef.current && recorderRef.current.state !== "inactive") {
      recorderRef.current.stop();
    }
    recorderRef.current = null;
    onCaptureRef.current(null);
    closeCamera();
    setStatus("Camera idle");
    onRetryRef.current?.();
  }

  function handleCaptureProgress(nextState: FaceState) {
    const now = performance.now();

    if (!nextState.ready) {
      validFaceStartedAtRef.current = 0;
      setReadyHoldProgress(0);
      recordMouthOpenSample(now, Boolean(nextState.metrics?.mouthOpen));
      if (voiceChallengeRevealedAtRef.current) {
        recordSpeechSample(now);
        if (
          hasDetectedSpeech(now) &&
          hasDetectedMouthOpen(now) &&
          now - voiceChallengeRevealedAtRef.current >= MIN_VOICE_RECORDING_MS &&
          now - lastSpeechAtRef.current >= SPEECH_END_SILENCE_MS
        ) {
          completedSessionRef.current = true;
          stopRecording();
        }
      }
      return;
    }

    if (!recordingStartedAtRef.current) {
      if (!challengeReady) {
        if (
          (!lastChallengeRequestAtRef.current ||
            now - lastChallengeRequestAtRef.current >=
              CHALLENGE_REQUEST_RETRY_MS) &&
          !requestChallengeInFlightRef.current &&
          onRequestVoiceChallengeRef.current
        ) {
          requestChallengeInFlightRef.current = true;
          lastChallengeRequestAtRef.current = now;
          setStatus("Look at the camera");
          void onRequestVoiceChallengeRef
            .current()
            ?.catch(() => undefined)
            .finally(() => {
              requestChallengeInFlightRef.current = false;
            });
        }
        return;
      }

      if (!validFaceStartedAtRef.current) {
        validFaceStartedAtRef.current = now;
      }
      setReadyHoldProgress(
        clamp((now - validFaceStartedAtRef.current) / FACE_STABLE_MS, 0, 1),
      );
      if (now - validFaceStartedAtRef.current >= FACE_STABLE_MS) {
        startRecording();
      }
      return;
    }

    const elapsed = now - recordingStartedAtRef.current;
    if (!voiceChallengeRevealedAtRef.current) {
      sampleAmbientNoise();
    }

    if (voiceChallengeRevealedAtRef.current) {
      recordSpeechSample(now);
      recordMouthOpenSample(now, Boolean(nextState.metrics?.mouthOpen));
    }

    if (
      voiceChallengeRevealedAtRef.current &&
      now - voiceChallengeRevealedAtRef.current >= MIN_VOICE_RECORDING_MS &&
      hasDetectedSpeech(now) &&
      hasDetectedMouthOpen(now) &&
      now - lastSpeechAtRef.current >= SPEECH_END_SILENCE_MS
    ) {
      completedSessionRef.current = true;
      stopRecording();
      return;
    }

    if (elapsed >= MAX_RECORDING_MS) {
      if (!hasDetectedSpeech(now)) {
        abortRecording(
          "No speech was detected after the phrase appeared. Please read the phrase aloud and retry.",
        );
        return;
      }
      if (!hasDetectedMouthOpen(now)) {
        abortRecording(
          "We could not clearly confirm the spoken challenge. Please read the digits again while facing the camera.",
        );
        return;
      }
      completedSessionRef.current = true;
      stopRecording();
    }
  }

  function startRecording() {
    if (
      !streamRef.current ||
      !challengeReady ||
      savingRef.current ||
      completedSessionRef.current ||
      recordingStartedAtRef.current
    ) {
      return;
    }

    chunksRef.current = [];
    const mimeType = getSupportedMimeType();
    if (!mimeType) {
      onErrorRef.current?.(
        "This browser does not support MP4 camera recording. Please try another browser.",
      );
      closeCamera({
        ...defaultFaceState,
        instruction: "MP4 recording unavailable",
        detail: "Please try a browser that supports MP4 camera recording.",
      });
      return;
    }

    const recorder = new MediaRecorder(streamRef.current, {
      mimeType,
      videoBitsPerSecond: 800_000,
    });

    recorder.addEventListener("dataavailable", (event) => {
      if (event.data.size > 0) {
        chunksRef.current.push(event.data);
      }
    });
    recorder.addEventListener("stop", saveRecording);
    recorder.start(250);
    recorderRef.current = recorder;
    recordingStartedAtRef.current = performance.now();
    voiceChallengeRevealedAtRef.current = performance.now();
    speechSamplesRef.current = 0;
    speechStartedAtRef.current = 0;
    lastSpeechAtRef.current = 0;
    mouthOpenSamplesRef.current = 0;
    mouthOpenedAtRef.current = 0;
    setRecording(true);
    setShowVoiceChallenge(true);
    setReadyHoldProgress(1);
    setStatus("Read the phrase aloud");
    clearMaxRecordingTimeout();
    maxRecordingTimeoutRef.current = window.setTimeout(() => {
      if (!completedSessionRef.current && !savingRef.current) {
        const now = performance.now();
        if (!hasDetectedSpeech(now)) {
          abortRecording(
            "No speech was detected. Please read the phrase aloud and retry.",
          );
          return;
        }
        if (!hasDetectedMouthOpen(now)) {
          abortRecording(
            "We could not clearly confirm the spoken challenge. Please read the digits again while facing the camera.",
          );
        }
      }
    }, MAX_RECORDING_MS);
  }

  function abortRecording(message: string) {
    if (!recorderRef.current || recorderRef.current.state === "inactive") {
      return;
    }

    ignoreNextSaveRef.current = true;
    recorderRef.current.stop();
    recorderRef.current = null;
    onCaptureRef.current(null);
    setStatus("Recording stopped");
    onErrorRef.current?.(message);
    closeCamera({
      ...defaultFaceState,
      instruction: "Capture stopped",
      detail: message,
    });
  }

  function stopRecording() {
    if (!recorderRef.current || recorderRef.current.state === "inactive") {
      return;
    }

    clearMaxRecordingTimeout();
    savingRef.current = true;
    setRecording(false);
    setSaving(true);
    setStatus("Saving recording");
    recorderRef.current.requestData();
    window.setTimeout(() => {
      if (recorderRef.current && recorderRef.current.state !== "inactive") {
        recorderRef.current.stop();
      }
    }, 160);
  }

  function saveRecording() {
    if (ignoreNextSaveRef.current) {
      ignoreNextSaveRef.current = false;
      resetRecordingState();
      return;
    }

    const recorder = recorderRef.current;
    const type = recorder?.mimeType || "video/mp4";
    const extension = getExtensionFromMimeType(type);
    const blob = new Blob(chunksRef.current, { type });
    if (blob.size < 1024) {
      recorderRef.current = null;
      savingRef.current = false;
      completedSessionRef.current = false;
      setSaving(false);
      setStatus("Recording failed");
      onErrorRef.current?.("Recording did not contain video data. Please retry.");
      resetRecordingState({
        ...defaultFaceState,
        instruction: "Recording failed",
        detail: "Please retry the face capture.",
      });
      return;
    }
    const file = new File(
      [blob],
      `ekyc-face-voice-${new Date().toISOString().replace(/[:.]/g, "-")}.${extension}`,
      { type },
    );

    onCaptureRef.current(file);
    recorderRef.current = null;
    savingRef.current = false;
    completedSessionRef.current = true;
    setSaving(false);
    setStatus("Face and voice video ready");
    closeCamera({
      ...defaultFaceState,
      instruction: "Face and voice captured",
      detail: "Press Submit for processing or Retry to start again.",
      phase: "captured",
    });
  }

  const captureFrameClass =
    "relative h-[min(58vh,540px)] min-h-[420px] overflow-hidden rounded-lg border border-cyan-300/25 bg-slate-950 shadow-[0_18px_48px_rgba(8,15,31,0.45)] sm:min-h-[460px] lg:h-[min(62vh,620px)] xl:h-[min(64vh,660px)]";

  return (
    <div className="grid gap-4">
      <div className="grid gap-3 rounded-lg border border-white/10 bg-slate-950/55 p-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
        <div className="min-w-0">
          <p className="text-base font-bold text-white">
            {translateCaptureText(status)}
          </p>
          <p className="mt-1 text-xs text-slate-400">
            {captureMetaText()}
          </p>
        </div>
        {!cameraReady ? (
          <button
            className="primary-button justify-center disabled:cursor-not-allowed disabled:opacity-50"
            disabled={disabled || saving}
            onClick={handleStartCameraClick}
            type="button"
          >
            <Camera size={16} />
            {t("ekyc.capture.startCamera")}
          </button>
        ) : (
          <button
            className="secondary-button justify-center disabled:cursor-not-allowed disabled:opacity-50"
            disabled={saving}
            onClick={() => closeCamera()}
            type="button"
          >
            <VideoOff size={16} />
            {t("ekyc.capture.closeCamera")}
          </button>
        )}
      </div>

      <div className={captureFrameClass} ref={capturePanelRef}>
        <video
          ref={videoRef}
          className="absolute inset-0 h-full w-full scale-x-[-1] object-cover"
          autoPlay
          muted
          playsInline
        />
        <canvas
          ref={canvasRef}
          className="pointer-events-none absolute inset-0 h-full w-full"
          aria-hidden="true"
        />

        {!cameraReady ? (
          <div className="absolute inset-0 grid place-items-center bg-slate-950/92 p-6 text-center">
            <div className="grid max-w-md justify-items-center gap-3">
              <div className="grid h-16 w-16 place-items-center rounded-lg border border-cyan-300/30 bg-cyan-300/10 text-cyan-100">
                {capturedFile ? <Check size={28} /> : <Video size={28} />}
              </div>
              <div>
                <h3 className="text-xl font-black">
                  {capturedFile
                    ? t("ekyc.capture.videoReady")
                    : sessionExpired
                      ? t("ekyc.capture.sessionExpiredTitle")
                      : t("ekyc.capture.captureFaceVoice")}
                </h3>
                <p className="mt-2 text-sm leading-6 text-slate-300">
                  {capturedFile
                    ? t("ekyc.capture.captureComplete")
                    : sessionExpired
                      ? t("ekyc.capture.timedOutDetailed")
                      : faceState.instruction === defaultFaceState.instruction
                      ? t("ekyc.capture.startCameraReadPhrase")
                      : translateCaptureText(faceState.detail)}
                </p>
              </div>
            </div>
          </div>
        ) : null}

        {cameraReady ? (
          <>
            <div
              className={`absolute bottom-8 left-1/2 grid w-[min(500px,calc(100%-32px))] -translate-x-1/2 gap-2 rounded-xl border px-4 py-3 text-center shadow-[0_18px_48px_rgba(8,15,31,0.35)] backdrop-blur lg:bottom-10 ${
                faceState.ready
                  ? "border-emerald-300/50 bg-emerald-950/70"
                  : faceState.found
                    ? "border-amber-300/50 bg-amber-950/60"
                    : "border-white/12 bg-slate-950/75"
              }`}
            >
              {challengeReady && showVoiceChallenge ? (
                <div className="grid gap-3 rounded-lg border border-cyan-300/35 bg-slate-950/85 px-3 py-3 shadow-[0_0_28px_rgba(34,211,238,0.14)]">
                  <span className="flex items-center justify-center gap-2 text-xs font-black uppercase text-cyan-100">
                    <Mic size={14} />
                    {t("ekyc.capture.readDigits")}
                  </span>
                  <div className="flex flex-wrap justify-center gap-2">
                    {displayDigits.map((digit, index) => (
                      <span
                        className="grid h-12 w-11 place-items-center rounded-md border border-cyan-200/70 bg-cyan-300/18 text-3xl font-black text-white shadow-[0_0_18px_rgba(103,232,249,0.2)] sm:h-14 sm:w-12 sm:text-4xl"
                        key={`${digit}-${index}`}
                      >
                        {digit}
                      </span>
                    ))}
                  </div>
                  {voiceChallengeHint ? (
                    <span className="text-sm font-bold text-cyan-50">
                      {t("ekyc.capture.say", { hint: voiceChallengeHint })}
                    </span>
                  ) : null}
                  <span className="text-xs font-semibold text-slate-300">
                    {t("ekyc.capture.doNotReadLargeNumber")}
                  </span>
                </div>
              ) : null}
              <strong className="text-lg font-black text-white">
                {translateCaptureText(faceState.instruction)}
              </strong>
              <span className="text-sm text-slate-200">
                {translateCaptureText(faceState.detail)}
              </span>
              <div className="mt-1 flex flex-wrap justify-center gap-2">
                {captureChecks.map((item) => (
                  <span
                    className={`rounded-full border px-3 py-1 text-[11px] font-bold ${
                      item.active
                        ? "border-emerald-300/40 bg-emerald-400/10 text-emerald-100"
                        : "border-white/10 bg-white/[0.04] text-slate-300"
                    }`}
                    key={item.label}
                  >
                    {item.label}
                  </span>
                ))}
              </div>
              {!showVoiceChallenge && challengeReady ? (
                <div className="mx-auto mt-1 w-full max-w-[220px]">
                  <div className="h-1.5 overflow-hidden rounded-full bg-white/10">
                    <div
                      className="h-full rounded-full bg-emerald-300 transition-[width] duration-150"
                      style={{ width: `${Math.round(readyHoldProgress * 100)}%` }}
                    />
                  </div>
                </div>
              ) : null}
              {cameraReady && !challengeReady ? (
                <span className="text-xs font-semibold text-cyan-100">
                  {challengeLoading
                    ? t("ekyc.messages.preparingVoice")
                    : t("ekyc.capture.holdStill")}
                </span>
              ) : null}
            </div>
          </>
        ) : null}
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        {onBackToDocuments ? (
          <button
            className="secondary-button justify-center disabled:cursor-not-allowed disabled:opacity-50"
            disabled={backDisabled}
            onClick={onBackToDocuments}
            type="button"
          >
            <ArrowLeft size={16} />
            {t("ekyc.capture.backToDocuments")}
          </button>
        ) : (
          <span />
        )}
        <div className="flex justify-end">
          <button
            className="secondary-button justify-center disabled:cursor-not-allowed disabled:opacity-50"
            disabled={disabled}
            onClick={retryCapture}
            type="button"
          >
            {saving ? (
              <Loader2 className="animate-spin" size={16} />
            ) : capturedFile ? (
              <RefreshCcw size={16} />
            ) : (
              <RotateCcw size={16} />
            )}
            {t("ekyc.capture.retry")}
          </button>
        </div>
      </div>
    </div>
  );
}
