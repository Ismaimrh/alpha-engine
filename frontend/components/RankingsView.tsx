"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import Link from "next/link";
import AlphaBar from "@/components/AlphaBar";
import { fetchRankings } from "@/lib/api";
import { cn, fmtPct, pnlColor } from "@/lib/utils";

const PAGE = 50;
const GRID =
  "grid grid-cols-[3rem_4.5rem_minmax(0,1fr)_8.5rem_4.5rem] items-center gap-2 max-md:grid-cols-[3rem_4.5rem_minmax(0,1fr)_4.5rem]";

export default function RankingsView() {
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [offset, setOffset] = useState(0);

  useEffect(() => {
    const t = setTimeout(() => {
      setDebounced(search.trim());
      setOffset(0);
    }, 250);
    return () => clearTimeout(t);
  }, [search]);

  const q = useQuery({
    queryKey: ["rankings", debounced, offset],
    queryFn: () => fetchRankings(offset, PAGE, debounced),
    placeholderData: (prev) => prev,
  });

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <label htmlFor="search" className="sr-only">Search ticker or company</label>
        <input
          id="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="search ticker or company…"
          className="w-64 border border-rule bg-panel px-3 py-1.5 font-mono text-xs text-bright placeholder:text-muted focus:border-cobalt focus:outline-none"
        />
        {q.data && (
          <span className="font-mono text-2xs text-muted">
            {q.data.total} names · {q.data.date}
          </span>
        )}
      </div>

      <div className="border border-rule bg-panel/40">
        <div className={cn(GRID, "border-b border-rule px-3 py-2")}>
          <span className="label-2xs">Rank</span>
          <span className="label-2xs">Tkr</span>
          <span className="label-2xs">Company</span>
          <span className="label-2xs max-md:hidden">Alpha (z)</span>
          <span className="label-2xs text-right">Exp 1mo</span>
        </div>

        {q.isPending && (
          <div className="space-y-1 p-3">
            {Array.from({ length: 10 }).map((_, i) => (
              <div key={i} className="skeleton h-6 w-full" />
            ))}
          </div>
        )}
        {q.isError && (
          <p className="p-4 font-mono text-xs text-loss">
            rankings fetch failed — is the API up?
          </p>
        )}
        {q.data && q.data.rows.length === 0 && (
          <p className="p-4 font-mono text-xs text-muted">
            no names match “{debounced}”
          </p>
        )}
        {q.data?.rows.map((r) => (
          <div
            key={r.ticker}
            className={cn(GRID, "border-b border-rule/60 px-3 py-1.5 last:border-b-0")}
          >
            <span className="font-mono text-xs text-muted">{r.rank}</span>
            <span className="font-display text-sm font-semibold text-bright">
              <Link href={`/stock/${r.ticker}`} className="hover:text-cobalt">{r.ticker}</Link>
            </span>
            <span className="truncate text-xs">
              {r.name}
              <span className="ml-2 hidden text-2xs text-muted lg:inline">
                {r.sector ?? ""}
              </span>
            </span>
            <span className="max-md:hidden">
              <AlphaBar value={r.alpha_score} width="w-20" />
            </span>
            <span
              className={cn(
                "text-right font-mono text-xs tabular-nums",
                pnlColor(r.predicted_return_30d),
              )}
            >
              {fmtPct(r.predicted_return_30d)}
            </span>
          </div>
        ))}
      </div>

      {q.data && !debounced && (
        <div className="mt-3 flex items-center gap-3">
          <button
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE))}
            className="tab-btn border border-rule text-muted hover:text-bright disabled:opacity-40"
          >
            ← prev
          </button>
          <span className="font-mono text-2xs text-muted">
            {offset + 1}–{Math.min(offset + PAGE, q.data.total)} of {q.data.total}
          </span>
          <button
            disabled={offset + PAGE >= q.data.total}
            onClick={() => setOffset(offset + PAGE)}
            className="tab-btn border border-rule text-muted hover:text-bright disabled:opacity-40"
          >
            next →
          </button>
        </div>
      )}
    </div>
  );
}
