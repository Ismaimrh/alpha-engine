const API = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export interface Pick {
  rank: number;
  rank_change: number | null;
  ticker: string;
  name: string;
  sector: string | null;
  alpha_score: number;
  confidence: number | null;
  predicted_return_30d: number | null;
  position_size: number | null;
}

export interface PicksResponse {
  date: string;
  model_version: string;
  count: number;
  picks: Pick[];
  disclaimer: string;
}

export interface FactorBreakdown {
  ticker: string;
  name: string;
  sector: string | null;
  date: string;
  momentum_composite: number | null;
  valuation_composite: number | null;
  quality_composite: number | null;
  insider_congress_composite: number | null;
}

export interface Thesis {
  ticker: string;
  date: string;
  thesis_text: string;
  model: string;
}

export interface Stats {
  companies_in_universe: number;
  latest_price_date: string | null;
  latest_prediction_date: string | null;
  model_versions: string[];
}

export interface RankingRow {
  rank: number;
  ticker: string;
  name: string;
  sector: string | null;
  alpha_score: number;
  predicted_return_30d: number | null;
}

export interface RankingsResponse {
  date: string;
  total: number;
  offset: number;
  rows: RankingRow[];
}

export interface PerformancePoint {
  date: string;
  strategy_equity: number;
  benchmark_equity: number;
}

export interface PerformanceResponse {
  points: PerformancePoint[];
  sharpe: number | null;
  ann_return: number | null;
  benchmark_ann_return: number | null;
  note: string;
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`);
  if (!res.ok) throw new Error(`API ${res.status}: ${path}`);
  return (await res.json()) as T;
}

export const fetchPicks = (limit = 20) =>
  get<PicksResponse>(`/api/picks?limit=${limit}`);
export const fetchStats = () => get<Stats>(`/api/stats`);
export const fetchFactors = (t: string) =>
  get<FactorBreakdown>(`/api/factors/${t}`);
export const fetchThesis = (t: string) => get<Thesis>(`/api/thesis/${t}`);
export const fetchRankings = (offset: number, limit: number, search: string) =>
  get<RankingsResponse>(
    `/api/rankings?offset=${offset}&limit=${limit}${search ? `&search=${encodeURIComponent(search)}` : ""}`,
  );
export const fetchSparklines = (tickers: string[], days = 90) =>
  get<{ days: number; series: Record<string, number[]> }>(
    `/api/sparklines?tickers=${tickers.join(",")}&days=${days}`,
  );
export const fetchPerformance = () =>
  get<PerformanceResponse>(`/api/performance`);

export async function subscribe(email: string): Promise<boolean> {
  try {
    const res = await fetch(`${API}/api/subscribe`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    });
    return res.ok;
  } catch {
    return false;
  }
}
