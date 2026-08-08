"""
Indicator definitions for the Market Risk/Froth Dashboard.

Design notes (why it's structured this way):

- Four categories instead of three "lenses": Macro Fundamentals (quant),
  Valuation & Positioning (quant), Technical Trend (quant), and Qualitative
  Judgment (your own subjective read). Keeping qualitative calls in their
  own bucket means they can't quietly pad a "quantitative" score, and you
  can see exactly how much of the composite is opinion vs data.

- Every indicator has a WEIGHT (0-1 relative importance within its
  category), not just a trigger/no-trigger flag. Credit spreads and the
  yield curve get weighted higher than sentiment surveys because they
  have historically had more predictive power. A straight "3 of 10
  triggered" count treats a AAII sentiment blip the same as a credit
  spread inversion, which isn't right.

- No indicator appears in more than one category. The yield curve is
  scored once (Macro Fundamentals). Shiller CAPE lives in Valuation, not
  in a "recession risk" bucket, since valuation predicts long-run
  *returns*, not recession *timing*.

- Each indicator has a `direction`: 'high_is_risk' or 'low_is_risk',
  plus a (low_risk_threshold, high_risk_threshold) band. Score is
  linearly interpolated between the thresholds and clipped to [0, 100],
  where 100 = maximum risk/froth on that single indicator.
"""

from dataclasses import dataclass, field
from typing import Literal, Optional


Direction = Literal["high_is_risk", "low_is_risk"]


@dataclass
class Indicator:
    key: str                 # unique id, used as the manual-entry prompt key
    label: str                # human-readable name
    category: str             # one of CATEGORIES below
    weight: float              # relative weight within its category (any positive number; normalized automatically)
    direction: Direction        # which end of the scale is "risky"
    low_risk_value: float        # value at/beyond which score = 0 (benign)
    high_risk_value: float        # value at/beyond which score = 100 (max risk)
    unit: str = ""             # shown in the input prompt, purely cosmetic
    subjective: bool = False       # True for qualitative 1-5 style inputs
    note: str = ""             # short reminder of what to look up / how to judge it
    fetch_key: Optional[str] = None  # if set, dashboard.py --auto will try data_sources.FETCHERS[fetch_key]
    source_links: Optional[list] = None  # list of (label, url) tuples — dashboard.py prints each as a clickable link

    def score(self, value: float) -> float:
        """Map a raw value to a 0-100 risk/froth score for this indicator.

        low_risk_value is the value at which this indicator scores 0
        (benign) and high_risk_value is the value at which it scores 100
        (max risk/froth) — direction is already baked into which one is
        numerically larger, so no separate flip is needed here. (An
        earlier version double-applied the flip via `direction`, which
        inverted low_is_risk indicators like PMI and the yield curve —
        fixed.)
        """
        lo, hi = self.low_risk_value, self.high_risk_value
        if lo == hi:
            return 0.0
        t = (value - lo) / (hi - lo)
        t = max(0.0, min(1.0, t))
        return round(t * 100, 1)


CATEGORIES = [
    "Macro Fundamentals",
    "Valuation & Positioning",
    "Technical Trend",
    "Qualitative Judgment",
]

# Default weight given to each category in the overall composite.
# Quant categories dominate; qualitative judgment counts but can't swamp
# the data-driven score. Edit these if you disagree with the balance.
CATEGORY_WEIGHTS = {
    "Macro Fundamentals": 0.35,
    "Valuation & Positioning": 0.25,
    "Technical Trend": 0.20,
    "Qualitative Judgment": 0.20,
}


