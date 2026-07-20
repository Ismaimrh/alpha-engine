"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  Area,
  AreaChart,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import AlphaBar from "@/components/AlphaBar";
import Providers from "@/components/Providers";
import { fetchStock } from "@/lib/api";
import { cn } from "@/lib/utils";

const pct = (v: number) => `${v >= 0 ? "+" : ""}${(v * 100).toFixed(1)}%`;

function StockInner() {
  const params = useParams<{ ticker: string }>();
  const ticker = (params.ticker ?? "").toUpperCase();
  const q = useQuery({
    queryKey: ["stock", ticker],
    queryFn: () => fetchStock(ticker),
    enabled: ticker.length > 0,
  });

  if (q.isPending)
    return <div className="skeleton m-6 h-96 w-auto" />;
  if (q.isError || !q.data)
    return (
      <div className="m-6 border border-rule bg-panel p-6 font-mono text-xs text-muted">
        {ticker}: not found in the universe.{" "}
        <Link href="/" className="text-cobalt">← back to rankings</Link>
      </div>
    );
  const d = q.data;
  const first = d.prices[0]?.close;
  const last = d.prices[d.prices.length - 1]?.close;
  const yearRet = first && last ? last / first - 1 : null;
  const latestFactors = d.factors[d.factors.length - 1];

  return (
    <main className="mx-auto max-w-5xl px-4 py-6">
      <Link href="/" className="font-mono text-2xs text-muted hover:text-body">
        ← alpha engine
      </Link>
      <div className="mt-2 flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <h1 className="font-display text-3xl font-semibold text-bright">
          {d.ticker}
        </h1>
        <span className="text-sm text-body">{d.name}</span>
        {d.sector && (
          <span className="font-mono text-2xs text-muted">{d.sector}</span>
        )}
        {yearRet != null && (
          <span
            className={cn("font-mono text-sm",
              yearRet >= 0 ? "text-gain" : "text-loss")}
          >
            {pct(yearRet)} / 1y
          </span>
        )}
        <span className="ml-auto font-mono text-2xs text-muted">
          data {d.date}
        </span>
      </div>

      {/* price chart */}
      <div className="mt-4 border border-rule bg-panel p-3">
        <div className="label-2xs mb-2">Close · ~1y</div>
        <div className="h-56">
          <ResponsiveContainer>
            <AreaChart data={d.prices}>
              <defs>
                <linearGradient id="pfill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#5B7CFF" stopOpacity={0.25} />
                  <stop offset="100%" stopColor="#5B7CFF" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis dataKey="date" hide />
              <YAxis
                domain={["auto", "auto"]}
                width={52}
                tick={{ fill: "#7A8580", fontSize: 10, fontFamily: "monospace" }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip
                contentStyle={{ background: "#101413", border: "1px solid #242C28",
                  fontFamily: "monospace", fontSize: 11 }}
                labelStyle={{ color: "#7A8580" }}
              />
              <Area type="monotone" dataKey="close" stroke="#5B7CFF"
                strokeWidth={1.5} fill="url(#pfill)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        {/* factor breakdown + history */}
        <div className="border border-rule bg-panel p-3">
          <div className="label-2xs mb-2">Factor breakdown (latest)</div>
          {latestFactors ? (
            <div className="space-y-1.5">
              {(
                [
                  ["Momentum", latestFactors.momentum],
                  ["Valuation", latestFactors.valuation],
                  ["Quality", latestFactors.quality],
                  ["Insider / Congress", latestFactors.insider_congress],
                ] as const
              ).map(([label, v]) => (
                <div key={label} className="flex items-center justify-between gap-3">
                  <span className="text-xs">{label}</span>
                  {v != null ? (
                    <AlphaBar value={v} width="w-28" max={3} />
                  ) : (
                    <span className="font-mono text-2xs text-muted">n/a</span>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p className="font-mono text-2xs text-muted">no factor history</p>
          )}
          <div className="label-2xs mb-1 mt-4">Momentum · 90d</div>
          <div className="h-24">
            <ResponsiveContainer>
              <LineChart data={d.factors}>
                <XAxis dataKey="date" hide />
                <YAxis hide domain={["auto", "auto"]} />
                <Line type="monotone" dataKey="momentum" stroke="#4ADE80"
                  strokeWidth={1.25} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* model views + cards */}
        <div className="space-y-4">
          <div className="border border-rule bg-panel p-3">
            <div className="label-2xs mb-2">Model views · {d.date}</div>
            {d.models.length === 0 ? (
              <p className="font-mono text-2xs text-muted">no predictions</p>
            ) : (
              d.models.map((m) => (
                <div key={m.model_version}
                  className="flex items-baseline justify-between py-0.5 font-mono text-xs">
                  <span className="truncate text-muted">{m.model_version}</span>
                  <span>
                    <span className="text-bright">#{m.rank ?? "—"}</span>
                    <span className={cn("ml-3",
                      m.alpha_score >= 0 ? "text-gain" : "text-loss")}>
                      {m.alpha_score >= 0 ? "+" : ""}{m.alpha_score.toFixed(2)}
                    </span>
                    {m.predicted_return_30d != null && (
                      <span className="ml-3 text-muted">
                        {pct(m.predicted_return_30d)} est.
                      </span>
                    )}
                  </span>
                </div>
              ))
            )}
          </div>

          <div className="border border-rule bg-panel p-3">
            <div className="label-2xs mb-2">Signal cards</div>
            {d.cards.length === 0 ? (
              <p className="font-mono text-2xs text-muted">
                none issued — cards require |alpha| ≥ 1.0
              </p>
            ) : (
              d.cards.map((c) => (
                <div key={c.issue_date}
                  className="flex flex-wrap items-baseline justify-between gap-x-3 border-t border-rule py-1 font-mono text-2xs first:border-t-0">
                  <span className={c.direction === "BUY" ? "text-gain" : "text-loss"}>
                    {c.direction}
                  </span>
                  <span className="text-muted">{c.issue_date}</span>
                  <span>
                    e {c.entry.toFixed(2)} · t {c.target.toFixed(2)} · s{" "}
                    {c.stop.toFixed(2)}
                  </span>
                  <span className={cn(
                    c.status === "hit" ? "text-gain"
                      : c.status === "stop" ? "text-loss" : "text-muted")}>
                    {c.status}
                    {c.realized_return != null && ` ${pct(c.realized_return)}`}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* thesis */}
      {d.thesis && (
        <div className="mt-4 border border-rule bg-panel p-4">
          <div className="label-2xs mb-2">Model thesis</div>
          <p className="whitespace-pre-line text-sm leading-relaxed text-body">
            {d.thesis}
          </p>
        </div>
      )}
      <p className="mt-4 font-mono text-2xs text-muted">
        Backtested signals, not financial advice.
      </p>
    </main>
  );
}

export default function StockPage() {
  return (
    <Providers>
      <StockInner />
    </Providers>
  );
}
