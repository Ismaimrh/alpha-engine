"""yfinance OHLCV pipeline (spec Step 5.1 / Phase 1).

Flow (see scripts/backfill_prices.py for the runnable entry):
    1. fetch_ohlcv(tickers)        — batched yf.download, retries, parquet cache
    2. compute_price_features(df)  — indicators matching the price_features schema
    3. upsert_price_features(...)  — batched idempotent writes
    4. data_quality_log rows       — per-ticker success/missing/error

Conventions:
- Prices are AUTO-ADJUSTED (splits + dividends): yfinance auto_adjust=True.
  All indicators are computed on adjusted closes.
- momentum_12_1 uses the trading-day convention close[t-21]/close[t-252]-1
  (21 ≈ 1 month, 252 ≈ 12 months of sessions). The factor module's
  calendar-offset function is for point queries; this vectorized form is
  for the daily table. Both implement the same 12-1 skip-month economics.
- realized_vol_30d: std of daily log returns over 30 sessions, annualized
  by sqrt(252).
- Point-in-time: every indicator uses only data at or before its row date
  (rolling/shift operations are inherently backward-looking).
"""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import ta
import yfinance as yf

from app.config import RAW_DATA_DIR

YF_CACHE_DIR = RAW_DATA_DIR / "yfinance"
BATCH_SIZE_TICKERS = 50  # per yf.download call — polite to Yahoo
BATCH_PAUSE_SECONDS = 1.0
MAX_RETRIES = 3
ANNUALIZATION = np.sqrt(252)

# Columns of the price_features table that this pipeline fills
FEATURE_COLUMNS = [
    "open", "high", "low", "close", "volume",
    "rsi_14", "macd", "macd_signal", "macd_hist",
    "sma_20", "sma_50", "sma_200",
    "momentum_12_1", "realized_vol_30d",
]


# ----------------------------------------------------------------- fetching

def fetch_ohlcv(
    tickers: list[str],
    start: date,
    end: date,
    cache: bool = True,
) -> dict[str, pd.DataFrame]:
    """Download daily OHLCV for tickers, batched with retries.

    Returns {ticker: DataFrame[Open, High, Low, Close, Volume]} containing
    only tickers that returned data. Missing/empty tickers are simply
    absent (callers log them). Caches each ticker to parquet.
    """
    out: dict[str, pd.DataFrame] = {}
    for i in range(0, len(tickers), BATCH_SIZE_TICKERS):
        batch = tickers[i : i + BATCH_SIZE_TICKERS]
        raw = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                raw = yf.download(
                    batch,
                    start=start.isoformat(),
                    end=(end + timedelta(days=1)).isoformat(),  # end-exclusive
                    auto_adjust=True,
                    group_by="ticker",
                    threads=True,
                    progress=False,
                )
                break
            except Exception as exc:  # noqa: BLE001
                if attempt == MAX_RETRIES:
                    print(f"WARN: batch {batch[0]}..{batch[-1]} failed: {exc}")
                else:
                    time.sleep(2**attempt)
        if raw is None or raw.empty:
            continue
        for ticker in batch:
            frame = (
                raw[ticker]
                if isinstance(raw.columns, pd.MultiIndex) and ticker in raw.columns.get_level_values(0)
                else (raw if len(batch) == 1 else None)
            )
            if frame is None:
                continue
            frame = frame.dropna(how="all")
            if frame.empty:
                continue
            out[ticker] = frame
            if cache:
                YF_CACHE_DIR.mkdir(parents=True, exist_ok=True)
                frame.to_parquet(YF_CACHE_DIR / f"{ticker}.parquet")
        time.sleep(BATCH_PAUSE_SECONDS)
    return out


# ------------------------------------------------------------- indicators

