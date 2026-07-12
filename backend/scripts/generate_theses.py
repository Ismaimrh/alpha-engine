"""Step 10 — generate LLM theses for the top picks (run on YOUR machine).

    cd backend
    python scripts/generate_theses.py                    # top 10, max $1
    python scripts/generate_theses.py --top-n 20 --max-cost 2.0

PREREQUISITES: migration database/008_theses_dedup.sql applied;
ANTHROPIC_API_KEY set in .env.

Cost expectation: ~600-800 input + ~250 output tokens per thesis ->
roughly half a cent per stock; top-10 ~ $0.05. The --max-cost guard stops
the run cleanly if reality disagrees.

Verification:
    SELECT count(*), sum(cost_usd), max(date) FROM llm_theses;
"""

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.llm.thesis_generator import ThesisGenerator  # noqa: E402
from app.ml.predict import CHAMPION_VERSION  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--max-cost", type=float, default=1.0)
    args = parser.parse_args()

    from app.api.picks import (fetch_companies, fetch_latest_prediction_date,
                               fetch_predictions)
    from app.utils.db import supabase

    pred_date = fetch_latest_prediction_date(CHAMPION_VERSION)
    if pred_date is None:
        print("No predictions found — run run_daily_predictions.py first.")
        return 1
    preds = fetch_predictions(pred_date, CHAMPION_VERSION, args.top_n)
    companies = fetch_companies([p["company_id"] for p in preds])

    window_start = (date.fromisoformat(pred_date) - timedelta(days=90)).isoformat()
    generator = ThesisGenerator()
    total_cost, written = 0.0, 0

    for rank, pred in enumerate(preds, 1):
        cid = pred["company_id"]
        company = companies.get(cid, {})
        factors = (
            supabase.table("factor_scores")
            .select("momentum_composite,valuation_composite,"
                    "quality_composite,insider_congress_composite")
            .eq("company_id", cid).eq("date", pred_date).limit(1).execute()
        ).data
        prices = (
            supabase.table("price_features")
            .select("momentum_12_1,rsi_14")
            .eq("company_id", cid).eq("date", pred_date).limit(1).execute()
        ).data
        ins = supabase.table("insider_transactions").select("transaction_code") \
            .eq("company_id", cid).gte("transaction_date", window_start) \
            .lte("filing_date", pred_date).execute().data
        con = supabase.table("congress_transactions").select("id", count="exact") \
            .eq("company_id", cid).gte("transaction_date", window_start) \
            .lte("filing_date", pred_date).limit(1).execute()

        context = {
            "ticker": company.get("ticker"), "name": company.get("name"),
            "sector": company.get("sector"), "date": pred_date, "rank": rank,
            "alpha_score": pred["alpha_score"],
            "predicted_return_30d": pred.get("predicted_return_30d"),
            **(factors[0] if factors else {}),
            **(prices[0] if prices else {}),
            "insider_buys_90d": sum(1 for r in ins if r["transaction_code"] == "P"),
            "insider_sells_90d": sum(1 for r in ins if r["transaction_code"] == "S"),
            "congress_trades_90d": con.count or 0,
        }
        result = generator.generate(context)
        total_cost += result["cost_usd"]
        if total_cost > args.max_cost:
            print(f"BUDGET STOP: ${total_cost:.4f} > ${args.max_cost} "
                  f"after {written} theses.")
            break
        supabase.table("llm_theses").upsert(
            {"company_id": cid, "date": pred_date, **result},
            on_conflict="company_id,date,model",
        ).execute()
        written += 1
        print(f"  #{rank} {company.get('ticker'):<6} "
              f"{result['prompt_tokens']}+{result['completion_tokens']} tok  "
              f"${result['cost_usd']:.4f}", flush=True)

    print(f"\n--- Step 10 summary ---\n  theses_written: {written}\n"
          f"  total_cost_usd: {round(total_cost, 4)}\n  date: {pred_date}")
    print("\nStep 10 " + ("PASSES." if written else "wrote nothing — review."))
    if written:
        first = supabase.table("llm_theses").select("thesis_text") \
            .eq("date", pred_date).limit(1).execute().data
        if first:
            print("\nSample thesis:\n" + "-" * 60 + f"\n{first[0]['thesis_text']}\n" + "-" * 60)
    return 0 if written else 1


if __name__ == "__main__":
    raise SystemExit(main())
