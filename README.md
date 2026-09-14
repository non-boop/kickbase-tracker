# kickbase-tracker

Scheduled job that logs into Kickbase, scans the transfer market and your
league, and writes the results to `data/latest.json`:

- top 20 market value gainers / losers (last 24h)
- buy recommendations (value momentum + underpriced + affordable within
  your current budget)
- an estimated budget for every manager in the league (see
  `fetch/budget.py` for how — and its limits)

A Claude scheduled task reads `data/latest.json` from this repo 1-2x/day
and feeds it into a small dashboard web app. This repo never contains
your Kickbase password — only the compiled results.

## One-time setup (do this in GitHub's web UI)

1. **Add two repo secrets** — Settings -> Secrets and variables -> Actions
   -> "New repository secret":
   - `KICK_EMAIL` — your Kickbase login email
   - `KICK_PASSWORD` — your Kickbase password

2. **Make the repo public** (Settings -> General -> Danger Zone -> Change
   visibility). This is what lets the dashboard fetch `data/latest.json`
   without another token. Your two secrets above stay encrypted and
   private either way — only the *scan results* (player values, your
   league's manager names + estimated budgets) become publicly
   fetchable at a hard-to-guess-but-not-secret URL. If you'd rather keep
   the repo private, that's fine too — just let Claude know and it'll
   set up a private Gist instead (one extra secret to add).

3. Push this code (from a normal terminal, not through Claude — GitHub
   blocks Claude's own network access to your account for pushes):

   ```
   cd ~/Documents/Kickbase-Tracker/kickbase-tracker
   git push -u origin main
   ```

4. Optionally trigger the first run immediately instead of waiting for
   the schedule: repo -> Actions tab -> "Kickbase scan" -> "Run workflow".

## Notes / known limitations (v1)

- Endpoint paths and field names come from reverse-engineering by the
  community (Kickbase publishes no official API docs) and may need
  adjusting once we see real output.
- Manager budget estimates ignore realized trading profit and periodic
  income for now — they're a rough "cash not tied up in your squad"
  figure, flagged `trusted: false` when it's clearly off for your own
  account (in which case treat other managers' numbers as directional
  only).
