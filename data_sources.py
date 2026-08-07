"""
Auto-fetch layer for the dashboard.

Every function here returns either a float (success) or None (failed —
dashboard.py will fall back to prompting you manually for that one
indicator, printing why it fell back). Nothing here ever raises; a
network hiccup or a source changing its page layout just means one
fewer auto-filled field, not a crashed program.

Sources used:
  - FRED (Federal Reserve Economic Data) — free, needs an API key.
    Get one in ~30 seconds at https://fred.stlouisfed.org/docs/api/api_key.html
    Then either set the environment variable FRED_API_KEY, or the first
    time you run --auto you'll be prompted and it'll save to fred_key.txt
    in this folder so you're not asked again.
  - yfinance — free, no key needed, pulls S&P 500 price history for the
    technical trend section.
  - multpl.com — scraped best-effort for Shiller CAPE and trailing P/E.
    No official API exists for these; if multpl changes their page
    layout this will start failing and you'll just get prompted
    manually instead, same as any other fallback.

IMPORTANT: none of these calls have been tested against the live
internet in the environment that built this (the sandbox that built
this file has no route to fred.stlouisfed.org / finance.yahoo.com /
multpl.com). Run `python data_sources.py` standalone once after
installing dependencies to sanity-check each fetcher on your own
machine before trusting --auto.
"""

from __future__ import annotations

import os
import statistics
from pathlib import Path
from typing import Optional

FRED_KEY_FILE = Path(__file__).parent / "fred_key.txt"


def get_fred_api_key() -> Optional[str]:
    key = os.environ.get("FRED_API_KEY")
    if key:
        return key.strip()
    if FRED_KEY_FILE.exists():
        return FRED_KEY_FILE.read_text().strip()
    return None


def prompt_and_save_fred_key() -> Optional[str]:
    print(
        "\nNo FRED API key found. FRED powers the yield curve, Sahm Rule, "
        "credit spread, and CPI fetches.\nGet a free key at: "
        "https://fred.stlouisfed.org/docs/api/api_key.html"
    )
    key = input("Paste your FRED API key (or press Enter to skip and enter those fields manually): ").strip()
    if key:
        FRED_KEY_FILE.write_text(key)
        print(f"Saved to {FRED_KEY_FILE.name} — you won't be asked again.\n")
        return key
    return None


def _fred_observations(series_id: str, api_key: str, limit: int = 1, sort_order: str = "desc"):
    import requests

    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "sort_order": sort_order,
        "limit": limit,
    }
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    return [obs for obs in data.get("observations", []) if obs.get("value") not in (".", None)]


def fetch_fred_latest(series_id: str, api_key: str) -> Optional[float]:
    try:
        obs = _fred_observations(series_id, api_key, limit=5, sort_order="desc")
        if not obs:
            return None
        return float(obs[0]["value"])
    except Exception as e:
        print(f"  (FRED fetch for {series_id} failed: {e})")
        return None


def fetch_fred_percentile(series_id: str, api_key: str, years: int = 10) -> Optional[float]:
    """Percentile rank (0-100) of the latest value within the trailing N years."""
    try:
        obs = _fred_observations(series_id, api_key, limit=years * 260, sort_order="desc")
        if len(obs) < 30:
            return None
        values = [float(o["value"]) for o in obs]
        latest = values[0]
        rank = sum(1 for v in values if v <= latest) / len(values) * 100
        return round(rank, 1)
    except Exception as e:
        print(f"  (FRED percentile fetch for {series_id} failed: {e})")
        return None


def fetch_yield_curve_10y_3m(api_key: str) -> Optional[float]:
    return fetch_fred_latest("T10Y3M", api_key)


def fetch_sahm_rule(api_key: str) -> Optional[float]:
    return fetch_fred_latest("SAHMREALTIME", api_key)


def fetch_hy_oas_stress(api_key: str) -> Optional[float]:
    val = fetch_fred_latest("BAMLH0A0HYM2", api_key)
    return round(val * 100, 1) if val is not None else None  # FRED reports this series in %, convert to bps


def fetch_credit_spread_percentile(api_key: str) -> Optional[float]:
    return fetch_fred_percentile("BAMLH0A0HYM2", api_key, years=10)


def fetch_cpi_yoy(api_key: str) -> Optional[float]:
    """CPI year-over-year % change, computed from the raw CPIAUCSL index."""
    try:
        obs = _fred_observations("CPIAUCSL", api_key, limit=14, sort_order="desc")
        if len(obs) < 13:
            return None
        latest = float(obs[0]["value"])
        year_ago = float(obs[12]["value"])
        return round((latest / year_ago - 1) * 100, 2)
    except Exception as e:
        print(f"  (CPI fetch failed: {e})")
        return None


