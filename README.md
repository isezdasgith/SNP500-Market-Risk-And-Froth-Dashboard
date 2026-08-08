# Market Risk / Froth Dashboard

Example Output from Dashboard
<img width="1036" height="449" alt="image" src="https://github.com/user-attachments/assets/1ab1ab3e-2f92-4ea9-ac37-15f2c10f0c45" />
<img width="748" height="577" alt="image" src="https://github.com/user-attachments/assets/a6b4a4c7-5a81-495a-982f-3718bd01365d" />

A manual-entry dashboard that has a collection of different checklist ranging from Macro Fundamentals, Valuation & Positioning, Technical Trend and Qualitative Judgment (subjective) to give an overall market sentiment based on latest data.

- **Weighted, not counted.** Each indicator has a weight; a credit-spread
  inversion counts for more than a sentiment survey blip.
- **No double-counting.** The yield curve (or any indicator) appears in
  exactly one category.
- **Valuation separated from recession risk.** Shiller CAPE predicts
  long-run *returns*, not recession *timing* — it lives in "Valuation &
  Positioning," not "Macro Fundamentals."
- **Qualitative inputs are explicit and separately weighted**, not hidden
  inside a raw indicator count. You rate them 1-5 yourself based on your
  own read of the news, and they're clearly labeled "subjective" in the
  output — the report never lets you forget which parts are data and
  which are judgment calls.

## Quick start

```bash
pip install -r requirements.txt
python dashboard.py --auto      # auto-fetch what's freely available, prompts for the rest
python dashboard.py             # fully manual entry
python dashboard.py --history   # just re-show the latest result + chart
```

### `--auto` mode: what gets fetched automatically

| Indicator | Source | Needs a key? |
|---|---|---|
| Yield curve (10Y-3M) | FRED (T10Y3M) | Yes, free |
| Sahm Rule | FRED (SAHMREALTIME) | Yes, free |
| HY credit spread + its 10yr percentile | FRED (BAMLH0A0HYM2) | Yes, free |
| Rule of 20 (trailing P/E + CPI) | multpl.com scrape + FRED CPI | Yes, free |
| Shiller CAPE | multpl.com scrape | No |
| Price vs 50/200-day SMA, death-cross proximity | yfinance (S&P 500) | No |

First time you run `--auto`, it'll ask for a free FRED API key
(https://fred.stlouisfed.org/docs/api/api_key.html, takes about 30
seconds to get) and save it to `fred_key.txt` so you're not asked again.
Press Enter to skip and those 5 fields will just prompt you manually
instead.

The multpl.com scrapes are best-effort — if multpl changes their page
layout, that fetch will fail and silently fall back to a manual prompt,
same as if your internet drops mid-run. Nothing crashes; you just end up
typing that one field yourself.

**Not automatable — no free structured source exists:** ISM PMI,
Conference Board LEI, payrolls-vs-consensus, forward P/E, AAII
sentiment, NAAIM exposure. Where to look each up
by hand: (LINKS ARE PROVIDED WITHIN EACH PROMPT)

- ISM PMI: ISM website / financial news
- Conference Board LEI: conference-board.org
- Forward P/E, AAII sentiment, NAAIM: FactSet/Yardeni research notes, AAII.com, NAAIM.org
- Payrolls vs consensus: any financial news site the day of the jobs report

For the "Qualitative Judgment" section, there's no lookup — rate each 1-5
based on your own read of recent coverage. The `note` shown for each one
tells you what a 1 and a 5 look like.

### Sanity-checking the fetchers on your machine

Run `python data_sources.py` on its own first — it tests each fetcher
and prints what it got (or the error) without going through the full
form. Useful for confirming your FRED key works and the scrapes are
still working before committing to a full `--auto` run.

## Every run is saved

Each run appends to `history.json` with a timestamp, so running this
weekly/monthly builds a track record you can chart over time — far more
useful than a single snapshot, and it lets you see whether your own
qualitative ratings drift in step with the quantitative score or diverge
from it (worth noticing either way).

## Customizing

- **Change weights or thresholds:** edit `INDICATORS` in `indicators.py`.
  Each indicator's `low_risk_value`/`high_risk_value` define where its
  score is 0 and 100 — tune these to your own view of what's "risky."
- **Change category weights:** edit `CATEGORY_WEIGHTS` in `indicators.py`.
- **Add/remove an indicator:** add or delete an `Indicator(...)` entry.
  The scoring, form, and chart all pick it up automatically — nothing
  else needs to change.

## Files

- `indicators.py` — indicator definitions and scoring logic (the "model")
- `data_sources.py` — auto-fetch layer for `--auto` (FRED, yfinance, multpl scrapes)
- `dashboard.py` — CLI form, composite scoring, history, chart (the "app")
- `requirements.txt` — `pip install -r requirements.txt`
- `fred_key.txt` — created after you enter your FRED key once (gitignore this if you push the repo)
- `history.json` — created after your first run
- `dashboard_output.png` — chart, regenerated each run

## A note on testing

The fetchers were built and their fallback-on-failure logic verified in
a sandboxed environment with no route to fred.stlouisfed.org,
finance.yahoo.com, or multpl.com — so the "network fails gracefully"
path is well-tested, but the "network succeeds" path (i.e. whether the
multpl.com HTML selectors and FRED series IDs are still exactly right)
hasn't been confirmed against the live sites. Run `python
data_sources.py` first to check before relying on `--auto`.
