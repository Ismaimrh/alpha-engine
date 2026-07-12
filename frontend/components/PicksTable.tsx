"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import AlphaBar from "@/components/AlphaBar";
import RankDelta from "@/components/RankDelta";
import Sparkline from "@/components/Sparkline";
import {
  fetchFactors,
  fetchSparklines,
  fetchThesis,
  type Pick,
} from "@/lib/api";
import { cn, fmtPct, pnlColor } from "@/lib/utils";

const FACTOR_LABELS: [string, string][] = [
  ["momentum_composite", "Momentum"],
  ["valuation_composite", "Valuation"],
  ["quality_composite", "Quality"],
  ["insider_congress_composite", "Insider / Congress"],
];

const GRID =
  "grid grid-cols-[2rem_2.25rem_4rem_minmax(0,1fr)_6.5rem_8.5rem_4.5rem] items-center gap-2 max-md:grid-cols-[2rem_2.25rem_4rem_minmax(0,1fr)_4.5rem]";

function Detail({ ticker }: { ticker: string }) {
  const factors = useQuery({
    queryKey: ["factors", ticker],
    queryFn: () => fetchFactors(ticker),
    retry: false,
  });
  const thesis = useQuery({
    queryKey: ["thesis", ticker],
    queryFn: () => fetchThesis(ticker),
    retry: false,
  });

  return (
    <div className="grid animate-fade-in gap-5 border-t border-rule bg-panel px-3 py-4 md:grid-cols-[minmax(0,18rem)_1fr]">
      <div>
        <h3 className="label-2xs mb-2">Factor breakdown</h3>
        {factors.isPending && (
          <div className="space-y-2">
            {FACTOR_LABELS.map(([k]) => (
              <div key={k} className="skeleton h-4 w-full" />
            ))}
          </div>
        )}
        {factors.isError && (
          <p className="font-mono text-2xs text-loss">factor fetch failed</p>
        )}
        {factors.data &&
          FACTOR_LABELS.map(([key, label]) => (
            <div key={key} className="flex items-center justify-between gap-3 py-0.5">
              <span className="text-xs text-body">{label}</span>
              <AlphaBar
                value={
                  factors.data[key as keyof typeof factors.data] as
                    | number
                    | null
                }
              />
            </div>
          ))}
      </div>
      <div>
        <h3 className="label-2xs mb-2">
          Model thesis{" "}
          {thesis.data && (
            <span className="normal-case tracking-normal text-muted">
              · {thesis.data.model}
            </span>
          )}
        </h3>
        {thesis.isPending && (
          <div className="space-y-2">
            <div className="skeleton h-3 w-full" />
            <div className="skeleton h-3 w-11/12" />
            <div className="skeleton h-3 w-4/5" />
          </div>
        )}
        {thesis.isError && (
          <p className="text-xs text-muted">
            No thesis for this name yet — theses cover the top 10.
          </p>
        )}
        {thesis.data && (
          <p className="whitespace-pre-line text-xs leading-relaxed text-body">
            {thesis.data.thesis_text.replaceAll("**", "")}
          </p>
        )}
      </div>
    </div>
  );
}

export default function PicksTable({ picks }: { picks: Pick[] }) {
  const [open, setOpen] = useState<string | null>(null);
  const tickers = picks.map((p) => p.ticker);
  const sparks = useQuery({
    queryKey: ["sparklines", tickers.join(",")],
    queryFn: () => fetchSparklines(tickers),
    enabled: tickers.length > 0,
  });

  return (
    <div className="border border-rule bg-panel/40">
      <div className={cn(GRID, "border-b border-rule px-3 py-2")}>
        <span className="label-2xs">#</span>
        <span className="label-2xs">Δ</span>
        <span className="label-2xs">Tkr</span>
        <span className="label-2xs">Company</span>
        <span className="label-2xs max-md:hidden">90d</span>
        <span className="label-2xs max-md:hidden">Alpha (z)</span>
        <span className="label-2xs text-right">Exp 1mo</span>
      </div>

      {picks.map((p) => (
        <div key={p.ticker} className="border-b border-rule/60 last:border-b-0">
          <button
            onClick={() => setOpen(open === p.ticker ? null : p.ticker)}
            aria-expanded={open === p.ticker}
            className={cn(
              GRID,
              "w-full px-3 py-1.5 text-left transition-colors hover:bg-panel2 focus-visible:outline focus-visible:outline-1 focus-visible:outline-cobalt",
              open === p.ticker && "bg-panel2",
            )}
          >
            <span className="font-mono text-xs text-muted">{p.rank}</span>
            <RankDelta change={p.rank_change} />
            <span className="font-display text-sm font-semibold text-bright">
              {p.ticker}
            </span>
            <span className="truncate text-xs">
              {p.name}
              <span className="ml-2 hidden text-2xs text-muted lg:inline">
                {p.sector ?? ""}
              </span>
            </span>
            <span className="max-md:hidden">
              <Sparkline data={sparks.data?.series[p.ticker]} />
            </span>
            <span className="max-md:hidden">
              <AlphaBar value={p.alpha_score} width="w-20" />
            </span>
            <span
              className={cn(
                "text-right font-mono text-xs tabular-nums",
                pnlColor(p.predicted_return_30d),
              )}
            >
              {fmtPct(p.predicted_return_30d)}
            </span>
          </button>
          {open === p.ticker && <Detail ticker={p.ticker} />}
        </div>
      ))}
    </div>
  );
}
