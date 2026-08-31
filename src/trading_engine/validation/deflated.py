"""Multiple-testing corrections for backtested Sharpe ratios.

The problem these solve: try enough strategy variants and one of them looks
brilliant on pure luck. Bailey & Lopez de Prado (2014) show that testing only
N = 10 configurations of a worthless strategy is expected to yield an
in-sample Sharpe of 1.57. So a raw Sharpe ratio is uninterpretable without
knowing how many were tried.

Formulas from:
  Bailey & Lopez de Prado, "The Deflated Sharpe Ratio", JPM 2014
  Bailey, Borwein, Lopez de Prado & Zhu, "Pseudo-Mathematics and Financial
    Charlatanism", Notices of the AMS 2014 (Theorem 3.1, MinBTL)
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.stats import norm

EULER_MASCHERONI = 0.5772156649015329


def expected_max_sharpe(n_trials: int, sharpe_variance: float) -> float:
    """Expected maximum Sharpe across `n_trials` when the true Sharpe is zero.

    This is the bar a candidate must clear to be distinguishable from luck.
    `sharpe_variance` is the variance of the Sharpe ratios actually observed
    across the trials; when unknown, 1.0 is the conventional stand-in.
    """
    if n_trials < 2:
        return 0.0
    g = EULER_MASCHERONI
    max_z = (1 - g) * norm.ppf(1 - 1.0 / n_trials) + g * norm.ppf(
        1 - 1.0 / (n_trials * math.e)
    )
    return float(math.sqrt(max(sharpe_variance, 0.0)) * max_z)


def probabilistic_sharpe(
    sharpe: float,
    n_obs: int,
    skew: float = 0.0,
    kurtosis: float = 3.0,
    benchmark: float = 0.0,
) -> float:
    """Probability the true Sharpe exceeds `benchmark`.

    `sharpe` must be per-observation (not annualized) to match `n_obs`.
    `kurtosis` is raw (3.0 for a normal distribution), not excess.
    Adjusts for sample length and for non-normal returns: negative skew and
    fat tails both make a given Sharpe less trustworthy.
    """
    if n_obs < 2:
        return float("nan")
    denom_sq = 1.0 - skew * sharpe + ((kurtosis - 1.0) / 4.0) * sharpe**2
    if denom_sq <= 0:
        return float("nan")
    z = (sharpe - benchmark) * math.sqrt(n_obs - 1) / math.sqrt(denom_sq)
    return float(norm.cdf(z))


def min_backtest_length(n_trials: int, target_sharpe: float = 1.0) -> float:
    """Years of data needed before a Sharpe of `target_sharpe` means anything,
    given `n_trials` configurations tested. Necessary, not sufficient.

    Bailey et al.: with only 5 years of data, testing more than ~45
    configurations almost guarantees an in-sample Sharpe of 1.0 whose
    out-of-sample expectation is zero -- which this reproduces exactly.

    Uses the paper's exact expression, not its looser 2*ln(N) bound; the bound
    overstates the requirement by ~50% at N=45.
    """
    if n_trials < 2 or target_sharpe <= 0:
        return float("nan")
    max_z = expected_max_sharpe(n_trials, 1.0)
    return float(max_z**2 / target_sharpe**2)


@dataclass(frozen=True)
class Verdict:
    """The honest read on a backtested Sharpe ratio."""

    annual_sharpe: float
    n_trials: int
    n_obs: int
    years: float
    skew: float
    kurtosis: float
    hurdle_annual: float  # expected max Sharpe under the null, annualized
    deflated_probability: float  # P(true Sharpe > hurdle)
    min_years_required: float
    passes: bool

    def report(self) -> str:
        lines = [
            f"  observed Sharpe (annual) : {self.annual_sharpe:6.2f}",
            f"  configurations tried     : {self.n_trials}",
            f"  sample length            : {self.years:.1f} years "
            f"({self.n_obs} observations)",
            f"  return skew / kurtosis   : {self.skew:.2f} / {self.kurtosis:.2f}",
            f"  luck hurdle (annual)     : {self.hurdle_annual:6.2f}  "
            f"<- best Sharpe {self.n_trials} worthless strategies would show",
            f"  P(real edge > hurdle)    : {self.deflated_probability:6.1%}",
            f"  years needed for Sharpe 1: {self.min_years_required:.1f}"
            f"  (have {self.years:.1f})",
            "",
            f"  VERDICT: {'survives' if self.passes else 'NOT distinguishable from luck'}",
        ]
        return "\n".join(lines)


def assess(
    daily_returns: np.ndarray,
    n_trials: int,
    trading_days: int = 252,
    sharpe_variance: float = 1.0,
    confidence: float = 0.95,
) -> Verdict:
    """Judge a strategy's Sharpe against the number of variants tested."""
    r = np.asarray(daily_returns, dtype=float)
    r = r[np.isfinite(r)]
    n = len(r)
    sd = r.std(ddof=1) if n > 1 else 0.0
    if n < 2 or sd == 0:
        raise ValueError("need at least 2 varying return observations")

    per_obs_sharpe = float(r.mean() / sd)
    annual_sharpe = per_obs_sharpe * math.sqrt(trading_days)
    centered = (r - r.mean()) / sd
    skew = float((centered**3).mean())
    kurtosis = float((centered**4).mean())

    hurdle_per_obs = expected_max_sharpe(n_trials, sharpe_variance) / math.sqrt(
        trading_days
    )
    prob = probabilistic_sharpe(
        per_obs_sharpe, n, skew, kurtosis, benchmark=hurdle_per_obs
    )
    return Verdict(
        annual_sharpe=annual_sharpe,
        n_trials=n_trials,
        n_obs=n,
        years=n / trading_days,
        skew=skew,
        kurtosis=kurtosis,
        hurdle_annual=expected_max_sharpe(n_trials, sharpe_variance),
        deflated_probability=prob,
        min_years_required=min_backtest_length(n_trials, 1.0),
        passes=bool(prob > confidence),
    )
