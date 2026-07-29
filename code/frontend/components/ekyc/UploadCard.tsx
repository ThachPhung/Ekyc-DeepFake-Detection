"use client";

import { useLanguage } from "@/contexts/LanguageContext";
import { motion } from "framer-motion";
import Image from "next/image";
import {
  ChangeEvent,
  DragEvent,
  KeyboardEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { FileUp, ScanLine, X } from "lucide-react";

type UploadCardProps = {
  title: string;
  accent: "cyan" | "violet";
  disabled?: boolean;
  file?: File | null;
  maxFileSizeMb?: number;
  onFileChange?: (file: File | null) => void;
};

const acceptedImageTypes = ["image/png", "image/jpeg"];

export function UploadCard({
  title,
  accent,
  disabled = false,
  file: controlledFile,
  maxFileSizeMb = 5,
  onFileChange,
}: UploadCardProps) {
  const { t } = useLanguage();
  const inputRef = useRef<HTMLInputElement>(null);
  const [localFile, setLocalFile] = useState<File | null>(null);
  const [error, setError] = useState("");
  const maxFileSize = maxFileSizeMb * 1024 * 1024;
  const isControlled = controlledFile !== undefined;
  const file = isControlled ? controlledFile : localFile;
  const previewUrl = useMemo(() => {
    if (!file) {
      return null;
    }
    return URL.createObjectURL(file);
  }, [file]);

  useEffect(() => {
    if (!previewUrl) {
      return;
    }

    return () => {
      URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  function validateAndSetFile(nextFile: File | undefined) {
    setError("");

    if (!nextFile) {
      return;
    }

    if (!acceptedImageTypes.includes(nextFile.type)) {
      setError(t("ekyc.upload.invalidType"));
      return;
    }

    if (nextFile.size > maxFileSize) {
      setError(t("ekyc.upload.fileTooLarge", { size: maxFileSizeMb }));
      return;
    }

    if (!isControlled) {
      setLocalFile(nextFile);
    }
    onFileChange?.(nextFile);
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    validateAndSetFile(event.target.files?.[0]);
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    if (disabled) {
      return;
    }
    validateAndSetFile(event.dataTransfer.files?.[0]);
  }

  function clearFile() {
    if (!isControlled) {
      setLocalFile(null);
    }
    setError("");
    onFileChange?.(null);

    if (inputRef.current) {
      inputRef.current.value = "";
    }
  }

  function handleDropzoneKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (disabled) {
      return;
    }
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      inputRef.current?.click();
    }
  }

  return (
    <motion.article
      className={`glass-panel upload-card accent-${accent} p-5`}
      initial={{ opacity: 0, y: 16 }}
      transition={{ duration: 0.4 }}
      viewport={{ once: true }}
      whileHover={{ y: -5 }}
      whileInView={{ opacity: 1, y: 0 }}
    >
      <div>
        <h2 className="text-xl font-bold">{title}</h2>
      </div>
      <div
        className={`upload-dropzone mt-5 ${
          disabled ? "cursor-not-allowed opacity-60" : "cursor-pointer"
        }`}
        onClick={() => {
          if (!disabled) {
            inputRef.current?.click();
          }
        }}
        onDragOver={(event) => event.preventDefault()}
        onDrop={handleDrop}
        onKeyDown={handleDropzoneKeyDown}
        role="button"
        tabIndex={0}
      >
        {previewUrl ? (
          <div className="grid w-full gap-3">
            <div className="flex justify-end">
              <button
                aria-label={t("ekyc.upload.removeImage", { title })}
                className="grid h-9 w-9 place-items-center rounded-full border border-white/20 bg-slate-950/85 text-white shadow-lg transition hover:border-rose-300 hover:bg-rose-500/90 disabled:cursor-not-allowed disabled:opacity-50"
                disabled={disabled}
                onClick={(event) => {
                  event.stopPropagation();
                  clearFile();
                }}
                title={t("ekyc.upload.removeImage", { title })}
                type="button"
              >
                <X size={18} />
              </button>
            </div>
            <Image
              alt={`${title} preview`}
              className="max-h-64 w-full rounded-lg object-contain"
              height={260}
              unoptimized
              src={previewUrl}
              width={420}
            />
          </div>
        ) : (
          <IdCardArtwork accent={accent} />
        )}
        {file ? (
          <p className="mt-4 max-w-full truncate text-sm font-bold text-white">
            {file.name}
          </p>
        ) : null}
      </div>
      {error ? (
        <p className="mt-3 rounded-lg border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm font-semibold text-rose-100">
          {error}
        </p>
      ) : null}
      <input
        accept={acceptedImageTypes.join(",")}
        className="hidden"
        disabled={disabled}
        onChange={handleFileChange}
        ref={inputRef}
        type="file"
      />
      <div className="mt-5 flex items-center gap-3">
        <button
          className="secondary-button flex-1 justify-center disabled:cursor-not-allowed disabled:opacity-50"
          disabled={disabled}
          onClick={() => inputRef.current?.click()}
          type="button"
        >
          <FileUp size={16} />
          {t("ekyc.upload.button")}
        </button>
      </div>
    </motion.article>
  );
}

function IdCardArtwork({ accent }: { accent: "cyan" | "violet" }) {
  const { t } = useLanguage();
  const stroke = accent === "cyan" ? "#22d3ee" : "#a855f7";

  return (
    <svg
      className="id-artwork"
      viewBox="0 0 320 200"
      role="img"
      aria-label={t("ekyc.upload.artworkLabel")}
    >
      <defs>
        <linearGradient id={`id-bg-${accent}`} x1="0" x2="1" y1="0" y2="1">
          <stop stopColor={accent === "cyan" ? "#0e7490" : "#6d28d9"} stopOpacity=".65" />
          <stop offset="1" stopColor="#020617" />
        </linearGradient>
      </defs>
      <rect x="18" y="24" width="284" height="152" rx="16" fill={`url(#id-bg-${accent})`} stroke={stroke} strokeOpacity=".62" />
      <rect x="42" y="52" width="64" height="48" rx="10" fill="#facc15" fillOpacity=".78" />
      <circle cx="76" cy="128" r="25" fill="#e0f2fe" fillOpacity=".62" />
      <path d="M42 164C49 143 62 135 76 135C91 135 103 143 110 164" stroke="#e0f2fe" strokeWidth="8" strokeLinecap="round" opacity=".65" />
      <rect x="132" y="55" width="126" height="9" rx="4" fill="#e0f2fe" opacity=".74" />
      <rect x="132" y="82" width="148" height="8" rx="4" fill="#93c5fd" opacity=".54" />
      <rect x="132" y="106" width="112" height="8" rx="4" fill="#93c5fd" opacity=".46" />
      <rect x="132" y="132" width="132" height="28" rx="8" fill="#020617" fillOpacity=".36" stroke={stroke} strokeOpacity=".4" />
      <path d="M282 34V62M282 34H254M38 166V138M38 166H66" stroke={stroke} strokeWidth="4" strokeLinecap="round" />
      <g className="ocr-scan-line">
        <ScanLine color={stroke} size={22} x={150} y={135} />
        <line x1="36" x2="284" y1="118" y2="118" stroke={stroke} strokeWidth="2" />
      </g>
    </svg>
  );
}
