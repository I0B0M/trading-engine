"""Stock universes, and an honest accounting of survivorship bias.

The problem this module refuses to hide: the obvious way to backtest a stock
strategy is to take today's S&P 500 members and run them back through history.
That is broken, because today's list contains only companies that SURVIVED.
Every firm that went bankrupt, got acquired at a discount, or was delisted for
poor performance is silently absent -- so the backtest is run on a universe
pre-selected for success.

The size of the distortion is not small. Bessembinder (2018) found that of
~26,000 US stocks since 1926, only 42.6% beat one-month Treasury bills over
their lifetime, the median lifetime return was -2.29%, and the single most
common outcome was a loss of essentially 100%. Removing the failures from a
backtest removes most of the downside of stock picking.

We cannot fully fix this without a paid point-in-time database (CRSP or
similar): free price sources carry no data for tickers that stopped trading.
What we CAN do, and do here, is:

  1. define universes as of a stated historical date, not as of today
  2. include the names that have since died, by ticker
  3. report exactly which ones have no price data, so the bias is measured
     and visible rather than assumed away

`survivorship_report()` is the function that does step 3. Run it before
trusting any backtest built on these lists.

MEASURED RESULT for large_cap_2010: 14 of 81 names (17%) have no usable price
history. Thirteen are genuine corporate deaths -- acquisitions, mergers, going
private. One, BK (Bank of New York Mellon), is still listed today and simply
fails to download: a free-data-source gap, not a delisting. Worth separating,
because they are different problems even though they bias a backtest the same
way. The practical reading is that ~17% is a FLOOR on the distortion here,
since it counts only names we know to look for.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

# Large-cap US names as of roughly January 2010. Chosen for two properties:
# broad sector spread, and it deliberately RETAINS companies that have since
# been acquired, taken private, or merged out of existence. Those are the
# names a naive "today's index members" universe would silently drop.
LARGE_CAP_2010: tuple[str, ...] = (
    # still listed today
    "AAPL", "ABT", "AMGN", "AXP", "BA", "BAC", "BK", "BMY", "C", "CAT",
    "CL", "CMCSA", "COP", "COST", "CSCO", "CVS", "CVX", "DD", "DIS", "EMR",
    "EXC", "F", "FDX", "GD", "GE", "GILD", "GS", "HD", "HON", "IBM",
    "INTC", "JNJ", "JPM", "KO", "LLY", "LMT", "LOW", "MCD", "MDT", "MMM",
    "MO", "MRK", "MS", "MSFT", "NKE", "NSC", "ORCL", "OXY", "PEP", "PFE",
    "PG", "QCOM", "RF", "SLB", "SO", "T", "TGT", "TXN", "UNH", "UNP",
    "UPS", "USB", "UTX", "VZ", "WFC", "WMB", "WMT", "XOM",
    # acquired, merged, taken private, or otherwise gone since 2010 --
    # these are the survivorship-bias canaries
    "AVP",   # Avon, acquired by Natura 2020
    "BHI",   # Baker Hughes, merged into GE Oil & Gas 2017
    "COV",   # Covidien, acquired by Medtronic 2015
    "DELL",  # taken private 2013
    "EP",    # El Paso, acquired by Kinder Morgan 2012
    "HNZ",   # H.J. Heinz, acquired by Berkshire/3G 2013
    "MON",   # Monsanto, acquired by Bayer 2018
    "NYX",   # NYSE Euronext, acquired by ICE 2013
    "RTN",   # Raytheon, merged into RTX 2020
    "S",     # Sprint, merged into T-Mobile 2020
    "SLE",   # Sara Lee, split 2012
    "WAG",   # Walgreen, reorganised as WBA 2014
    "XTO",   # XTO Energy, acquired by ExxonMobil 2010
)

UNIVERSES: dict[str, tuple[str, ...]] = {
    "large_cap_2010": LARGE_CAP_2010,
}


@dataclass(frozen=True)
class SurvivorshipReport:
    universe: str
    as_of: dt.date
    total: int
    with_data: tuple[str, ...]
    missing: tuple[str, ...]

    @property
    def missing_fraction(self) -> float:
        return len(self.missing) / self.total if self.total else 0.0

    def render(self) -> str:
        lines = [
            f"universe            : {self.universe} (constituents as of {self.as_of})",
            f"names in universe   : {self.total}",
            f"price data available: {len(self.with_data)}",
            f"price data MISSING  : {len(self.missing)} "
            f"({self.missing_fraction:.0%})",
        ]
        if self.missing:
            lines += [
                "",
                "  missing: " + ", ".join(self.missing),
                "",
                "  These are companies that existed in the universe but no longer",
                "  trade. A backtest silently runs without them, so its results are",
                "  biased upward by however much they underperformed. Treat any",
                "  result from this universe as an OPTIMISTIC bound, not an estimate.",
            ]
        else:
            lines.append("  No gaps detected -- but absence of evidence is not evidence.")
        return "\n".join(lines)


def survivorship_report(
    name: str = "large_cap_2010", as_of: dt.date | None = None
) -> SurvivorshipReport:
    """Try to load every name in the universe; report which ones are gone."""
    from .loader import load_bars

    symbols = UNIVERSES[name]
    as_of = as_of or dt.date(2010, 1, 1)
    with_data, missing = [], []
    for symbol in symbols:
        try:
            frames = load_bars([symbol], as_of, as_of + dt.timedelta(days=365))
            frame = frames.get(symbol)
            (with_data if frame is not None and len(frame) > 100 else missing).append(
                symbol
            )
        except Exception:
            missing.append(symbol)
    return SurvivorshipReport(
        universe=name,
        as_of=as_of,
        total=len(symbols),
        with_data=tuple(with_data),
        missing=tuple(missing),
    )
