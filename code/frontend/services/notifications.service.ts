import { apiFetch } from "@/lib/api";

export type NotificationItem = {
  id: string;
  user_id: string;
  type: string;
  title: string;
  message: string;
  data?: Record<string, unknown> | null;
  read_at?: string | null;
  created_at: string;
};

export type NotificationsResponse = {
  data: NotificationItem[];
  count: number;
  unread_count: number;
};

export type UnreadCountResponse = {
  unread_count: number;
};

export type ListNotificationsParams = {
  skip?: number;
  limit?: number;
  unreadOnly?: boolean;
  type?: string;
};

export async function listNotifications({
  limit = 20,
  skip = 0,
  type = "",
  unreadOnly = false,
}: ListNotificationsParams = {}): Promise<NotificationsResponse> {
  const params = new URLSearchParams({
    limit: String(limit),
    skip: String(skip),
  });

  if (unreadOnly) {
    params.set("unread_only", "true");
  }
  if (type) {
    params.set("type", type);
  }

  return apiFetch<NotificationsResponse>(
    `/notifications?${params.toString()}`,
    { method: "GET" },
    { auth: true },
  );
}

export async function getUnreadNotificationCount(): Promise<UnreadCountResponse> {
  return apiFetch<UnreadCountResponse>(
    "/notifications/unread-count",
    { method: "GET" },
    { auth: true },
  );
}

export async function markNotificationRead(
  notificationId: string,
): Promise<NotificationItem> {
  return apiFetch<NotificationItem>(
    `/notifications/${notificationId}/read`,
    { method: "PATCH" },
    { auth: true },
  );
}

export async function markAllNotificationsRead(): Promise<UnreadCountResponse> {
  return apiFetch<UnreadCountResponse>(
    "/notifications/read-all",
    { method: "PATCH" },
    { auth: true },
  );
}