INDICATORS: list[Indicator] = [
    # ---------------- Macro Fundamentals (quant) ----------------
    Indicator(
        key="yield_curve_10y_3m",
        label="10Y-3M Treasury spread",
        category="Macro Fundamentals",
        weight=1.0,
        direction="low_is_risk",
        low_risk_value=1.5,   # pp, steeply positive = benign
        high_risk_value=-1.0,  # pp, inverted = risky
        unit="pp",
        note="FRED series T10Y3M, latest value in percentage points.",
        fetch_key="yield_curve_10y_3m",
    ),
    Indicator(
        key="sahm_rule",
        label="Sahm Rule indicator",
        category="Macro Fundamentals",
        weight=1.0,
        direction="high_is_risk",
        low_risk_value=0.0,
        high_risk_value=0.5,
        note="FRED SAHMREALTIME. 0.50+ historically flags a recession has started.",
        fetch_key="sahm_rule",
    ),
    Indicator(
        key="hy_oas_stress",
        label="High-yield credit spread (stress check)",
        category="Macro Fundamentals",
        weight=0.9,
        direction="high_is_risk",
        low_risk_value=350,
        high_risk_value=800,
        unit="bps",
        note="ICE BofA HY OAS (FRED BAMLH0A0HYM2). Widening spreads = credit stress.",
        fetch_key="hy_oas_stress",
    ),
    Indicator(
        key="ism_pmi",
        label="ISM Manufacturing PMI",
        category="Macro Fundamentals",
        weight=0.8,
        direction="low_is_risk",
        low_risk_value=55,
        high_risk_value=45,
        note="Below 50 = contraction.",
        source_links=[("ISM PMI", "https://tradingeconomics.com/united-states/manufacturing-pmi")],
    ),
    Indicator(
        key="lei_mom",
        label="Conference Board LEI, m/m change",
        category="Macro Fundamentals",
        weight=0.6,
        direction="low_is_risk",
        low_risk_value=0.2,
        high_risk_value=-1.0,
        unit="%",
        source_links=[("Conference Board LEI", "https://www.conference-board.org/topics/us-leading-indicators")],
    ),
    Indicator(
        key="payrolls_vs_consensus",
        label="Latest nonfarm payrolls vs consensus",
        category="Macro Fundamentals",
        weight=0.6,
        direction="low_is_risk",
        low_risk_value=20,
        high_risk_value=-100,
        unit="k, actual minus consensus",
        source_links=[("Nonfarm payrolls", "https://tradingeconomics.com/united-states/non-farm-payrolls")],
    ),

    # ---------------- Valuation & Positioning (quant) ----------------
    Indicator(
        key="shiller_cape",
        label="Shiller CAPE ratio",
        category="Valuation & Positioning",
        weight=0.7,
        direction="high_is_risk",
        low_risk_value=20,
        high_risk_value=40,
        note="Long-run median is ~17x. This predicts long-run returns, not recession timing.",
        fetch_key="shiller_cape",
        source_links=[("Shiller CAPE", "https://www.multpl.com/shiller-pe")],
    ),
    Indicator(
        key="forward_pe",
        label="S&P 500 forward P/E",
        category="Valuation & Positioning",
        weight=0.8,
        direction="high_is_risk",
        low_risk_value=16,
        high_risk_value=23,
        source_links=[("S&P 500 forward P/E", "https://www.wsj.com/market-data/stocks/peyields")],
    ),
    Indicator(
        key="rule_of_20",
        label="Rule of 20 (trailing P/E + CPI y/y)",
        category="Valuation & Positioning",
        weight=0.6,
        direction="high_is_risk",
        low_risk_value=16,
        high_risk_value=26,
        fetch_key="rule_of_20",
        source_links=[("Trailing P/E", "https://www.wsj.com/market-data/stocks/peyields"), ("CPI y/y", "https://www.investing.com/economic-calendar/cpi-733")],
    ),
    Indicator(
        key="aaii_bull_bear_spread",
        label="AAII bulls minus bears",
        category="Valuation & Positioning",
        weight=0.5,
        direction="high_is_risk",
        low_risk_value=0,
        high_risk_value=35,
        unit="pp",
        note="Historical average bull-bear spread is roughly +6 to +8pp.",
        source_links=[("AAII Sentiment Survey", "https://www.aaii.com/sentimentsurvey")],
    ),
    Indicator(
        key="naaim_exposure",
        label="NAAIM manager equity exposure",
        category="Valuation & Positioning",
        weight=0.6,
        direction="high_is_risk",
        low_risk_value=60,
        high_risk_value=100,
        source_links=[("NAAIM Exposure Index", "https://ycharts.com/indicators/naaim_number")],
    ),
    Indicator(
        key="credit_spread_percentile",
        label="HY credit spread percentile vs 10yr history",
        category="Valuation & Positioning",
        weight=0.7,
        direction="low_is_risk",
        low_risk_value=40,
        high_risk_value=5,
        unit="percentile, 0=tightest ever",
        note="A separate lens from hy_oas_stress above: how RICH/complacent credit looks, not whether it's stressed.",
        fetch_key="credit_spread_percentile",
    ),
    
    # ---------------- Technical Trend (quant) ----------------
    Indicator(
        key="price_vs_200sma",
        label="Price vs 200-day SMA",
        category="Technical Trend",
        weight=1.0,
        direction="low_is_risk",
        low_risk_value=5,
        high_risk_value=-5,
        unit="%",
        fetch_key="price_vs_200sma",
    ),
    Indicator(
        key="price_vs_50sma",
        label="Price vs 50-day SMA",
        category="Technical Trend",
        weight=0.7,
        direction="low_is_risk",
        low_risk_value=3,
        high_risk_value=-5,
        unit="%",
        fetch_key="price_vs_50sma",
    ),
    Indicator(
        key="sma50_vs_sma150_slope",
        label="50-day SMA minus 150-day SMA (death-cross proximity)",
        category="Technical Trend",
        weight=0.9,
        direction="low_is_risk",
        low_risk_value=1.0,
        high_risk_value=-0.5,
        unit="%",
        note="Negative and widening = death cross territory.",
        fetch_key="sma50_vs_sma150_slope",
    ),

    # ---------------- Qualitative Judgment (subjective, 1-5) ----------------
    Indicator(
        key="labor_market_softness_feel",
        label="Labor market softness (your read of recent coverage)",
        category="Qualitative Judgment",
        weight=1.0,
        direction="high_is_risk",
        low_risk_value=1,
        high_risk_value=5,
        subjective=True,
        note="1 = solid, hiring healthy. 5 = layoffs/hiring freezes dominating headlines.",
    ),
    Indicator(
        key="retail_mania_vibe",
        label="Retail/meme mania vibe",
        category="Qualitative Judgment",
        weight=0.8,
        direction="high_is_risk",
        low_risk_value=1,
        high_risk_value=5,
        subjective=True,
        note="1 = fear/apathy dominates. 5 = 'can't lose' retail euphoria, everyone's a trader.",
    ),
    Indicator(
        key="narrative_crowding",
        label="Single-theme narrative crowding (e.g. one dominant AI/macro story)",
        category="Qualitative Judgment",
        weight=0.7,
        direction="high_is_risk",
        low_risk_value=1,
        high_risk_value=5,
        subjective=True,
        note="1 = diverse, balanced narratives. 5 = market seemingly pricing one story only.",
    ),
    Indicator(
        key="geopolitical_tail_risk",
        label="Geopolitical/tail-risk overhang",
        category="Qualitative Judgment",
        weight=0.6,
        direction="high_is_risk",
        low_risk_value=1,
        high_risk_value=5,
        subjective=True,
        note="1 = quiet backdrop. 5 = live, market-moving geopolitical risk in play.",
    ),
    Indicator(
        key="credit_conditions_narrative",
        label="Credit-tightening narrative in the news (bank surveys, lending standards)",
        category="Qualitative Judgment",
        weight=0.6,
        direction="high_is_risk",
        low_risk_value=1,
        high_risk_value=5,
        subjective=True,
        note="1 = lending easy/stable. 5 = widespread reports of tightening standards.",
    ),
]


def indicators_by_category() -> dict[str, list[Indicator]]:
    out: dict[str, list[Indicator]] = {c: [] for c in CATEGORIES}
    for ind in INDICATORS:
        out[ind.category].append(ind)
    return out
