import type {
  Budget,
  BudgetAlert,
  KeyIssued,
  ModelDeployment,
  Team,
  UsageRow,
  VirtualKey,
} from "@/api/types";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export type AuthHeaders = Record<string, string>;

let headersProvider: () => AuthHeaders = () => ({});

/** The auth store installs a provider so requests carry the dev principal. */
export function setAuthHeadersProvider(fn: () => AuthHeaders): void {
  headersProvider = fn;
}

export async function api<T>(method: string, path: string, body?: unknown): Promise<T> {
  const resp = await fetch(path, {
    method,
    headers: { "Content-Type": "application/json", ...headersProvider() },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!resp.ok) {
    throw new ApiError(resp.status, await resp.text());
  }
  if (resp.status === 204) {
    return undefined as T;
  }
  const contentType = resp.headers.get("content-type") ?? "";
  return contentType.includes("json") ? ((await resp.json()) as T) : ((await resp.text()) as T);
}

// --- Resource helpers ------------------------------------------------------

export const teams = {
  list: (orgId: string) => api<Team[]>("GET", `/api/v1/teams?org_id=${orgId}`),
  create: (orgId: string, name: string) =>
    api<Team>("POST", "/api/v1/teams", { org_id: orgId, name }),
};

export const models = {
  list: () => api<ModelDeployment[]>("GET", "/api/v1/models"),
  create: (body: Partial<ModelDeployment>) =>
    api<ModelDeployment>("POST", "/api/v1/models", body),
  remove: (id: string) => api<void>("DELETE", `/api/v1/models/${id}`),
};

export const keys = {
  list: (teamId: string) => api<VirtualKey[]>("GET", `/api/v1/keys?team_id=${teamId}`),
  issue: (body: { team_id: string; allowed_models?: string[] }) =>
    api<KeyIssued>("POST", "/api/v1/keys", body),
  rotate: (id: string) => api<KeyIssued>("POST", `/api/v1/keys/${id}/rotate`),
  revoke: (id: string) => api<VirtualKey>("POST", `/api/v1/keys/${id}/revoke`),
};

export const usage = {
  summary: (groupBy = "model") =>
    api<UsageRow[]>("GET", `/api/v1/usage?group_by=${groupBy}`),
};

export const budgets = {
  list: () => api<Budget[]>("GET", "/api/v1/budgets"),
  upsert: (body: { scope_type: string; scope_id: string; limit: string }) =>
    api<Budget>("PUT", "/api/v1/budgets", body),
  alerts: () => api<BudgetAlert[]>("GET", "/api/v1/budgets/alerts"),
};
