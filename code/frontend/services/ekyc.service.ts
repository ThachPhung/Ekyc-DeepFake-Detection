import { API_BASE_URL, ApiError, apiFetch, getStoredToken } from "@/lib/api";
import type { MessageResponse } from "@/services/auth.service";

export type EkycRequestStatus =
  | "PENDING"
  | "PROCESSING"
  | "SUCCESS"
  | "FAILED"
  | "MANUAL_REVIEW";

export type EkycVideoStatus =
  | "NOT_STARTED"
  | "PENDING"
  | "PROCESSING"
  | "SUCCESS"
  | "FAILED";

export type FaceDecision = "match" | "consider" | "not_match";

export type EkycDocumentType = "CCCD" | "GPLX" | "HOCHIEU";

export type EkycDocumentFields = {
  full_name?: string;
  id_number?: string;
  passport_number?: string;
  date_of_birth?: string;
  birth_year?: string;
  sex?: string;
  gender?: string;
  nationality?: string;
  address?: string;
  place_of_origin?: string;
  place_of_residence?: string;
  issue_date?: string;
  issue_place?: string;
  expiry_date?: string;
  expired_date?: string;
};

export type AdminEkycDocumentFieldsPayload = Partial<EkycDocumentFields>;

export type EkycRequestResponse = {
  request_id: string;
  status: EkycRequestStatus;
  message?: string | null;
  ocr_result?: Record<string, unknown> | null;
  document_confirmed_fields?: Partial<EkycDocumentFields> | null;
  document_confirmed_at?: string | null;
  video_status: EkycVideoStatus;
  video_result?: Record<string, unknown> | null;
  voice_result?: Record<string, unknown> | null;
  face_similarity?: number | null;
  face_decision?: FaceDecision | string | null;
  error_message?: string | null;
  video_error_message?: string | null;
  model_version?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  processed_at?: string | null;
  video_processed_at?: string | null;
};

export type EkycRequestAdminResponse = EkycRequestResponse & {
  id: string;
  user_id?: string | null;
  owner_email?: string | null;
  owner_full_name?: string | null;
  duplicate_identity_detected?: boolean;
  duplicate_identity_warning?: string | null;
  image_path?: string | null;
  front_image_path?: string | null;
  back_image_path?: string | null;
  video_path?: string | null;
  video_result?: Record<string, unknown> | null;
  ai_admin_review?: AdminAiReview | null;
  error_message?: string | null;
  video_error_message?: string | null;
};

export type AdminAiReviewBangChung = {
  hang_muc: string;
  ket_qua: string;
  do_tin_cay: number;
};

export type AdminAiReview = {
  ket_luan: "PASS" | "REVIEW" | "REJECT";
  muc_do_rui_ro: "THẤP" | "TRUNG BÌNH" | "CAO";
  do_tin_cay: number;
  tom_tat: string;
  diem_tich_cuc?: string[];
  van_de_phat_hien?: string[];
  bang_chung?: AdminAiReviewBangChung[];
  khuyen_nghi_cho_admin?: string;
  danh_sach_can_admin_kiem_tra?: string[];
  du_lieu_con_thieu?: string[];
  giai_thich?: string;
  provider?: string | null;
  model?: string | null;
  error?: string | null;
  ready?: boolean;
};

export type EkycRequestsAdminListResponse = {
  data: EkycRequestAdminResponse[];
  count: number;
};

export type AdminEkycListParams = {
  skip?: number;
  limit?: number;
  status?: EkycRequestStatus | "";
  videoStatus?: EkycVideoStatus | "";
  faceDecision?: FaceDecision | "";
  query?: string;
  sort?: "latest" | "oldest";
};

export type AdminEkycFileKind = "front" | "back" | "liveness";

export type MyEkycStatusResponse = {
  is_verified: boolean;
  verified_at?: string | null;
  document_type?: EkycDocumentType | null;
  latest_request?: EkycRequestResponse | null;
};

export type MyVerifiedIdentityResponse = {
  is_verified: boolean;
  document_type?: EkycDocumentType | null;
  identity_number?: string | null;
  full_name?: string | null;
  birth_date?: string | null;
  gender?: string | null;
  nationality?: string | null;
  address?: string | null;
  place_of_origin?: string | null;
  place_of_residence?: string | null;
  issued_date?: string | null;
  issue_place?: string | null;
  expired_date?: string | null;
  verified_at?: string | null;
};

export type VoiceSessionResponse = {
  session_id: string;
  status: "PENDING" | "PASSED" | "FAILED" | "EXPIRED";
  display_digits: string[];
  display_text: string;
  spoken_hint: string;
  attempts: number;
  max_attempts: number;
  remaining_attempts: number;
  expires_at: string;
  expires_in_seconds: number;
};

export type VoiceSessionVerifyResponse = VoiceSessionResponse & {
  verified: boolean;
  can_continue: boolean;
  reset_required: boolean;
  decision?: string | null;
  warning?: string | null;
  verified_against_text?: string | null;
  verified_against_hint?: string | null;
};

export async function createEkycRequest({
  frontImage,
  backImage,
  videoFile,
  documentType,
  voiceSessionId,
  voiceChallengeText,
}: {
  frontImage: File;
  backImage: File;
  videoFile: File;
  documentType: EkycDocumentType;
  voiceSessionId?: string;
  voiceChallengeText?: string;
}): Promise<EkycRequestResponse> {
  const body = new FormData();
  body.set("front_image", frontImage);
  body.set("back_image", backImage);
  body.set("liveness_file", videoFile);
  body.set("document_type", documentType);
  if (voiceSessionId) {
    body.set("voice_session_id", voiceSessionId);
  }
  if (voiceChallengeText) {
    body.set("voice_challenge_text", voiceChallengeText);
  }

  return apiFetch<EkycRequestResponse>(
    "/ekyc/requests/",
    {
      method: "POST",
      body,
    },
    { auth: true },
  );
}

