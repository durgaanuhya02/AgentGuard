"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Agent,
  ApiError,
  Approval,
  IncidentReport,
  AuditEvent,
  Me,
  api,
  inr,
  istTime,
  setDevUser,
} from "@/lib/api";
import { AiChip, OUTCOME_LABEL, OUTCOME_STYLE, Stat, argsLabel, btn, card, isAi } from "@/components/ui";

const DEV_USERS = [
  { id: "meera", label: "Meera (admin)" },
  { id: "priya", label: "Priya (support)" },
  { id: "arjun", label: "Arjun (intern)" },
];

export default function Dashboard() {
  const [devUser, setDevUserState] = useState<string>("meera");
  const [me, setMe] = useState<Me | null>(null);
  const [needsLogin, setNeedsLogin] = useState(false);
  const router = useRouter();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [newKey, setNewKey] = useState<{ agent: string; key: string } | null>(null);
  // Incident copilot results per agent: "loading", a report, or an error message.
  const [reports, setReports] = useState<Record<string, IncidentReport | "loading" | { error: string }>>({});

  const explainAgent = async (agentId: string) => {
    setReports((r) => ({ ...r, [agentId]: "loading" }));
    try {
      const rep = await api<IncidentReport>(`/v1/agents/${agentId}/explain`, { method: "POST" });
      setReports((r) => ({ ...r, [agentId]: rep }));
    } catch (err) {
      setReports((r) => ({ ...r, [agentId]: { error: err instanceof Error ? err.message : String(err) } }));
    }
  };
  const seen = useRef<Set<number>>(new Set());
  const [fresh, setFresh] = useState<Set<number>>(new Set());

  // Remember the demo user between reloads (dev mode only).
  useEffect(() => {
    try {
      const saved = localStorage.getItem("agentguard.devUser");
      if (saved) setDevUserState(saved);
    } catch {}
  }, []);

  const refresh = useCallback(async () => {
    try {
      const [m, a, e, p] = await Promise.all([
        api<Me>("/me"),
        api<Agent[]>("/v1/agents"),
        api<AuditEvent[]>("/v1/audit?limit=100"),
        api<Approval[]>("/v1/approvals"),
      ]);
      setMe(m);
      setAgents(a);
      setApprovals(p);
      const newIds = e.filter((x) => !seen.current.has(x.id)).map((x) => x.id);
      if (seen.current.size > 0) setFresh(new Set(newIds));
      newIds.forEach((id) => seen.current.add(id));
      setAudit(e);
      setError(null);
      setNeedsLogin(false);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401 && err.message.includes("/auth/login")) {
        setNeedsLogin(true);
      } else {
        setError(err instanceof Error ? err.message : String(err));
      }
    }
  }, []);

  useEffect(() => {
    setDevUser(devUser);
    try {
      localStorage.setItem("agentguard.devUser", devUser);
    } catch {}
    refresh();
    const t = setInterval(refresh, 2000);
    return () => clearInterval(t);
  }, [devUser, refresh]);

  const act = async (fn: () => Promise<unknown>) => {
    try {
      await fn();
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const isAdmin = me?.role === "admin";
  const totals = agents.reduce(
    (t, a) => ({
      actions: t.actions + Object.values(a.actions_today).reduce((s, n) => s + (n ?? 0), 0),
      stopped: t.stopped + (a.actions_today.deny ?? 0) + (a.actions_today.frozen ?? 0),
      money: t.money + a.blocked_amount_today_inr,
      spend: t.spend + a.spent_today_inr,
    }),
    { actions: 0, stopped: 0, money: 0, spend: 0 },
  );

  // Visitors who aren't signed in go straight to the public read-only demo.
  useEffect(() => {
    if (needsLogin) router.replace("/demo");
  }, [needsLogin, router]);

  if (needsLogin) {
    return (
      <main className="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center gap-4 p-6 text-center">
        <h1 className="text-2xl font-semibold">AgentGuard</h1>
        <p className="text-zinc-500">
          Identity, spending caps and anomaly detection for AI agents, so every agent action is tied to a human,
          capped in cost, and stoppable.
        </p>
        <Link href="/demo" className={`${btn} bg-zinc-900 text-white dark:bg-white dark:text-zinc-900`}>
          View the live demo (no sign-in)
        </Link>
        <a href="/api/auth/login" className="text-sm text-zinc-500 underline hover:text-zinc-700">
          Admin? Sign in with WorkOS
        </a>
        <a href="https://github.com/durgaanuhya02/AgentGuard" className="text-sm text-blue-600 hover:underline">
          Code on GitHub
        </a>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-6xl space-y-6 p-4 sm:p-8">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">AgentGuard</h1>
          <p className="text-sm text-zinc-500">Every agent action tied to a human, capped in cost, and stoppable.</p>
        </div>
        {me?.auth === "workos" ? (
          <div className="flex items-center gap-3 text-sm">
            <span>
              <span className="text-zinc-500">Signed in as </span>
              <b>{me.name}</b> <span className="text-zinc-500">({me.role})</span>
              {me.email && <span className="block text-xs text-zinc-500">{me.email} · via WorkOS</span>}
            </span>
            <a href="/api/auth/logout" className={`${btn} bg-zinc-200 hover:bg-zinc-300 dark:bg-zinc-800 dark:hover:bg-zinc-700`}>
              Sign out
            </a>
          </div>
        ) : (
        <label className="flex items-center gap-2 text-sm">
          <span className="text-zinc-500">Acting as</span>
          <select
            value={devUser}
            onChange={(e) => setDevUserState(e.target.value)}
            className="rounded-md border border-zinc-300 bg-white px-2 py-1.5 dark:border-zinc-700 dark:bg-zinc-900"
          >
            {DEV_USERS.map((u) => (
              <option key={u.id} value={u.id}>
                {u.label}
              </option>
            ))}
          </select>
        </label>
        )}
      </header>

      {error && (
        <div className="rounded-lg border border-red-300 bg-red-50 px-4 py-2 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
          {error}
          {error.includes("fetch") || error.includes("Internal") ? " (is the API running on port 8000?)" : ""}
        </div>
      )}

      <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Agent actions today" value={String(totals.actions)} />
        <Stat label="Actions stopped" value={String(totals.stopped)} tone="red" />
        <Stat label="Money in stopped actions" value={inr(totals.money)} tone="red" />
        <Stat label="Agent spend today" value={inr(totals.spend)} />
      </section>

      {newKey && (
        <div className={`${card} border-amber-300 dark:border-amber-800`}>
          <p className="text-sm font-medium">New key for {newKey.agent}. Copy it now, it won&apos;t be shown again:</p>
          <code className="mt-2 block break-all rounded bg-zinc-100 p-2 font-mono text-sm dark:bg-zinc-800">
            {newKey.key}
          </code>
          <button className={`${btn} mt-2 bg-zinc-200 dark:bg-zinc-800`} onClick={() => setNewKey(null)}>
            Done
          </button>
        </div>
      )}

      <section>
        <h2 className="mb-3 text-lg font-semibold">Agents</h2>
        <div className="grid gap-3 md:grid-cols-2">
          {agents.map((a) => {
            const pct = Math.min(100, (a.spent_today_inr / a.daily_budget_inr) * 100);
            return (
              <div key={a.id} className={`${card} ${a.frozen ? "border-violet-400 dark:border-violet-700" : ""}`}>
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="font-mono font-medium">{a.id}</p>
                    <p className="text-sm text-zinc-500">acts on behalf of {a.on_behalf_of}</p>
                  </div>
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                      a.frozen ? OUTCOME_STYLE.frozen : OUTCOME_STYLE.allow
                    }`}
                  >
                    {a.frozen ? "Frozen" : "Active"}
                  </span>
                </div>

                {a.frozen && (
                  <div className="mt-3 rounded-md bg-violet-50 p-2 text-sm text-violet-900 dark:bg-violet-950 dark:text-violet-200">
                    {a.frozen.reason}
                    {isAdmin && (
                      <button
                        className={`${btn} mt-2 block bg-violet-600 text-white hover:bg-violet-700`}
                        onClick={() => act(() => api(`/v1/agents/${a.id}/unfreeze`, { method: "POST" }))}
                      >
                        Review done, unfreeze
                      </button>
                    )}
                  </div>
                )}

                <div className="mt-3">
                  <div className="flex justify-between text-xs text-zinc-500">
                    <span>Spend today</span>
                    <span>
                      {inr(a.spent_today_inr)} / {inr(a.daily_budget_inr)}
                    </span>
                  </div>
                  <div className="mt-1 h-2 rounded-full bg-zinc-200 dark:bg-zinc-800">
                    <div
                      className={`h-2 rounded-full ${pct > 80 ? "bg-red-500" : "bg-emerald-500"}`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>

                <p className="mt-3 text-xs text-zinc-500">
                  Can use: {a.effective_tools.length ? a.effective_tools.join(", ") : "nothing"}
                </p>
                <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
                  <span className="text-zinc-500">Keys:</span>
                  {a.keys.length === 0 && <span className="text-zinc-400">none</span>}
                  {a.keys.map((k) => (
                    <span key={k} className="flex items-center gap-1 rounded bg-zinc-100 px-1.5 py-0.5 font-mono dark:bg-zinc-800">
                      agk_{k}_…
                      {isAdmin && (
                        <button
                          title="Revoke this key"
                          className="cursor-pointer text-red-600 hover:text-red-800"
                          onClick={() => act(() => api(`/v1/keys/${k}`, { method: "DELETE" }))}
                        >
                          ×
                        </button>
                      )}
                    </span>
                  ))}
                  {isAdmin && (
                    <button
                      className="cursor-pointer text-blue-600 hover:underline"
                      onClick={() =>
                        act(async () => {
                          const k = await api<{ key: string }>(`/v1/agents/${a.id}/keys`, { method: "POST" });
                          setNewKey({ agent: a.id, key: k.key });
                        })
                      }
                    >
                      + new key
                    </button>
                  )}
                </div>

                <div className="mt-3 border-t border-zinc-100 pt-3 dark:border-zinc-800">
                  <button
                    className={`${btn} ${a.frozen ? "bg-sky-600 text-white hover:bg-sky-700" : "bg-zinc-100 hover:bg-zinc-200 dark:bg-zinc-800 dark:hover:bg-zinc-700"}`}
                    disabled={reports[a.id] === "loading"}
                    onClick={() => explainAgent(a.id)}
                  >
                    {reports[a.id] === "loading" ? "AI is reading the audit trail…" : "Explain with AI"}
                  </button>
                  <IncidentPanel report={reports[a.id]} />
                </div>
              </div>
            );
          })}
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold">
          Waiting for approval {approvals.length > 0 && <span className="text-amber-600">({approvals.length})</span>}
        </h2>
        {approvals.length === 0 ? (
          <p className="text-sm text-zinc-500">Nothing waiting.</p>
        ) : (
          <div className="space-y-2">
            {approvals.map((p) => (
              <div key={p.id} className={`${card} flex flex-wrap items-start justify-between gap-3`}>
                <div className="min-w-0 flex-1 space-y-1.5 text-sm">
                  <p>
                    <span className="font-mono">{p.agent_id}</span> wants to <b>{p.tool}</b>{" "}
                    {p.amount_inr > 0 && <b>{inr(p.amount_inr)}</b>}
                    {argsLabel(p.args_json) && <span className="font-mono text-xs"> {argsLabel(p.args_json)}</span>}
                    <span className="text-zinc-500">
                      {" "}
                      · for {p.on_behalf_of} · {istTime(p.created_at)}
                    </span>
                  </p>
                  {p.reason && (
                    <p className="flex items-start gap-1.5 text-zinc-700 dark:text-zinc-300">
                      {isAi(p.reason) && <AiChip />}
                      <span>{p.reason}</span>
                    </p>
                  )}
                  {p.intent && (
                    <blockquote className="border-l-2 border-zinc-300 pl-2 text-xs text-zinc-500 dark:border-zinc-700">
                      Customer asked: &ldquo;{p.intent}&rdquo;
                    </blockquote>
                  )}
                </div>
                <div className="flex gap-2">
                  <button
                    className={`${btn} bg-emerald-600 text-white hover:bg-emerald-700`}
                    onClick={() => act(() => api(`/v1/approvals/${p.id}`, { method: "POST", body: JSON.stringify({ approve: true }) }))}
                  >
                    Approve
                  </button>
                  <button
                    className={`${btn} bg-zinc-200 hover:bg-zinc-300 dark:bg-zinc-800 dark:hover:bg-zinc-700`}
                    onClick={() => act(() => api(`/v1/approvals/${p.id}`, { method: "POST", body: JSON.stringify({ approve: false }) }))}
                  >
                    Reject
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold">Live audit trail</h2>
        <div className={`${card} overflow-x-auto p-0`}>
          <table className="w-full text-left text-sm">
            <thead className="border-b border-zinc-200 text-xs text-zinc-500 dark:border-zinc-800">
              <tr>
                <th className="px-3 py-2 font-medium">Time (IST)</th>
                <th className="px-3 py-2 font-medium">Agent</th>
                <th className="px-3 py-2 font-medium">For</th>
                <th className="px-3 py-2 font-medium">Tool</th>
                <th className="px-3 py-2 text-right font-medium">Amount</th>
                <th className="px-3 py-2 font-medium">Decision</th>
                <th className="px-3 py-2 font-medium">Why</th>
              </tr>
            </thead>
            <tbody>
              {audit.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-3 py-6 text-center text-zinc-500">
                    No agent activity yet. Run <code className="font-mono">python demo/simulate_traffic.py</code>
                  </td>
                </tr>
              )}
              {audit.map((e) => (
                <tr
                  key={e.id}
                  className={`border-b border-zinc-100 last:border-0 dark:border-zinc-800/60 ${fresh.has(e.id) ? "row-new" : ""}`}
                >
                  <td className="whitespace-nowrap px-3 py-2 font-mono text-xs">{istTime(e.at)}</td>
                  <td className="whitespace-nowrap px-3 py-2 font-mono text-xs">{e.agent_id}</td>
                  <td className="px-3 py-2">{e.on_behalf_of ?? "—"}</td>
                  <td className="whitespace-nowrap px-3 py-2">{e.tool}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-right">{e.amount_inr ? inr(e.amount_inr) : ""}</td>
                  <td className="px-3 py-2">
                    <span className={`whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ${OUTCOME_STYLE[e.outcome]}`}>
                      {OUTCOME_LABEL[e.outcome]}
                    </span>
                  </td>
                  <td className="min-w-64 px-3 py-2 text-zinc-600 dark:text-zinc-400">
                    <span className="flex items-start gap-1.5">
                      {isAi(e.reason) && <AiChip />}
                      <span>{e.reason}</span>
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}

const RISK_STYLE = {
  low: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
  medium: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
  high: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
};

function IncidentPanel({ report }: { report: IncidentReport | "loading" | { error: string } | undefined }) {
  if (!report || report === "loading") return null;
  if ("error" in report) return <p className="mt-2 text-sm text-red-600">{report.error}</p>;
  const { facts, explanation: ex } = report;
  return (
    <div className="mt-3 space-y-2 rounded-lg bg-sky-50 p-3 text-sm dark:bg-sky-950/40">
      <div className="flex flex-wrap items-center gap-2">
        {ex.source === "ai" && <AiChip />}
        <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${RISK_STYLE[ex.risk]}`}>{ex.risk} risk</span>
        <span className="text-xs text-zinc-500">
          {facts.actions} actions in {facts.window_hours.toFixed(0)} h · {inr(facts.money_moved_inr)} moved ·{" "}
          {inr(facts.money_stopped_or_held_inr)} stopped or held
        </span>
      </div>
      <p>{ex.summary}</p>
      {ex.likely_cause && (
        <p>
          <b>Likely cause:</b> {ex.likely_cause}
        </p>
      )}
      {ex.recommended_actions.length > 0 && (
        <ul className="list-disc pl-5">
          {ex.recommended_actions.map((x, i) => (
            <li key={i}>{x}</li>
          ))}
        </ul>
      )}
      <p className="text-xs text-zinc-500">
        {ex.source === "ai"
          ? "Written by AI from facts computed by AgentGuard. Numbers above come from the audit trail, not the AI."
          : ex.note ?? "Rule-based summary."}
      </p>
    </div>
  );
}
