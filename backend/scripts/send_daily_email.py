"""Step 14 — send the daily top-10 email (nightly soft step; manual ok).

    python scripts/send_daily_email.py --dry-run     # render + log only
    python scripts/send_daily_email.py               # real send (needs RESEND_API_KEY)

Env: RESEND_API_KEY (absent -> dry run), EMAIL_FROM, SITE_URL, API_URL.
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.notify.daily_email import render_email, send_batch  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.dry_run:
        os.environ.pop("RESEND_API_KEY", None)

    from app.api.picks import (fetch_companies, fetch_latest_prediction_date,
                               fetch_predictions)
    from app.ml.predict import CHAMPION_VERSION
    from app.utils.db import supabase

    pred_date = fetch_latest_prediction_date(CHAMPION_VERSION)
    if pred_date is None:
        print("No predictions — nothing to send.")
        return 0
    preds = fetch_predictions(pred_date, CHAMPION_VERSION, 10)
    companies = fetch_companies([p["company_id"] for p in preds])
    picks = [{"rank": i, "ticker": companies[p["company_id"]]["ticker"],
              "name": companies[p["company_id"]]["name"],
              "alpha_score": p["alpha_score"],
              "predicted_return_30d": p.get("predicted_return_30d")}
             for i, p in enumerate(preds, 1) if p["company_id"] in companies]

    subs = supabase.table("subscribers").select("email").execute().data
    emails = [s["email"] for s in subs]
    if not emails:
        print("0 subscribers — nothing to send.")
        return 0

    api_url = os.getenv("API_URL", "http://127.0.0.1:8000")
    subject, html = render_email(pred_date, picks, api_url)
    result = send_batch(emails, subject, html, api_url)
    print(f"--- daily email ---\n  date: {pred_date}\n  subscribers: "
          f"{len(emails)}\n  {result}")
    return 0 if result["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
