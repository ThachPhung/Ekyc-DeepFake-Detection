import { apiFetch } from "@/lib/api";

export type AdminUsersOverview = {
  total: number;
  active: number;
  admins: number;
  reviewers: number;
};

export type AdminEkycOverview = {
  total: number;
  pending: number;
  processing: number;
  success: number;
  failed: number;
  manual_review: number;
  today: number;
  latest_created_at?: string | null;
  latest_processed_at?: string | null;
};

export type AdminServiceHealth = {
  status: string;
  message?: string | null;
};

export type AdminQueueHealth = {
  status: string;
  queue_name: string;
  pending_jobs?: number | null;
  message?: string | null;
};

export type AdminSystemOverview = {
  database: AdminServiceHealth;
  redis: AdminServiceHealth;
  ekyc_queue: AdminQueueHealth;
  generated_at: string;
};

export type AdminOverview = {
  users: AdminUsersOverview;
  ekyc: AdminEkycOverview;
  system: AdminSystemOverview;
};

export type AdminRuntimeSettings = {
  project_name: string;
  environment: string;
  ai_service_url: string;
  ai_model_version: string;
  ekyc_queue_name: string;
  upload_dir: string;
  max_upload_size_mb: number;
  max_video_upload_size_mb: number;
};

export type AdminSettings = {
  ekyc_processing_timeout_minutes: number;
  ekyc_processing_timeout_source: string;
  user_notifications_enabled: boolean;
  user_notifications_source: string;
  runtime: AdminRuntimeSettings;
};

export type AdminSettingsUpdate = {
  ekyc_processing_timeout_minutes?: number;
  user_notifications_enabled?: boolean;
};

export type AdminAuditLog = {
  id: string;
  actor_user_id?: string | null;
  actor_email?: string | null;
  action: string;
  target_type: string;
  target_id?: string | null;
  target_label?: string | null;
  details?: Record<string, unknown> | null;
  created_at: string;
};

export type AdminAuditLogsResponse = {
  data: AdminAuditLog[];
  count: number;
};

export type AdminAuditLogsParams = {
  skip?: number;
  limit?: number;
  action?: string;
  targetType?: string;
  query?: string;
};

export async function getAdminOverview(): Promise<AdminOverview> {
  return apiFetch<AdminOverview>(
    "/admin/overview",
    { method: "GET" },
    { auth: true },
  );
}

export async function getAdminSettings(): Promise<AdminSettings> {
  return apiFetch<AdminSettings>(
    "/admin/settings",
    { method: "GET" },
    { auth: true },
  );
}

export async function updateAdminSettings(
  payload: AdminSettingsUpdate,
): Promise<AdminSettings> {
  return apiFetch<AdminSettings>(
    "/admin/settings",
    {
      body: JSON.stringify(payload),
      method: "PATCH",
    },
    { auth: true },
  );
}

export async function listAdminAuditLogs({
  action = "",
  limit = 50,
  query = "",
  skip = 0,
  targetType = "",
}: AdminAuditLogsParams = {}): Promise<AdminAuditLogsResponse> {
  const params = new URLSearchParams({
    skip: String(skip),
    limit: String(limit),
  });
  if (action) {
    params.set("action", action);
  }
  if (targetType) {
    params.set("target_type", targetType);
  }
  if (query.trim()) {
    params.set("q", query.trim());
  }

  return apiFetch<AdminAuditLogsResponse>(
    `/admin/audit-logs?${params.toString()}`,
    { method: "GET" },
    { auth: true },
  );
}
