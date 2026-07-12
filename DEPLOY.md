# DEPLOY.md — Step 12 runbook (~30 minutes, all free tiers)

Architecture: **Railway** serves the FastAPI (always-on), **Vercel** serves
the Next.js frontend, **GitHub Actions** runs the nightly pipeline and the
weekly Senate EFD refresh (headed Chrome under xvfb). Supabase stays as-is.

## 0. Push to GitHub (prerequisite for everything)
```bash
cd <project root>
git init && git add -A && git commit -m "phase 3 complete"  # if not already
gh repo create alpha-engine --private --source . --push     # or via web UI
```

## 1. Backend → Railway (~10 min)
1. railway.app → New Project → Deploy from GitHub repo → pick the repo.
2. Settings → **Root Directory: `backend`** (railway.json is read from there;
   it sets the uvicorn start command and the /health healthcheck).
3. Variables → add:
   - `SUPABASE_URL`, `SUPABASE_KEY` (same values as your .env)
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
`SUPABASE_URL`, `SUPABASE_KEY`, `ANTHROPIC_API_KEY`, `SEC_USER_AGENT`.

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
