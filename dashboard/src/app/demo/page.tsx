"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { PublicOverview, inr, istTime } from "@/lib/api";
import { AiChip, OUTCOME_LABEL, OUTCOME_STYLE, Stat, card, isAi } from "@/components/ui";

const REPO = "https://github.com/durgaanuhya02/AgentGuard";

export default function PublicDemo() {
  const [data, setData] = useState<PublicOverview | null>(null);
  const [state, setState] = useState<"loading" | "ok" | "off" | "error">("loading");

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const res = await fetch("/api/v1/public/overview", { cache: "no-store" });
        if (!alive) return;
        if (res.status === 404) return setState("off");
        if (!res.ok) return setState("error");
        setData(await res.json());
        setState("ok");
      } catch {
        if (alive) setState("error");
      }
    };
    load();
    const t = setInterval(load, 5000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  const totals = (data?.agents ?? []).reduce(
    (t, a) => ({
      actions: t.actions + Object.values(a.actions_today).reduce((s, n) => s + (n ?? 0), 0),
      stopped: t.stopped + (a.actions_today.deny ?? 0) + (a.actions_today.frozen ?? 0),
      money: t.money + a.blocked_amount_today_inr,
      spend: t.spend + a.spent_today_inr,
    }),
    { actions: 0, stopped: 0, money: 0, spend: 0 },
  );

  return (
    <main className="mx-auto max-w-6xl space-y-6 p-4 sm:p-8">
      <header className="space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h1 className="text-2xl font-semibold tracking-tight">AgentGuard · live demo</h1>
          <div className="flex gap-3 text-sm">
            <a className="text-blue-600 hover:underline" href={REPO}>
              Code on GitHub
            </a>
            <Link className="text-blue-600 hover:underline" href="/">
              Admin sign-in
            </Link>
          </div>
        </div>
        <p className="max-w-3xl text-sm text-zinc-600 dark:text-zinc-400">
          A read-only view of a running AgentGuard. A scripted support agent handled refunds through it: honest
          refunds went through, an intern&apos;s agent was stopped from doing what the intern can&apos;t, a
          prompt-injected refund and a large refund were sent to a human, and a refund loop got the agent frozen.
          Everything below is live data from the API; nothing here can be changed.
        </p>
        <p className="text-xs text-zinc-500">
          Hosted on free tiers: the first load can take about a minute while the API wakes up, and data resets when
          it restarts. The AI model runs only locally, so here the intent check runs in rules-only mode.
        </p>
      </header>

      {state === "loading" && <p className="text-sm text-zinc-500">Waking up the API… this can take up to a minute.</p>}
      {state === "off" && <p className="text-sm text-zinc-500">The public demo isn&apos;t enabled on this deployment.</p>}
      {state === "error" && <p className="text-sm text-red-600">Couldn&apos;t reach the API. Retrying every 5 seconds…</p>}

      {data && (
        <>
          <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label="Agent actions today" value={String(totals.actions)} />
            <Stat label="Actions stopped" value={String(totals.stopped)} tone="red" />
            <Stat label="Money in stopped actions" value={inr(totals.money)} tone="red" />
            <Stat label="Agent spend today" value={inr(totals.spend)} />
          </section>

          <section>
            <h2 className="mb-3 text-lg font-semibold">Agents</h2>
            <div className="grid gap-3 md:grid-cols-2">
              {data.agents.map((a) => {
                const pct = Math.min(100, (a.spent_today_inr / a.daily_budget_inr) * 100);
                return (
                  <div key={a.id} className={`${card} ${a.frozen ? "border-violet-400 dark:border-violet-700" : ""}`}>
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <p className="font-mono font-medium">{a.id}</p>
                        <p className="text-sm text-zinc-500">acts on behalf of {a.on_behalf_of}</p>
                      </div>
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs font-medium ${a.frozen ? OUTCOME_STYLE.frozen : OUTCOME_STYLE.allow}`}
                      >
                        {a.frozen ? "Frozen" : "Active"}
                      </span>
                    </div>
                    {a.frozen && (
                      <p className="mt-3 rounded-md bg-violet-50 p-2 text-sm text-violet-900 dark:bg-violet-950 dark:text-violet-200">
                        {a.frozen.reason}
                      </p>
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
                  </div>
                );
              })}
            </div>
          </section>

          <section>
            <h2 className="mb-3 text-lg font-semibold">Waiting for a human ({data.approvals.length})</h2>
            {data.approvals.length === 0 ? (
              <p className="text-sm text-zinc-500">Nothing waiting.</p>
            ) : (
              <div className="space-y-2">
                {data.approvals.map((p) => (
                  <div key={p.id} className={`${card} space-y-1.5 text-sm`}>
                    <p>
                      <span className="font-mono">{p.agent_id}</span> wants to <b>{p.tool}</b>{" "}
                      {p.amount_inr > 0 && <b>{inr(p.amount_inr)}</b>}
                      <span className="text-zinc-500"> · for {p.on_behalf_of} · {istTime(p.created_at)}</span>
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
                ))}
              </div>
            )}
          </section>

          <section>
            <h2 className="mb-3 text-lg font-semibold">Audit trail</h2>
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
                  {data.audit.length === 0 && (
                    <tr>
                      <td colSpan={7} className="px-3 py-6 text-center text-zinc-500">
                        No agent activity yet (the data resets when the free API restarts).
                      </td>
                    </tr>
                  )}
                  {data.audit.map((e) => (
                    <tr key={e.id} className="border-b border-zinc-100 last:border-0 dark:border-zinc-800/60">
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
        </>
      )}
    </main>
  );
}