def compute_price_features(ohlcv: pd.DataFrame) -> pd.DataFrame:
    """Compute the price_features indicator set for one ticker.

    Input: DataFrame with columns Open/High/Low/Close/Volume and a
    DatetimeIndex (as returned by yfinance with auto_adjust=True).
    Output: DataFrame indexed by date with FEATURE_COLUMNS. Warm-up rows
    (insufficient history) carry NaN — the DB stores them as NULL.
    """
    close = ohlcv["Close"].astype(float)

    # RSI-14 and MACD 12/26/9 via the ta library — the same canonical
    # implementation the factor module uses. (A hand-rolled Wilder RSI was
    # rejected: its seed initialization diverged from ta in early rows.)
    rsi_14 = ta.momentum.RSIIndicator(close, window=14).rsi()
    macd_obj = ta.trend.MACD(close)
    macd = macd_obj.macd()
    macd_signal = macd_obj.macd_signal()
    macd_hist = macd_obj.macd_diff()

    log_ret = np.log(close / close.shift(1))

    features = pd.DataFrame(
        {
            "open": ohlcv["Open"].astype(float),
            "high": ohlcv["High"].astype(float),
            "low": ohlcv["Low"].astype(float),
            "close": close,
            "volume": ohlcv["Volume"].astype("Int64"),
            "rsi_14": rsi_14,
            "macd": macd,
            "macd_signal": macd_signal,
            "macd_hist": macd_hist,
            "sma_20": close.rolling(20).mean(),
            "sma_50": close.rolling(50).mean(),
            "sma_200": close.rolling(200).mean(),
            "momentum_12_1": close.shift(21) / close.shift(252) - 1,
            "realized_vol_30d": log_ret.rolling(30).std(ddof=1) * ANNUALIZATION,
        }
    )
    features.index = pd.to_datetime(features.index).date
    features.index.name = "date"
    return features


# ------------------------------------------------------------------ writes

def _records(company_id: str, features: pd.DataFrame) -> list[dict]:
    """DB-ready records: NaN -> None, dates -> ISO strings."""
    df = features.reset_index()
    df["date"] = df["date"].astype(str)
    df = df.astype(object).where(pd.notna(df), None)
    records = df.to_dict(orient="records")
    for r in records:
        r["company_id"] = company_id
        if r["volume"] is not None:
            r["volume"] = int(r["volume"])
    return records


def upsert_price_features(
    company_id: str, features: pd.DataFrame, batch_size: int = 1000
) -> int:
    """Idempotent batched upsert into price_features (conflict: company_id+date)."""
    from app.utils.db import supabase

    records = _records(company_id, features)
    sent = 0
    for i in range(0, len(records), batch_size):
        chunk = records[i : i + batch_size]
        supabase.table("price_features").upsert(
            chunk, on_conflict="company_id,date"
        ).execute()
        sent += len(chunk)
    return sent


def log_quality(rows: list[dict]) -> None:
    """Insert data_quality_log rows: {source, ticker, status, details}."""
    from app.utils.db import supabase

    stamped = [{"date": date.today().isoformat(), "source": "yfinance", **r} for r in rows]
    if stamped:
        supabase.table("data_quality_log").insert(stamped).execute()


# ---------------------------------------------------------------- backfill

def get_ticker_to_id() -> dict[str, str]:
    """ticker -> companies.id for the active universe."""
    from app.utils.db import supabase

    resp = (
        supabase.table("companies")
        .select("id,ticker")
        .eq("in_universe", True)
        .execute()
    )
    return {row["ticker"]: row["id"] for row in resp.data}


def backfill_prices(
    tickers: list[str] | None = None, years: int = 2, cache: bool = True
) -> dict:
    """Full Step 5.1 flow. Returns a summary dict."""
    mapping = get_ticker_to_id()
    universe = tickers if tickers is not None else sorted(mapping)
    unknown = [t for t in universe if t not in mapping]
    universe = [t for t in universe if t in mapping]

    end = date.today()
    start = end - timedelta(days=int(years * 365.25) + 30)  # +30d warm-up pad

    print(f"Backfilling {len(universe)} tickers, {start} -> {end} ...")
    data = fetch_ohlcv(universe, start, end, cache=cache)

    quality, rows_written = [], 0
    started = datetime.now()
    for n, ticker in enumerate(universe, 1):
        if ticker not in data:
            quality.append(
                {"ticker": ticker, "status": "missing", "details": "no data returned"}
            )
            continue
        try:
            features = compute_price_features(data[ticker])
            rows_written += upsert_price_features(mapping[ticker], features)
            quality.append(
                {"ticker": ticker, "status": "success", "details": f"{len(features)} rows"}
            )
        except Exception as exc:  # noqa: BLE001 — one bad ticker must not kill the run
            quality.append({"ticker": ticker, "status": "error", "details": str(exc)[:300]})
        if n % 50 == 0:
            print(f"  {n}/{len(universe)} done ({rows_written} rows)")
    for t in unknown:
        quality.append({"ticker": t, "status": "error", "details": "not in companies table"})
    log_quality(quality)

    ok = sum(1 for q in quality if q["status"] == "success")
    return {
        "tickers_requested": len(universe) + len(unknown),
        "tickers_success": ok,
        "tickers_missing": sum(1 for q in quality if q["status"] == "missing"),
        "tickers_error": sum(1 for q in quality if q["status"] == "error"),
        "rows_written": rows_written,
        "elapsed_s": round((datetime.now() - started).total_seconds(), 1),
    }