def fetch_sp500_technicals() -> Optional[dict]:
    """Returns dict with price_vs_50sma, price_vs_200sma, sma50_vs_sma150_slope (all %), or None."""
    try:
        import yfinance as yf

        hist = yf.Ticker("^GSPC").history(period="18mo")
        if hist.empty or len(hist) < 200:
            return None
        close = hist["Close"]
        price = close.iloc[-1]
        sma50 = close.rolling(50).mean().iloc[-1]
        sma150 = close.rolling(150).mean().iloc[-1]
        sma200 = close.rolling(200).mean().iloc[-1]
        return {
            "price_vs_50sma": round((price / sma50 - 1) * 100, 2),
            "price_vs_200sma": round((price / sma200 - 1) * 100, 2),
            "sma50_vs_sma150_slope": round((sma50 / sma150 - 1) * 100, 2),
        }
    except Exception as e:
        print(f"  (yfinance technicals fetch failed: {e})")
        return None


def fetch_shiller_cape() -> Optional[float]:
    try:
        import requests
        from bs4 import BeautifulSoup

        resp = requests.get("https://www.multpl.com/shiller-pe", timeout=10,
                             headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        el = soup.select_one("#current div#current + div, .current-value, #current")
        text = el.get_text() if el else resp.text
        import re
        m = re.search(r"(\d{1,3}\.\d{1,2})", text)
        return float(m.group(1)) if m else None
    except Exception as e:
        print(f"  (Shiller CAPE scrape failed: {e})")
        return None


def fetch_trailing_pe() -> Optional[float]:
    try:
        import requests
        from bs4 import BeautifulSoup

        resp = requests.get("https://www.multpl.com/s-p-500-pe-ratio", timeout=10,
                             headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        el = soup.select_one("#current")
        text = el.get_text() if el else resp.text
        import re
        m = re.search(r"(\d{1,3}\.\d{1,2})", text)
        return float(m.group(1)) if m else None
    except Exception as e:
        print(f"  (Trailing P/E scrape failed: {e})")
        return None


def fetch_rule_of_20(api_key: Optional[str]) -> Optional[float]:
    pe = fetch_trailing_pe()
    if pe is None or api_key is None:
        return None
    cpi = fetch_cpi_yoy(api_key)
    if cpi is None:
        return None
    return round(pe + cpi, 2)


# Maps Indicator.fetch_key -> a zero-arg callable. Built once auto_fetch_all()
# runs, since a couple of these need the FRED key bound in via closures.
def build_fetchers(fred_key: Optional[str]) -> dict:
    fetchers = {
        "price_vs_200sma": lambda: _cached_sp500_technicals().get("price_vs_200sma"),
        "price_vs_50sma": lambda: _cached_sp500_technicals().get("price_vs_50sma"),
        "sma50_vs_sma150_slope": lambda: _cached_sp500_technicals().get("sma50_vs_sma150_slope"),
        "shiller_cape": fetch_shiller_cape,
    }
    if fred_key:
        fetchers.update({
            "yield_curve_10y_3m": lambda: fetch_yield_curve_10y_3m(fred_key),
            "sahm_rule": lambda: fetch_sahm_rule(fred_key),
            "hy_oas_stress": lambda: fetch_hy_oas_stress(fred_key),
            "credit_spread_percentile": lambda: fetch_credit_spread_percentile(fred_key),
            "rule_of_20": lambda: fetch_rule_of_20(fred_key),
        })
    return fetchers


# Cache so we don't hit yfinance three times for the three technical indicators
# in one run.
_technicals_cache = None


def _cached_sp500_technicals():
    global _technicals_cache
    if _technicals_cache is None:
        _technicals_cache = fetch_sp500_technicals() or {}
    return _technicals_cache


if __name__ == "__main__":
    # Standalone sanity check — run this after `pip install -r requirements.txt`
    # to see which fetchers work from your machine before running dashboard.py --auto.
    key = get_fred_api_key() or prompt_and_save_fred_key()
    fetchers = build_fetchers(key)
    print("\nTesting each fetcher:\n")
    for name, fn in fetchers.items():
        try:
            val = fn()
        except Exception as e:
            val = f"ERROR: {e}"
        print(f"  {name}: {val}")
