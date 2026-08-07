"""
Market Risk / Froth Dashboard — manual-entry version.

Combines quantitative (macro fundamentals, valuation & positioning,
technical trend) and qualitative (your own judgment calls) inputs into
a single weighted composite score, tracked over time.

USAGE
-----
    python dashboard.py            # interactive form, prompts for each indicator
    python dashboard.py --demo     # runs with example values, no typing required
    python dashboard.py --history  # just show the score history chart/table, no new entry

Each run is saved to history.json (in this folder) with a timestamp, so
you can re-run this weekly/monthly and watch how the composite score
and each category trend over time — much more useful than a single
snapshot.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from indicators import INDICATORS, CATEGORIES, CATEGORY_WEIGHTS, indicators_by_category
import data_sources

HISTORY_FILE = Path(__file__).parent / "history.json"
CHART_FILE = Path(__file__).parent / "dashboard_output.png"

# Example values for --demo mode, keyed by indicator key.
DEMO_VALUES = {
    "yield_curve_10y_3m": 0.98,
    "sahm_rule": 0.2,
    "hy_oas_stress": 281,
    "ism_pmi": 55.6,
    "lei_mom": -0.2,
    "payrolls_vs_consensus": -63,
    "shiller_cape": 42.0,
    "forward_pe": 19.6,
    "rule_of_20": 29.6,
    "aaii_bull_bear_spread": -11,
    "naaim_exposure": 79.7,
    "credit_spread_percentile": 12,
    "ipo_deal_growth_yoy": 88,
    "price_vs_200sma": 1.6,
    "price_vs_50sma": 1.8,
    "sma50_vs_sma150_slope": -0.1,
    "labor_market_softness_feel": 3,
    "retail_mania_vibe": 3,
    "narrative_crowding": 4,
    "geopolitical_tail_risk": 2,
    "credit_conditions_narrative": 2,
}

def prompt_value(ind) -> float:
    unit = f" [{ind.unit}]" if ind.unit else ""
    scale_hint = " (enter 1-5)" if ind.subjective else ""
    note = f"\n    note: {ind.note}" if ind.note else ""
    while True:
        raw = input(f"{ind.label}{unit}{scale_hint}{note}\n> ").strip()
        try:
            return float(raw)
        except ValueError:
            print("  Please enter a number. Try again.")


def collect_values(demo: bool, auto: bool) -> dict[str, float]:
    if demo:
        print("Running in --demo mode with example values.\n")
        return dict(DEMO_VALUES)

    print("=" * 60)
    title = "MARKET RISK / FROTH DASHBOARD" + ("  (auto-fetch on)" if auto else "  — manual entry")
    print(title)
    print("=" * 60)

    fetchers = {}
    if auto:
        fred_key = data_sources.get_fred_api_key() or data_sources.prompt_and_save_fred_key()
        fetchers = data_sources.build_fetchers(fred_key)
        if not fred_key:
            print("(No FRED key — yield curve, Sahm Rule, HY spread, credit percentile, and "
                  "Rule of 20 will fall back to manual entry.)")

    values: dict[str, float] = {}
    for category, inds in indicators_by_category().items():
        print(f"\n--- {category} ---")
        for ind in inds:
            fetched = None
            if auto and ind.fetch_key and ind.fetch_key in fetchers:
                print(f"Fetching {ind.label}...")
                fetched = fetchers[ind.fetch_key]()
            if fetched is not None:
                print(f"  -> {ind.label}: {fetched}{(' ' + ind.unit) if ind.unit else ''}  (auto-fetched)")
                values[ind.key] = fetched
            else:
                if auto and ind.fetch_key:
                    print(f"  -> auto-fetch unavailable, enter manually:")
                values[ind.key] = prompt_value(ind)
    return values


def compute_scores(values: dict[str, float]) -> dict:
    by_cat = indicators_by_category()
    category_scores: dict[str, float] = {}
    indicator_scores: dict[str, dict] = {}

    for category, inds in by_cat.items():
        weighted_sum = 0.0
        weight_total = 0.0
        for ind in inds:
            val = values[ind.key]
            s = ind.score(val)
            indicator_scores[ind.key] = {
                "label": ind.label,
                "category": category,
                "value": val,
                "score": s,
                "weight": ind.weight,
                "subjective": ind.subjective,
            }
            weighted_sum += s * ind.weight
            weight_total += ind.weight
        category_scores[category] = round(weighted_sum / weight_total, 1) if weight_total else 0.0

    cat_weight_total = sum(CATEGORY_WEIGHTS.values())
    composite = round(
        sum(category_scores[c] * CATEGORY_WEIGHTS[c] for c in CATEGORIES) / cat_weight_total,
        1,
    )

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "composite_score": composite,
        "category_scores": category_scores,
        "indicator_scores": indicator_scores,
    }


def verdict(score: float) -> str:
    if score < 30:
        return "BENIGN — little corroborating stress or froth"
    if score < 55:
        return "WATCH — mixed signals, monitor closely"
    if score < 75:
        return "ELEVATED — multiple indicators flashing risk/froth"
    return "HIGH ALERT — broad-based confirmation across categories"


def print_report(result: dict) -> None:
    print("\n" + "=" * 60)
    print(f"COMPOSITE SCORE: {result['composite_score']} / 100")
    print(f"VERDICT: {verdict(result['composite_score'])}")
    print("=" * 60)
    for cat in CATEGORIES:
        cs = result["category_scores"][cat]
        weight_pct = round(CATEGORY_WEIGHTS[cat] * 100)
        tag = " (subjective)" if cat == "Qualitative Judgment" else ""
        print(f"\n{cat}{tag} — {cs}/100  (category weight: {weight_pct}%)")
        for key, info in result["indicator_scores"].items():
            if info["category"] != cat:
                continue
            flag = "  <-- elevated" if info["score"] >= 60 else ""
            print(f"    {info['label']}: value={info['value']}  ->  score={info['score']}{flag}")


def save_history(result: dict) -> list[dict]:
    history = []
    if HISTORY_FILE.exists():
        history = json.loads(HISTORY_FILE.read_text())
    history.append(result)
    HISTORY_FILE.write_text(json.dumps(history, indent=2))
    return history


def plot_history(history: list[dict]) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("\n(matplotlib not installed — skipping chart. `pip install matplotlib` to enable it.)")
        return

    if len(history) < 1:
        return

    dates = [datetime.fromisoformat(h["timestamp"]) for h in history]
    composite = [h["composite_score"] for h in history]

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # Left panel: composite score over time (or single bar if only one run)
    ax1 = axes[0]
    if len(history) == 1:
        ax1.bar(["Latest"], composite, color="#4C72B0")
        ax1.set_ylim(0, 100)
    else:
        ax1.plot(dates, composite, marker="o", color="#4C72B0")
        ax1.set_ylim(0, 100)
        ax1.tick_params(axis="x", rotation=30)
    ax1.axhspan(0, 30, color="green", alpha=0.08)
    ax1.axhspan(30, 55, color="gold", alpha=0.08)
    ax1.axhspan(55, 75, color="orange", alpha=0.08)
    ax1.axhspan(75, 100, color="red", alpha=0.08)
    ax1.set_title("Composite Score Over Time")
    ax1.set_ylabel("Risk / Froth Score")

    # Right panel: latest category breakdown
    ax2 = axes[1]
    latest = history[-1]["category_scores"]
    cats = list(latest.keys())
    vals = [latest[c] for c in cats]
    colors = ["#4C72B0", "#55A868", "#C44E52", "#8172B2"]
    ax2.barh(cats, vals, color=colors[: len(cats)])
    ax2.set_xlim(0, 100)
    ax2.set_title("Latest Category Scores")
    ax2.set_xlabel("Score")
    for i, v in enumerate(vals):
        ax2.text(v + 1, i, str(v), va="center")

    fig.suptitle("Market Risk / Froth Dashboard", fontsize=14, fontweight="bold")
    fig.tight_layout()
    fig.savefig(CHART_FILE, dpi=150)
    print(f"\nChart saved to: {CHART_FILE}")


def main():
    parser = argparse.ArgumentParser(description="Manual-entry market risk/froth dashboard.")
    parser.add_argument("--demo", action="store_true", help="Use example values instead of prompting.")
    parser.add_argument("--auto", action="store_true", help="Auto-fetch what's freely available (FRED + yfinance); prompts for the rest.")
    parser.add_argument("--history", action="store_true", help="Just show history, don't record a new entry.")
    args = parser.parse_args()

    if args.history:
        if not HISTORY_FILE.exists():
            print("No history yet — run the dashboard normally first.")
            return
        history = json.loads(HISTORY_FILE.read_text())
        print_report(history[-1])
        plot_history(history)
        return

    values = collect_values(demo=args.demo, auto=args.auto)
    result = compute_scores(values)
    print_report(result)
    history = save_history(result)
    plot_history(history)


if __name__ == "__main__":
    main()
