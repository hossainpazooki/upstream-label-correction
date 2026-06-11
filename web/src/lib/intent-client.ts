/**
 * Typed HTTP client for the Go intent-controller service.
 * Proxies intent lifecycle and workflow operations.
 */

const INTENT_CONTROLLER_URL =
  process.env.INTENT_CONTROLLER_URL ?? "http://localhost:8090";

// Shared service token for the internal control plane (gap #8). Server-only —
// must NOT be a NEXT_PUBLIC_ var, so it never reaches the browser bundle. When
// set, it is attached to every controller call as X-Service-Token; when unset
// (local dev), no header is sent and the controller runs in bypass mode.
const SERVICE_AUTH_TOKEN = process.env.SERVICE_AUTH_TOKEN;

export class IntentControllerError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "IntentControllerError";
  }
}

async function intentFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${INTENT_CONTROLLER_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(SERVICE_AUTH_TOKEN ? { "X-Service-Token": SERVICE_AUTH_TOKEN } : {}),
      ...options.headers,
    },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new IntentControllerError(res.status, text);
  }
  return res.json() as Promise<T>;
}

// --- Intent Types ---

export interface Intent {
  id: number;
  intent_id: string;
  intent_type: "analysis" | "training" | "validation";
  status:
    | "declared"
    | "resolving"
    | "blocked"
    | "active"
    | "verifying"
    | "achieved"
    | "failed"
    | "cancelled";
  params: Record<string, unknown>;
  infra_state: Record<string, unknown>;
  workflow_ids: string[];
  eval_results: Record<string, unknown>;
  created_at: string;
  resolved_at: string | null;
  activated_at: string | null;
  completed_at: string | null;
  error: string | null;
  requested_by: string;
}

export interface IntentStatus {
  intent_id: string;
  status: string;
  intent_type: string;
  workflow_ids: string[];
  eval_results: Record<string, unknown>;
  error: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface CreateIntentRequest {
  intent_type: "analysis" | "training" | "validation";
  params?: Record<string, unknown>;
  requested_by?: string;
}

// --- Workflow Types ---

export interface WorkflowExecution {
  id: number;
  workflow_id: string;
  workflow_type: string;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  current_phase: string;
  phases_completed: string[];
  started_at: string;
  completed_at: string | null;
  result: Record<string, unknown>;
  error: string | null;
}

export interface TriggerWorkflowRequest {
  workflow_type: string;
  params?: Record<string, unknown>;
}

export interface WorkflowStep {
  phase_name: string;
  status: string;
}

// --- Intent Operations ---

export async function createIntent(
  req: CreateIntentRequest,
): Promise<Intent> {
  return intentFetch<Intent>("/api/v1/intents", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export async function getIntent(intentId: string): Promise<Intent> {
  return intentFetch<Intent>(`/api/v1/intents/${intentId}`);
}

export async function listIntents(filters?: {
  status?: string;
  type?: string;
}): Promise<Intent[]> {
  const params = new URLSearchParams();
  if (filters?.status) params.set("status", filters.status);
  if (filters?.type) params.set("type", filters.type);
  const qs = params.toString();
  return intentFetch<Intent[]>(`/api/v1/intents${qs ? `?${qs}` : ""}`);
}

export async function cancelIntent(intentId: string): Promise<Intent> {
  return intentFetch<Intent>(`/api/v1/intents/${intentId}`, {
    method: "DELETE",
  });
}

export async function processIntent(intentId: string): Promise<Intent> {
  return intentFetch<Intent>(`/api/v1/intents/${intentId}/process`, {
    method: "POST",
  });
}

export async function getIntentStatus(
  intentId: string,
): Promise<IntentStatus> {
  return intentFetch<IntentStatus>(`/api/v1/intents/${intentId}/status`);
}

// --- Workflow Operations ---

export async function triggerWorkflow(
  req: TriggerWorkflowRequest,
): Promise<{ workflow_id: string; status: string }> {
  return intentFetch<{ workflow_id: string; status: string }>(
    "/api/v1/workflows",
    { method: "POST", body: JSON.stringify(req) },
  );
}

export async function getWorkflow(
  workflowId: string,
): Promise<WorkflowExecution> {
  return intentFetch<WorkflowExecution>(`/api/v1/workflows/${workflowId}`);
}

export async function listWorkflows(filters?: {
  status?: string;
}): Promise<WorkflowExecution[]> {
  const params = new URLSearchParams();
  if (filters?.status) params.set("status", filters.status);
  const qs = params.toString();
  return intentFetch<WorkflowExecution[]>(
    `/api/v1/workflows${qs ? `?${qs}` : ""}`,
  );
}

export async function cancelWorkflow(
  workflowId: string,
): Promise<{ status: string }> {
  return intentFetch<{ status: string }>(
    `/api/v1/workflows/${workflowId}/cancel`,
    { method: "POST" },
  );
}

export async function getWorkflowSteps(
  workflowId: string,
): Promise<WorkflowStep[]> {
  return intentFetch<WorkflowStep[]>(`/api/v1/workflows/${workflowId}/steps`);
}
