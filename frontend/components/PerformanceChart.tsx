"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { fetchPerformance } from "@/lib/api";
import { fmtPct } from "@/lib/utils";

export default function PerformanceChart() {
  const q = useQuery({
    queryKey: ["performance"],
    queryFn: fetchPerformance,
    retry: false,
  });

  if (q.isPending) return <div className="skeleton h-80 w-full" />;
  if (q.isError || !q.data) {
    return (
      <p className="border border-rule bg-panel p-4 font-mono text-xs text-muted">
        performance series not available — run scripts/export_performance.py
      </p>
    );
  }
  const d = q.data;

  return (
    <div className="animate-fade-in">
      <div className="mb-4 flex flex-wrap gap-6 border border-rule bg-panel px-4 py-3">
        {[
          ["Sharpe (after costs)", d.sharpe?.toFixed(2) ?? "n/a", "text-bright"],
          ["Strategy ann.", fmtPct(d.ann_return), "text-gain"],
          ["Benchmark ann.", fmtPct(d.benchmark_ann_return), "text-muted"],
        ].map(([label, value, color]) => (
          <div key={label as string}>
            <div className="label-2xs">{label}</div>
            <div className={`font-mono text-lg tabular-nums ${color}`}>{value}</div>
          </div>
        ))}
      </div>

      <div className="border border-rule bg-panel p-3">
        <ResponsiveContainer width="100%" height={320}>
          <AreaChart data={d.points} margin={{ top: 6, right: 6, left: -14, bottom: 0 }}>
            <defs>
              <linearGradient id="strat" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#5B7CFF" stopOpacity={0.25} />
                <stop offset="100%" stopColor="#5B7CFF" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="#242C28" strokeDasharray="3 3" vertical={false} />
            <XAxis
              dataKey="date"
              tick={{ fill: "#7A8580", fontSize: 10, fontFamily: "var(--font-plex-mono)" }}
              tickLine={false}
              axisLine={{ stroke: "#242C28" }}
              minTickGap={48}
            />
            <YAxis
              tick={{ fill: "#7A8580", fontSize: 10, fontFamily: "var(--font-plex-mono)" }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v: number) => `${v.toFixed(1)}x`}
              domain={["auto", "auto"]}
            />
            <Tooltip
              contentStyle={{
                background: "#101513",
                border: "1px solid #242C28",
                fontFamily: "var(--font-plex-mono)",
                fontSize: 11,
              }}
              labelStyle={{ color: "#7A8580" }}
              formatter={(v: number, name: string) => [
                `${v.toFixed(3)}x`,
                name === "strategy_equity" ? "strategy" : "benchmark",
              ]}
            />
            <Area
              type="monotone"
              dataKey="benchmark_equity"
              stroke="#7A8580"
              strokeWidth={1}
              fill="none"
              dot={false}
            />
            <Area
              type="monotone"
              dataKey="strategy_equity"
              stroke="#5B7CFF"
              strokeWidth={1.5}
              fill="url(#strat)"
              dot={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <p className="mt-2 font-mono text-2xs text-muted">{d.note}</p>
    </div>
  );
}
