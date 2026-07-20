"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import {
  fetchHitRate,
  fetchSignalLedger,
  fetchSignals,
  type SignalCardT,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const fmt = (v: number) => v.toFixed(2);
const pct = (v: number) => `${v >= 0 ? "+" : ""}${(v * 100).toFixed(1)}%`;

function HitRateHeader() {
  const q = useQuery({ queryKey: ["hitrate"], queryFn: fetchHitRate });
  if (q.isPending || !q.data) return <div className="skeleton mb-4 h-16 w-full" />;
  const h = q.data;
  return (
    <div className="mb-4 border border-rule bg-panel px-4 py-3">
      {h.state === "collecting" ? (
        <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1">
          <span className="font-mono text-xs uppercase text-warn">
            collecting track record
          </span>
          <span className="font-mono text-xs text-muted">
            {h.n_resolved}/30 resolved cards before the hit rate is shown —
            pre-registered rule, no early numbers
          </span>
        </div>
      ) : (
        <div className="flex flex-wrap items-baseline gap-x-8 gap-y-1">
          <div>
            <div className="label-2xs">Hit rate (close-touch)</div>
            <span className="font-mono text-2xl text-bright">
              {((h.hit_rate ?? 0) * 100).toFixed(1)}%
            </span>
            <span className="ml-2 font-mono text-2xs text-muted">
              95% CI {((h.wilson_low ?? 0) * 100).toFixed(0)}–
              {((h.wilson_high ?? 0) * 100).toFixed(0)}% · n={h.n_resolved}
            </span>
          </div>
          <div className="font-mono text-xs text-muted">
            {h.n_hit} hit · {h.n_stop} stopped · {h.n_expired} expired
            {h.avg_realized_return != null && (
              <> · avg {pct(h.avg_realized_return)}</>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function Card({ c }: { c: SignalCardT }) {
  const buy = c.direction === "BUY";
  // AVOID mechanics are mirrored in the resolver (hit = fall to downside
  // target, stopped by rallies). Display the MIRRORED levels so the card
  // reads in its own frame — showing the BUY-frame target above entry on
  // an AVOID card was misleading (spec v1.2 / review G1).
  const dTarget = buy ? c.target : c.entry - (c.target - c.entry);
  const dStop = buy ? c.stop : c.entry + (c.entry - c.stop);
  const lo = Math.min(dTarget, dStop);
  const hi = Math.max(dTarget, dStop);
  const pos = Math.min(1, Math.max(0, (c.entry - lo) / (hi - lo)));
  return (
    <div className="border border-rule bg-panel">
      <div className="flex items-baseline justify-between border-b border-rule px-3 py-2">
        <span className="font-mono text-sm font-semibold text-bright">
          {c.ticker}
        </span>
        <span
          className={cn(
            "border px-1.5 py-0.5 font-mono text-2xs",
            buy ? "border-gain/40 text-gain" : "border-loss/40 text-loss",
          )}
        >
          {c.direction}
        </span>
      </div>
      <div className="px-3 py-2 font-mono text-xs">
        <div className="mb-1.5 flex justify-between text-2xs text-muted">
          <span>{buy ? `stop ${fmt(dStop)}` : `target ${fmt(dTarget)}`}</span>
          <span>entry {fmt(c.entry)}</span>
          <span>{buy ? `target ${fmt(dTarget)}` : `stop ${fmt(dStop)}`}</span>
        </div>
        <div className="relative h-1.5 w-full bg-track">
          <div
            className="absolute top-0 h-1.5 w-0.5 bg-bright"
            style={{ left: `${pos * 100}%` }}
          />
          <div className={`absolute left-0 top-0 h-1.5 w-[2px] ${buy ? "bg-loss" : "bg-gain"}`} />
          <div className={`absolute right-0 top-0 h-1.5 w-[2px] ${buy ? "bg-gain" : "bg-loss"}`} />
        </div>
        <div className="mt-2 flex justify-between text-2xs text-muted">
          <span>α {c.alpha_score >= 0 ? "+" : ""}{c.alpha_score.toFixed(2)}</span>
          <span>σ₂₁ {(c.sigma_21 * 100).toFixed(1)}%</span>
          <span>{c.horizon_days}d · {c.issue_date}</span>
        </div>
        {!buy && (
          <p className="mt-1 text-2xs text-muted">
            avoid / underweight — not a short recommendation
          </p>
        )}
      </div>
    </div>
  );
}

function Ledger() {
  const [offset, setOffset] = useState(0);
  const limit = 25;
  const q = useQuery({
    queryKey: ["ledger", offset],
    queryFn: () => fetchSignalLedger(offset, limit),
  });
  if (q.isPending || !q.data) return <div className="skeleton h-40 w-full" />;
  const d = q.data;
  if (d.total === 0)
    return (
      <p className="font-mono text-2xs text-muted">
        ledger empty — first resolutions land ~21 trading days after the first
        issued cards
      </p>
    );
  const STATUS_STYLE: Record<string, string> = {
    hit: "text-gain",
    stop: "text-loss",
    expired: "text-muted",
  };
  return (
    <div>
      <table className="w-full font-mono text-xs">
        <thead>
          <tr className="label-2xs text-left">
            <th className="py-1">tkr</th>
            <th>dir</th>
            <th>issued</th>
            <th>resolved</th>
            <th>status</th>
            <th className="text-right">return</th>
          </tr>
        </thead>
        <tbody>
          {d.cards.map((c, i) => (
            <tr key={`${c.ticker}-${c.issue_date}-${i}`} className="border-t border-rule">
              <td className="py-1 text-bright">{c.ticker}</td>
              <td>{c.direction}</td>
              <td className="text-muted">{c.issue_date}</td>
              <td className="text-muted">{c.resolved_date ?? "—"}</td>
              <td className={STATUS_STYLE[c.status] ?? ""}>{c.status}</td>
              <td className={cn("text-right",
                (c.realized_return ?? 0) >= 0 ? "text-gain" : "text-loss")}>
                {c.realized_return != null ? pct(c.realized_return) : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-2 flex items-center gap-3 font-mono text-2xs text-muted">
        <button
          disabled={offset === 0}
          onClick={() => setOffset(Math.max(0, offset - limit))}
          className="border border-rule px-2 py-0.5 disabled:opacity-40"
        >
          prev
        </button>
        <span>
          {offset + 1}–{Math.min(offset + limit, d.total)} of {d.total}
        </span>
        <button
          disabled={offset + limit >= d.total}
          onClick={() => setOffset(offset + limit)}
          className="border border-rule px-2 py-0.5 disabled:opacity-40"
        >
          next
        </button>
      </div>
    </div>
  );
}

export default function SignalsView() {
  const q = useQuery({ queryKey: ["signals"], queryFn: fetchSignals });

  return (
    <div className="animate-fade-in">
      <HitRateHeader />
      {q.isPending ? (
        <div className="grid gap-3 md:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="skeleton h-36 w-full" />
          ))}
        </div>
      ) : q.isError || !q.data ? (
        <p className="border border-rule bg-panel p-4 font-mono text-xs text-muted">
          signals unavailable — is the API up?
        </p>
      ) : q.data.open_cards.length === 0 ? (
        <p className="border border-rule bg-panel p-4 font-mono text-xs text-muted">
          no open cards — cards issue nightly when names cross ±1.0σ alpha
        </p>
      ) : (
        <>
          <p className="mb-2 font-mono text-2xs text-muted">
            {q.data.open_cards.length} open · {q.data.note.toLowerCase()}{" "}
            · entry = issue-day close; next-day fills differ (overnight gap
            risk is the reader&apos;s)
          </p>
          <div className="grid gap-3 md:grid-cols-3 lg:grid-cols-4">
            {q.data.open_cards.map((c) => (
              <Card key={`${c.ticker}-${c.issue_date}`} c={c} />
            ))}
          </div>
        </>
      )}
      <div className="mt-6">
        <div className="label-2xs mb-2">Resolved ledger (append-only)</div>
        <Ledger />
      </div>
    </div>
  );
}
