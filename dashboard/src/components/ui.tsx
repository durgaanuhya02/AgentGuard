// Display pieces shared by the signed-in dashboard and the public demo page.
import type { Outcome } from "@/lib/api";

export const OUTCOME_STYLE: Record<Outcome, string> = {
  allow: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
  deny: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
  needs_approval: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
  frozen: "bg-violet-100 text-violet-800 dark:bg-violet-950 dark:text-violet-300",
};

export const OUTCOME_LABEL: Record<Outcome, string> = {
  allow: "Allowed",
  deny: "Denied",
  needs_approval: "Needs approval",
  frozen: "Frozen",
};

export const card = "rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900";
export const btn =
  "rounded-md px-3 py-1.5 text-sm font-medium transition disabled:opacity-50 cursor-pointer disabled:cursor-not-allowed";

export const isAi = (reason: string) => reason.startsWith("AI intent check");

export function argsLabel(json: string | null | undefined): string {
  if (!json) return "";
  try {
    const a = JSON.parse(json) as Record<string, unknown>;
    return a.order_id ? `on ${a.order_id}` : "";
  } catch {
    return "";
  }
}

export function AiChip() {
  return (
    <span
      title="Decided by the AI intent check"
      className="mt-0.5 shrink-0 rounded bg-sky-100 px-1 text-[10px] font-semibold text-sky-800 dark:bg-sky-950 dark:text-sky-300"
    >
      AI
    </span>
  );
}

export function Stat({ label, value, tone }: { label: string; value: string; tone?: "red" }) {
  return (
    <div className={card}>
      <p className="text-xs text-zinc-500">{label}</p>
      <p className={`mt-1 text-2xl font-semibold ${tone === "red" ? "text-red-600 dark:text-red-400" : ""}`}>{value}</p>
    </div>
  );
}
