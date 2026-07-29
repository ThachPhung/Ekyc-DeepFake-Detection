import { apiFetch } from "@/lib/api";
import type {
  MessageResponse,
  UserPublic,
  UserRole,
} from "@/services/auth.service";

export type UsersListResponse = {
  data: UserPublic[];
  count: number;
};

export type CreateUserPayload = {
  email: string;
  password: string;
  full_name?: string | null;
  is_active?: boolean;
  is_superuser?: boolean;
  role?: UserRole;
};

export type UpdateUserPayload = {
  is_active?: boolean;
  is_superuser?: boolean;
  role?: UserRole;
};

export async function listUsers(
  skip = 0,
  limit = 100,
): Promise<UsersListResponse> {
  const params = new URLSearchParams({
    skip: String(skip),
    limit: String(limit),
  });

  return apiFetch<UsersListResponse>(
    `/users/?${params.toString()}`,
    { method: "GET" },
    { auth: true },
  );
}

export async function createUser(
  payload: CreateUserPayload,
): Promise<UserPublic> {
  return apiFetch<UserPublic>(
    "/users/",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    { auth: true },
  );
}

export async function updateUser(
  userId: string,
  payload: UpdateUserPayload,
): Promise<UserPublic> {
  return apiFetch<UserPublic>(
    `/users/${userId}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
    { auth: true },
  );
}

export async function deleteUser(userId: string): Promise<MessageResponse> {
  return apiFetch<MessageResponse>(
    `/users/${userId}`,
    { method: "DELETE" },
    { auth: true },
  );
}
