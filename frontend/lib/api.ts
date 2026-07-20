const API = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
if (!process.env.NEXT_PUBLIC_API_URL && process.env.NODE_ENV === "production") {
  // Fail the build rather than ship a frontend that silently calls localhost.
  throw new Error("NEXT_PUBLIC_API_URL must be set for production builds");
}

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

export interface ModelCard {
  model_version: string;
  role: "champion" | "candidate" | "challenger";
  top10: { rank: number; ticker: string; alpha_score: number }[];
  realized: {
    n_days: number;
    mean_ic: number | null;
    t_stat: number | null;
    hit_rate: number | null;
  } | null;
}

export interface ModelsResponse {
  date: string;
  models: ModelCard[];
  overlap_top50: Record<string, number>;
  note: string;
}

export interface SectorRow {
  sector: string;
  n: number;
  mean_alpha: number;
  top_ticker: string;
}

export interface SectorsResponse {
  date: string;
  sectors: SectorRow[];
}

export interface SignalCardT {
  ticker: string;
  issue_date: string;
  direction: "BUY" | "AVOID";
  alpha_score: number;
  entry: number;
  target: number;
  stop: number;
  sigma_21: number;
  horizon_days: number;
  status: string;
  resolved_date: string | null;
  resolved_close: number | null;
  realized_return: number | null;
}

export interface SignalsResponse {
  open_cards: SignalCardT[];
  note: string;
}

export interface LedgerResponse {
  cards: SignalCardT[];
  total: number;
  offset: number;
  limit: number;
}

export interface HitRateResponse {
  state: "collecting" | "reporting";
  n_resolved: number;
  n_hit: number;
  n_stop: number;
  n_expired: number;
  hit_rate: number | null;
  wilson_low: number | null;
  wilson_high: number | null;
  avg_realized_return: number | null;
  note: string;
}

export const fetchSignals = () => get<SignalsResponse>(`/api/signals`);
export const fetchSignalLedger = (offset = 0, limit = 50) =>
  get<LedgerResponse>(`/api/signals/ledger?offset=${offset}&limit=${limit}`);
export const fetchHitRate = () => get<HitRateResponse>(`/api/hitrate`);

export const fetchModels = () => get<ModelsResponse>(`/api/models`);
export const fetchSectors = () => get<SectorsResponse>(`/api/sectors`);

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