export async function getMyEkycStatus(): Promise<MyEkycStatusResponse> {
  return apiFetch<MyEkycStatusResponse>(
    "/ekyc/requests/me/status",
    { method: "GET" },
    { auth: true },
  );
}

export async function getMyVerifiedIdentity({
  reveal = false,
}: { reveal?: boolean } = {}): Promise<MyVerifiedIdentityResponse> {
  const params = reveal ? "?reveal=true" : "";

  return apiFetch<MyVerifiedIdentityResponse>(
    `/ekyc/requests/me/identity${params}`,
    { method: "GET" },
    { auth: true },
  );
}

export async function getEkycRequest(
  requestId: string,
): Promise<EkycRequestResponse> {
  return apiFetch<EkycRequestResponse>(
    `/ekyc/requests/${requestId}`,
    { method: "GET" },
    { auth: true },
  );
}

export async function listAdminEkycRequests({
  faceDecision = "",
  limit = 100,
  query = "",
  skip = 0,
  sort = "latest",
  status = "",
  videoStatus = "",
}: AdminEkycListParams = {}): Promise<EkycRequestsAdminListResponse> {
  const params = new URLSearchParams({
    skip: String(skip),
    limit: String(limit),
  });
  if (status) {
    params.set("status", status);
  }
  if (videoStatus) {
    params.set("video_status", videoStatus);
  }
  if (faceDecision) {
    params.set("face_decision", faceDecision);
  }
  if (query.trim()) {
    params.set("q", query.trim());
  }
  if (sort) {
    params.set("sort", sort);
  }

  return apiFetch<EkycRequestsAdminListResponse>(
    `/ekyc/requests/?${params.toString()}`,
    { method: "GET" },
    { auth: true },
  );
}

export async function getAdminEkycRequest(
  requestId: string,
): Promise<EkycRequestAdminResponse> {
  return apiFetch<EkycRequestAdminResponse>(
    `/ekyc/requests/${requestId}/admin-detail`,
    { method: "GET" },
    { auth: true },
  );
}

export async function createVoiceSession(): Promise<VoiceSessionResponse> {
  return apiFetch<VoiceSessionResponse>(
    "/ekyc/requests/voice-session",
    { method: "POST" },
    { auth: true },
  );
}

export async function verifyVoiceSession({
  sessionId,
  videoFile,
}: {
  sessionId: string;
  videoFile: File;
}): Promise<VoiceSessionVerifyResponse> {
  const body = new FormData();
  body.set("liveness_file", videoFile);

  return apiFetch<VoiceSessionVerifyResponse>(
    `/ekyc/requests/voice-session/${sessionId}/verify`,
    {
      method: "POST",
      body,
    },
    { auth: true },
  );
}


export async function deleteAdminEkycRequest(
  requestId: string,
): Promise<MessageResponse> {
  return apiFetch<MessageResponse>(
    `/ekyc/requests/${requestId}`,
    { method: "DELETE" },
    { auth: true },
  );
}

export async function approveAdminEkycRequest(
  requestId: string,
  reason = "",
): Promise<EkycRequestAdminResponse> {
  return apiFetch<EkycRequestAdminResponse>(
    `/ekyc/requests/${requestId}/approve`,
    {
      method: "POST",
      body: JSON.stringify({ reason }),
    },
    { auth: true },
  );
}

export async function rejectAdminEkycRequest(
  requestId: string,
  reason: string,
): Promise<EkycRequestAdminResponse> {
  return apiFetch<EkycRequestAdminResponse>(
    `/ekyc/requests/${requestId}/reject`,
    {
      method: "POST",
      body: JSON.stringify({ reason }),
    },
    { auth: true },
  );
}

export async function retryAdminEkycRequest(
  requestId: string,
): Promise<EkycRequestAdminResponse> {
  return apiFetch<EkycRequestAdminResponse>(
    `/ekyc/requests/${requestId}/retry`,
    { method: "POST" },
    { auth: true },
  );
}

export async function updateAdminEkycDocumentFields(
  requestId: string,
  fields: AdminEkycDocumentFieldsPayload,
): Promise<EkycRequestAdminResponse> {
  return apiFetch<EkycRequestAdminResponse>(
    `/ekyc/requests/${requestId}/document-fields`,
    {
      method: "PATCH",
      body: JSON.stringify(fields),
    },
    { auth: true },
  );
}

export async function generateAdminAiReview(
  requestId: string,
): Promise<EkycRequestAdminResponse> {
  return apiFetch<EkycRequestAdminResponse>(
    `/ekyc/requests/${requestId}/ai-review`,
    { method: "POST" },
    { auth: true },
  );
}

export async function getAdminEkycFileBlob(
  requestId: string,
  fileKind: AdminEkycFileKind,
): Promise<Blob | null> {
  const token = getStoredToken();
  const response = await fetch(
    `${API_BASE_URL}/ekyc/requests/${requestId}/files/${fileKind}`,
    {
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    },
  );

  if (response.status === 404) {
    return null;
  }

  if (!response.ok) {
    let payload = null;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }
    throw new ApiError(response.status, payload, "Could not load eKYC media");
  }

  return response.blob();
}
