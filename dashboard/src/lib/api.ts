export type Outcome = "allow" | "deny" | "needs_approval" | "frozen";

export interface Agent {
  id: string;
  on_behalf_of: string;
  effective_tools: string[];
  daily_budget_inr: number;
  spent_today_inr: number;
  actions_today: Partial<Record<Outcome, number>>;
  blocked_amount_today_inr: number;
  frozen: { frozen_at: string; reason: string } | null;
  keys: string[];
}

export interface AuditEvent {
  id: number;
  at: string;
  agent_id: string;
  on_behalf_of: string | null;
  tool: string;
  amount_inr: number;
  cost_inr: number;
  outcome: Outcome;
  reason: string;
  anomaly_score: number | null;
  args_json: string | null;
  intent: string | null;
}

export interface Approval {
  id: number;
  created_at: string;
  agent_id: string;
  on_behalf_of: string | null;
  tool: string;
  amount_inr: number;
  status: string;
  args_json: string | null;
  intent: string | null;
  reason: string | null;
}

export interface Me {
  id: string;
  name: string;
  role: string;
  auth: "workos" | "dev";
  email: string | null;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

// Dev mode only: which demo user the dashboard acts as. With WorkOS, the session cookie is used.
let devUser: string | null = null;
export function setDevUser(id: string | null) {
  devUser = id;
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (devUser) headers.set("X-User-Id", devUser);
  if (init.body) headers.set("Content-Type", "application/json");
  const res = await fetch(`/api${path}`, { ...init, headers, cache: "no-store" });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {}
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

export const inr = (n: number) =>
  "₹" + n.toLocaleString("en-IN", { maximumFractionDigits: 0 });

export const istTime = (iso: string) =>
  new Date(iso).toLocaleTimeString("en-IN", {
    timeZone: "Asia/Kolkata",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
