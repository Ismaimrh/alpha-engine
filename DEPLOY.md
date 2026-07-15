# DEPLOY.md — Step 12 runbook (~30 minutes, all free tiers)

Architecture: **Railway** serves the FastAPI (always-on), **Vercel** serves
the Next.js frontend, **GitHub Actions** runs the nightly pipeline and the
weekly Senate EFD refresh (headed Chrome under xvfb). Supabase stays as-is.

## 0. Push to GitHub (prerequisite for everything)
The commit message is a label for humans — any text is fine. What matters:
push the WHOLE project root (backend/, frontend/, .github/, database/), and
verify no secrets are staged before committing.
```bash
cd <project root>
git init && git add -A
git status | grep -E "\.env|data/" && echo "STOP: secrets/data staged" || echo "clean"
git commit -m "Alpha Engine MVP: pipeline, factors, backtest, API, frontend, schedulers"
gh repo create alpha-engine --private --source . --push   # or create on github.com + git remote add + push
```

## 1. Backend → Railway (~10 min)
1. railway.app → New Project → Deploy from GitHub repo → pick the repo.
2. Settings → **Root Directory: `backend`** (railway.json is read from there;
   it sets the uvicorn start command and the /health healthcheck).
3. Variables → add:
   - `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` (same values as your .env)
   - `ANTHROPIC_API_KEY`
   - `SEC_USER_AGENT`
   - `FRONTEND_ORIGIN` = your Vercel URL (add after step 2; redeploy)
4. Deploy → note the public URL, e.g. `https://alpha-engine-api.up.railway.app`
5. Verify: `curl https://<railway-url>/health` → `{"status":"ok",...}`

## 2. Frontend → Vercel (~5 min)
1. vercel.com → Add New Project → import the repo.
2. **Root Directory: `frontend`** (framework auto-detected: Next.js).
3. Environment variable: `NEXT_PUBLIC_API_URL` = the Railway URL (no
   trailing slash).
4. Deploy → open the URL → all three tabs should populate.
5. Go back to Railway and set `FRONTEND_ORIGIN` to this Vercel URL
   (locks CORS down from `*`).

## 3. Schedulers → GitHub Actions (~5 min)
Repo → Settings → Secrets and variables → Actions → add:
`SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `ANTHROPIC_API_KEY`, `SEC_USER_AGENT`.

Workflows already in the repo:
- `nightly.yml` — 01:30 UTC Tue–Sat: prices (1.2y window) → fundamentals
  snapshot → insider (15d) → factors → predictions → theses (≤$0.25) →
  performance export. Critical-step failures fail the workflow (you get a
  GitHub email).
- `weekly_congress.yml` — Sundays: Senate EFD via headed Chrome + xvfb.

Smoke-test both now: Actions tab → each workflow → **Run workflow**
(manual dispatch is enabled). First nightly run takes ~30–45 min.

## 4. Post-deploy checklist
- [ ] `/health` 200 from Railway
- [ ] Vercel page loads with live data, CORS locked to the Vercel origin
- [ ] Manual nightly run green end-to-end
- [ ] Manual weekly-congress run green (check congress freshness after)
- [ ] Supabase: `select max(date) from predictions;` advances next trading day

## Costs
Railway free/hobby tier (API is tiny), Vercel hobby, GitHub Actions free
(~45 min/night ≈ 1000 min/month, within the 2000 free), Supabase free,
Anthropic ~$0.05/day of theses → **≈ $1–2/month total**, inside the $0–50 budget.

## Known deferred items
- House PTRs (PDF parsing) — post-MVP decision on record.
- Subscriber email *sending* (list collection works; sending is Step 14).
- yfinance rate limits on Actions runners: if the prices step starts
  flaking, add a retry or move price fetch to a Railway cron.

## 5. Launch (Step 14) — daily email
1. resend.com → free account → API key → add GitHub secret `RESEND_API_KEY`.
   Optional secrets: `SITE_URL` (Vercel URL), `API_URL` (Railway URL),
   `EMAIL_FROM` (defaults to Resend's onboarding sender until you verify a domain).
2. Without RESEND_API_KEY the nightly email step DRY-RUNS (logs, no send) —
   the pipeline stays green either way.
3. Test: `python scripts/send_daily_email.py --dry-run` locally, then subscribe
   yourself on the site and trigger the nightly workflow manually.

## GATE 5 — launch checklist
- [ ] Railway /api/stats returns live data (DB wiring proven)
- [ ] Vercel site shows a data date that advances every trading day
- [ ] Nightly + weekly workflows green on schedule (not just manual)
- [ ] Subscribed with a real address; received the daily email; unsubscribe link works
- [ ] UptimeRobot (or similar) pinging /health
- [ ] Supabase backup: weekly pg_dump or scheduled export
- [ ] paper_scoreboard.py reports PENDING (accruing) — Gate 4 verdict ~Sep
