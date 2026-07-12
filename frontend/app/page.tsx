"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import PerformanceChart from "@/components/PerformanceChart";
import PicksTable from "@/components/PicksTable";
import RankingsView from "@/components/RankingsView";
import SubscribeBox from "@/components/SubscribeBox";
import { fetchPicks, fetchStats } from "@/lib/api";
import { cn } from "@/lib/utils";

type Tab = "picks" | "ranking" | "performance";

const TABS: { id: Tab; label: string }[] = [
  { id: "picks", label: "Top Picks" },
  { id: "ranking", label: "Full Ranking" },
  { id: "performance", label: "Performance" },
];

export default function Home() {
  const [tab, setTab] = useState<Tab>("picks");
  const picks = useQuery({ queryKey: ["picks"], queryFn: () => fetchPicks(20) });
  const stats = useQuery({ queryKey: ["stats"], queryFn: fetchStats });

  return (
    <main className="mx-auto max-w-5xl px-4 py-8 md:py-12">
      {/* Masthead */}
      <header className="mb-6">
        <div className="flex flex-wrap items-baseline justify-between gap-4">
          <div>
            <p className="label-2xs mb-1">Daily factor rankings · S&amp;P 500</p>
            <h1 className="font-display text-3xl font-bold tracking-tight text-bright">
              Alpha Engine
            </h1>
          </div>
          <SubscribeBox />
        </div>

        {/* Status line */}
        <div className="mt-4 flex flex-wrap gap-x-6 gap-y-1 border-y border-rule py-2 font-mono text-2xs text-muted">
          <span>
            data{" "}
            <span className="text-body">
              {picks.data?.date ?? (picks.isPending ? "…" : "offline")}
            </span>
          </span>
          <span>
            universe{" "}
            <span className="text-body">
              {stats.data?.companies_in_universe ?? "—"}
            </span>
          </span>
          <span>
            model{" "}
            <span className="text-body">
              {picks.data?.model_version ?? "—"}
            </span>
          </span>
          <span className="ml-auto hidden md:inline">
            challenger tracked · promotion is data-driven
          </span>
        </div>
      </header>

      {/* Tabs */}
      <nav className="mb-4 flex gap-1 border border-rule bg-panel p-1" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => setTab(t.id)}
            className={cn(
              "tab-btn",
              tab === t.id
                ? "bg-panel2 text-bright"
                : "text-muted hover:text-body",
            )}
          >
            {t.label}
          </button>
        ))}
      </nav>

      {/* Views */}
      {tab === "picks" && (
        <>
          {picks.isPending && (
            <div className="space-y-1">
              {Array.from({ length: 12 }).map((_, i) => (
                <div key={i} className="skeleton h-7 w-full" />
              ))}
            </div>
          )}
          {picks.isError && (
            <div className="border border-rule bg-panel p-6 text-center font-mono text-xs text-muted">
              API unreachable — start it (uvicorn app.main:app) or check
              NEXT_PUBLIC_API_URL, then reload.
            </div>
          )}
          {picks.data && <PicksTable picks={picks.data.picks} />}
        </>
      )}
      {tab === "ranking" && <RankingsView />}
      {tab === "performance" && <PerformanceChart />}

      {/* Methodology + disclaimer */}
      <section className="mt-10 border-t border-rule pt-5 text-xs leading-relaxed text-muted">
        <h2 className="mb-2 font-display text-sm font-semibold text-body">
          How the ranking works
        </h2>
        <p>
          Three factor families are computed nightly from public data:
          momentum (12-1 month return, RSI, MACD), valuation (value and
          quality composites), and smart money (SEC Form 4 insider filings
          plus Senate disclosures). Scores are z-scored across the universe
          daily; the live model ranks by the momentum composite, validated
          walk-forward with purge gaps and after transaction costs. A
          machine-learned ensemble runs in parallel as a challenger and is
          promoted only if it wins on realized predictions.
        </p>
        <p className="mt-3 border-l-2 border-rule pl-3 font-mono text-2xs">
          {picks.data?.disclaimer ??
            "Backtested signals, not financial advice. Past performance does not guarantee future results."}
        </p>
      </section>
    </main>
  );
}
