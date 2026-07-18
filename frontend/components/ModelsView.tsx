"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchModels } from "@/lib/api";
import { cn } from "@/lib/utils";

const ROLE_STYLE: Record<string, string> = {
  champion: "text-gain border-gain/40",
  candidate: "text-warn border-warn/40",
  challenger: "text-cobalt border-cobalt/40",
};

export default function ModelsView() {
  const q = useQuery({ queryKey: ["models"], queryFn: fetchModels });

  if (q.isPending)
    return (
      <div className="grid gap-3 md:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <div key={i} className="skeleton h-72 w-full" />
        ))}
      </div>
    );
  if (q.isError || !q.data)
    return (
      <p className="border border-rule bg-panel p-4 font-mono text-xs text-muted">
        model race unavailable — is the API up?
      </p>
    );
  const d = q.data;

  return (
    <div className="animate-fade-in">
      <p className="mb-3 font-mono text-2xs text-muted">
        three prediction streams · {d.date} · {d.note.toLowerCase()}
      </p>

      <div className="grid gap-3 md:grid-cols-3">
        {d.models.map((m) => (
          <div key={m.model_version} className="border border-rule bg-panel">
            <div className="flex items-baseline justify-between border-b border-rule px-3 py-2">
              <span className="font-mono text-xs text-bright">
                {m.model_version}
              </span>
              <span
                className={cn(
                  "border px-1.5 py-0.5 font-mono text-2xs uppercase",
                  ROLE_STYLE[m.role],
                )}
              >
                {m.role}
              </span>
            </div>

            <div className="px-3 py-2">
              <div className="label-2xs mb-1">Top 10 today</div>
              {m.top10.map((p) => (
                <div
                  key={p.ticker}
                  className="flex justify-between py-0.5 font-mono text-xs"
                >
                  <span>
                    <span className="mr-2 text-muted">{p.rank}</span>
                    <span className="text-bright">{p.ticker}</span>
                  </span>
                  <span className={p.alpha_score >= 0 ? "text-gain" : "text-loss"}>
                    {p.alpha_score >= 0 ? "+" : ""}
                    {p.alpha_score.toFixed(2)}
                  </span>
                </div>
              ))}
            </div>

            <div className="border-t border-rule px-3 py-2">
              <div className="label-2xs mb-1">Realized IC (live)</div>
              {m.realized ? (
                <div className="font-mono text-xs">
                  <span className="text-bright">
                    {m.realized.mean_ic?.toFixed(4)}
                  </span>
                  <span className="ml-2 text-muted">
                    t={m.realized.t_stat} · {m.realized.n_days}d · hit{" "}
                    {((m.realized.hit_rate ?? 0) * 100).toFixed(0)}%
                  </span>
                </div>
              ) : (
                <p className="font-mono text-2xs text-muted">
                  pending — first outcomes resolve 21 trading days after each
                  prediction
                </p>
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="mt-4 border border-rule bg-panel px-3 py-2">
        <div className="label-2xs mb-1">Top-50 book overlap</div>
        <div className="flex flex-wrap gap-x-6 gap-y-1 font-mono text-2xs text-body">
          {Object.entries(d.overlap_top50).map(([pair, frac]) => (
            <span key={pair}>
              {pair.replaceAll("champion-momentum-v1", "champion")
                .replaceAll("cand-sector-momentum-v1", "sector-cand")
                .replaceAll("lgbm-v1-momentum-insider-valuation", "lgbm")}{" "}
              <span className="text-bright">{(frac * 100).toFixed(0)}%</span>
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
