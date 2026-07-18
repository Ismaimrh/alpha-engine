"use client";

import { useQuery } from "@tanstack/react-query";
import AlphaBar from "@/components/AlphaBar";
import { fetchSectors } from "@/lib/api";

export default function SectorStrip() {
  const q = useQuery({ queryKey: ["sectors"], queryFn: fetchSectors });
  if (q.isPending) return <div className="skeleton mb-3 h-24 w-full" />;
  if (q.isError || !q.data) return null; // strip is optional garnish

  return (
    <div className="mb-4 border border-rule bg-panel px-3 py-2">
      <div className="label-2xs mb-1.5">Mean alpha by sector</div>
      <div className="grid gap-x-6 gap-y-0.5 sm:grid-cols-2 lg:grid-cols-3">
        {q.data.sectors.map((s) => (
          <div key={s.sector} className="flex items-center justify-between gap-2">
            <span className="truncate text-xs">
              {s.sector}
              <span className="ml-1.5 font-mono text-2xs text-muted">
                {s.n} · top {s.top_ticker}
              </span>
            </span>
            <AlphaBar value={s.mean_alpha} width="w-16" max={1} />
          </div>
        ))}
      </div>
    </div>
  );
}
