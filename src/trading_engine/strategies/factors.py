"""Signal construction for cross-sectional factor strategies.

Specs follow published institutional definitions rather than invented ones:

  Momentum  -- MSCI Momentum Indexes Methodology (2025): 6- and 12-month
               price momentum, each lagged one month and divided by the
               3-year weekly return volatility, then z-scored and blended
               50/50. The volatility normalization and the one-month lag are
               the two details retail implementations usually drop.
  Low vol   -- Blitz & van Vliet, "The Volatility Effect" (JPM 2007):
               3-year weekly return volatility, low is good.
  Scaling   -- AQR "Quality Minus Junk": convert to cross-sectional RANK then
               z-score the ranks, so outliers cannot dominate. Winsorized at
               +/-3 per MSCI.
"""

from __future__ import annotations

import numpy as np

TRADING_DAYS_PER_MONTH = 21
WEEKS_PER_YEAR = 52

# A real traded asset never shows annualized volatility below this. A smaller
# value means stale, synthetic, or degenerate price data -- and since
# volatility is a DENOMINATOR in the momentum signal, letting floating-point
# noise through produces absurd scores (observed: 4e14) that would dominate
# every cross-sectional ranking.
MIN_ANNUAL_VOL = 1e-4


def weekly_volatility(closes: np.ndarray, years: int = 3) -> float:
    """Annualized volatility of weekly returns over the trailing `years`.

    Weekly rather than daily because it is the published spec and because
    weekly sampling is less sensitive to bid-ask bounce and non-synchronous
    closes than daily.
    """
    needed = years * WEEKS_PER_YEAR * 5
    window = closes[-needed:] if len(closes) > needed else closes
    if len(window) < 60:
        return float("nan")
    weekly = window[::5]
    if len(weekly) < 12:
        return float("nan")
    returns = np.diff(weekly) / weekly[:-1]
    returns = returns[np.isfinite(returns)]
    if len(returns) < 12:
        return float("nan")
    annual = float(returns.std(ddof=1)) * np.sqrt(WEEKS_PER_YEAR)
    return annual if annual >= MIN_ANNUAL_VOL else float("nan")


def risk_adjusted_momentum(closes: np.ndarray, months: int, lag_months: int = 1) -> float:
    """Return over `months`, ending `lag_months` ago, divided by 3-year vol.

    The lag matters: the most recent month's return reverses on average, so
    including it contaminates the signal.
    """
    lag = lag_months * TRADING_DAYS_PER_MONTH
    span = months * TRADING_DAYS_PER_MONTH
    if len(closes) < lag + span + 1:
        return float("nan")
    end = closes[-(lag + 1)]
    start = closes[-(lag + span + 1)]
    if not (np.isfinite(end) and np.isfinite(start)) or start <= 0:
        return float("nan")
    vol = weekly_volatility(closes)
    if not np.isfinite(vol) or vol <= 0:
        return float("nan")
    return float((end / start - 1.0) / vol)


def rank_zscores(values: dict[str, float]) -> dict[str, float]:
    """Cross-sectional rank, then z-score of the ranks, winsorized at +/-3.

    Rank-based so a single extreme value cannot swamp the signal -- the
    property QMJ cites for using z-scores of ranks rather than raw values.
    """
    clean = {k: v for k, v in values.items() if np.isfinite(v)}
    n = len(clean)
    if n < 2:
        return {}
    order = sorted(clean, key=lambda k: clean[k])
    ranks = {symbol: float(i + 1) for i, symbol in enumerate(order)}
    arr = np.array([ranks[s] for s in order])
    mean, sd = arr.mean(), arr.std(ddof=1)
    if sd == 0:
        return {}
    return {s: float(np.clip((ranks[s] - mean) / sd, -3.0, 3.0)) for s in order}


def composite_scores(
    closes_by_symbol: dict[str, np.ndarray],
    use_low_vol: bool = True,
    extra_signals: dict[str, dict[str, float]] | None = None,
) -> dict[str, float]:
    """Equal-weighted composite of the available price-based factor signals.

    Equal weighting is deliberate: DeMiguel, Garlappi & Uppal show that
    estimating optimal weights costs more in estimation error than it gains,
    and in factor-combination tests equal weighting slightly beat
    inverse-volatility weighting.

    Price-based sleeves are computed here. Fundamental sleeves (quality,
    value) are passed in via `extra_signals` as {name: {symbol: raw_value}},
    because they require point-in-time accounting data that price history
    cannot supply. A sleeve covering only part of the universe still ranks
    only the names it covers -- see the coverage caveat in
    data/fundamentals.py, which is a selection effect, not a rounding error.
    """
    mom6 = rank_zscores(
        {s: risk_adjusted_momentum(c, 6) for s, c in closes_by_symbol.items()}
    )
    mom12 = rank_zscores(
        {s: risk_adjusted_momentum(c, 12) for s, c in closes_by_symbol.items()}
    )
    sleeves = []
    if mom6 and mom12:
        blended = {s: 0.5 * mom6[s] + 0.5 * mom12[s] for s in mom6 if s in mom12}
        sleeves.append(blended)
    elif mom12:
        sleeves.append(mom12)

    if use_low_vol:
        # Negated: low volatility is the desirable end.
        low_vol = rank_zscores(
            {
                s: -v
                for s, v in (
                    (s, weekly_volatility(c)) for s, c in closes_by_symbol.items()
                )
                if np.isfinite(v)
            }
        )
        if low_vol:
            sleeves.append(low_vol)

    # Fundamental sleeves (quality, value) arrive pre-computed because they
    # need point-in-time accounting data the price history does not carry.
    # Each is rank-z-scored on the same footing as the price sleeves.
    for raw in (extra_signals or {}).values():
        sleeve = rank_zscores(raw)
        if sleeve:
            sleeves.append(sleeve)

    if not sleeves:
        return {}
    common = set(sleeves[0])
    for sleeve in sleeves[1:]:
        common &= set(sleeve)
    if not common:
        return {}
    return {
        s: float(np.mean([sleeve[s] for sleeve in sleeves])) for s in sorted(common)
    }
