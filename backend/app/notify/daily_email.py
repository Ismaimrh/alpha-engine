"""Daily top-10 email (spec Step 14 / launch).

Design decisions:
- Provider: Resend (100 emails/day free) behind a tiny adapter — swap =
  reimplement send_batch(). NO KEY -> DRY RUN: renders and logs instead
  of sending, so the nightly pipeline is green before signup.
- Unsubscribe: every email carries a signed link
  (/api/unsubscribe?email=..&sig=..). The signature is an HMAC derived
  from SUPABASE_SERVICE_KEY (no new secret to manage) — MVP-honest, not
  bank-grade; documented.
- Content: top 10 tickers + alpha + expected 1mo + link to the site;
  the same disclaimer as the API, always.
"""

from __future__ import annotations

import hashlib
import hmac
import os

import requests

RESEND_URL = "https://api.resend.com/emails"
SITE_URL = os.getenv("SITE_URL", "https://alpha-engine.vercel.app")
EMAIL_FROM = os.getenv("EMAIL_FROM", "Alpha Engine <onboarding@resend.dev>")

DISCLAIMER = ("Backtested signals, not financial advice. "
              "Past performance does not guarantee future results.")


def unsubscribe_sig(email: str) -> str:
    """HMAC-SHA256(email) with a key derived from the service key."""
    secret = (os.getenv("SUPABASE_SERVICE_KEY") or "dev-secret").encode()
    return hmac.new(secret, f"unsub:{email}".encode(),
                    hashlib.sha256).hexdigest()[:20]


def render_email(date: str, picks: list[dict], api_url: str) -> tuple[str, str]:
    """(subject, html). picks: [{rank, ticker, name, alpha_score,
    predicted_return_30d}]."""
    subject = f"Alpha Engine top 10 — {date}"
    rows = "".join(
        f"<tr>"
        f"<td style='padding:4px 10px;color:#7A8580'>{p['rank']}</td>"
        f"<td style='padding:4px 10px;font-weight:600'>{p['ticker']}</td>"
        f"<td style='padding:4px 10px'>{p['name']}</td>"
        f"<td style='padding:4px 10px;text-align:right'>"
        f"{p['alpha_score']:+.2f}</td>"
        f"<td style='padding:4px 10px;text-align:right'>"
        f"{(p.get('predicted_return_30d') or 0) * 100:+.1f}%</td>"
        f"</tr>"
        for p in picks
    )
    html = f"""<div style="font-family:ui-monospace,Menlo,monospace;background:#0A0D0C;color:#C9D1CC;padding:24px">
<h2 style="color:#F2F5F3;margin:0 0 2px">Alpha Engine</h2>
<p style="color:#7A8580;font-size:12px;margin:0 0 16px">daily factor rankings · {date}</p>
<table style="border-collapse:collapse;font-size:13px">
<tr style="color:#7A8580;text-transform:uppercase;font-size:10px">
<th style="padding:4px 10px">#</th><th style="padding:4px 10px">tkr</th>
<th style="padding:4px 10px">company</th><th style="padding:4px 10px">alpha</th>
<th style="padding:4px 10px">exp 1mo</th></tr>
{rows}
</table>
<p style="margin:16px 0"><a href="{SITE_URL}" style="color:#5B7CFF">full ranking, factors &amp; theses →</a></p>
<p style="color:#7A8580;font-size:11px;border-left:2px solid #242C28;padding-left:8px">{DISCLAIMER}</p>
<p style="font-size:10px;color:#7A8580">__UNSUB__</p>
</div>"""
    return subject, html


def send_batch(subscribers: list[str], subject: str, html_template: str,
               api_url: str, force_dry: bool = False) -> dict:
    """Send one email per subscriber with a personal unsubscribe link.
    Dry run when force_dry=True or RESEND_API_KEY is absent. (force_dry
    exists because env-popping is unreliable: config.load_dotenv() can
    restore the key after a pop — learned in production.)"""
    key = os.getenv("RESEND_API_KEY")
    sent, failed, dry = 0, 0, force_dry or key is None
    for email in subscribers:
        link = (f"{api_url}/api/unsubscribe?email={email}"
                f"&sig={unsubscribe_sig(email)}")
        html = html_template.replace(
            "__UNSUB__", f'<a href="{link}" style="color:#7A8580">unsubscribe</a>')
        if dry:
            print(f"  [dry-run] would send to {email}", flush=True)
            sent += 1
            continue
        try:
            resp = requests.post(
                RESEND_URL,
                headers={"Authorization": f"Bearer {key}",
                         "Content-Type": "application/json"},
                json={"from": EMAIL_FROM, "to": [email],
                      "subject": subject, "html": html},
                timeout=20,
            )
            resp.raise_for_status()
            sent += 1
        except Exception as exc:  # noqa: BLE001 — one bad address must not stop the batch
            print(f"  send failed for {email}: {exc}", flush=True)
            failed += 1
    return {"sent": sent, "failed": failed, "dry_run": dry}
