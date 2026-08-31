"""Factor signal construction, verified against hand-computed cases."""

import numpy as np
import pytest

from trading_engine.strategies.factors import (
    composite_scores,
    rank_zscores,
    risk_adjusted_momentum,
    weekly_volatility,
)


def _flat(n, value=100.0):
    return np.full(n, value)


def _smooth_trend(n, daily=0.001, start=100.0):
    """Perfectly smooth exponential -- degenerate, zero volatility."""
    return start * (1 + daily) ** np.arange(n)


def _noisy_trend(n, daily=0.001, sigma=0.005, seed=0, start=100.0):
    rng = np.random.default_rng(seed)
    return start * np.cumprod(1 + daily + rng.normal(0, sigma, n))


def test_flat_price_has_no_volatility_signal():
    assert np.isnan(weekly_volatility(_flat(800)))


def test_degenerate_smooth_series_is_rejected_not_amplified():
    # A smooth exponential has volatility at floating-point scale. Since vol is
    # the momentum denominator, this must be rejected rather than producing an
    # astronomically large score that dominates every ranking.
    assert np.isnan(weekly_volatility(_smooth_trend(800)))
    assert np.isnan(risk_adjusted_momentum(_smooth_trend(800), 12))


def test_weekly_volatility_scales_with_noise():
    rng = np.random.default_rng(1)
    quiet = 100 * np.cumprod(1 + rng.normal(0, 0.002, 800))
    loud = 100 * np.cumprod(1 + rng.normal(0, 0.02, 800))
    assert weekly_volatility(quiet) < weekly_volatility(loud)


def test_momentum_is_nan_without_enough_history():
    # 12-month momentum needs 12*21 + 21 + 1 = 274 bars minimum.
    assert np.isnan(risk_adjusted_momentum(_noisy_trend(200), 12))
    assert not np.isnan(risk_adjusted_momentum(_noisy_trend(800), 12))


def test_momentum_sign_follows_trend_direction():
    rng = np.random.default_rng(2)
    noise = rng.normal(0, 0.005, 800)
    up = 100 * np.cumprod(1 + 0.001 + noise)
    down = 100 * np.cumprod(1 - 0.001 + noise)
    assert risk_adjusted_momentum(up, 12) > 0
    assert risk_adjusted_momentum(down, 12) < 0


def test_momentum_return_term_excludes_the_most_recent_month():
    # Change ONLY the final month's prices. The return numerator must be
    # untouched (that's the one-month lag), while the volatility denominator
    # legitimately does see the new data. So the two signals may differ, but
    # only in proportion to their volatilities:
    #     mom_base / mom_spiked == vol_spiked / vol_base
    # If the last month leaked into the return term, this identity breaks.
    base = _noisy_trend(800, seed=7)
    spiked = base.copy()
    spiked[-21:] = base[-21:] * 3.0

    mom_base = risk_adjusted_momentum(base, 12, lag_months=1)
    mom_spiked = risk_adjusted_momentum(spiked, 12, lag_months=1)
    vol_base = weekly_volatility(base)
    vol_spiked = weekly_volatility(spiked)

    assert vol_spiked > vol_base, "the spike must raise measured volatility"
    assert mom_base / mom_spiked == pytest.approx(vol_spiked / vol_base, rel=1e-9)


def test_momentum_return_term_does_see_older_changes():
    # The mirror image: a change OUTSIDE the lag window must move the signal.
    base = _noisy_trend(800, seed=7)
    altered = base.copy()
    altered[-200:-100] = base[-200:-100] * 1.5
    assert risk_adjusted_momentum(base, 12) != pytest.approx(
        risk_adjusted_momentum(altered, 12)
    )


def test_rank_zscores_are_centered_and_ordered():
    z = rank_zscores({"A": 1.0, "B": 2.0, "C": 3.0, "D": 4.0, "E": 5.0})
    assert z["A"] < z["B"] < z["C"] < z["D"] < z["E"]
    assert sum(z.values()) == pytest.approx(0.0, abs=1e-9)
    assert z["C"] == pytest.approx(0.0, abs=1e-9)


def test_rank_zscores_ignore_outlier_magnitude():
    # Rank-based: replacing 5.0 with 5_000_000 must not change any score,
    # because only the ordering matters. This is the QMJ robustness property.
    mild = rank_zscores({"A": 1.0, "B": 2.0, "C": 3.0, "D": 4.0, "E": 5.0})
    extreme = rank_zscores({"A": 1.0, "B": 2.0, "C": 3.0, "D": 4.0, "E": 5e6})
    assert mild == pytest.approx(extreme)


def test_rank_zscores_drop_non_finite_and_need_two_names():
    assert rank_zscores({"A": float("nan"), "B": 1.0}) == {}
    assert rank_zscores({"A": 1.0}) == {}
    z = rank_zscores({"A": 1.0, "B": float("inf"), "C": 2.0, "D": 3.0})
    assert set(z) == {"A", "C", "D"}


def test_composite_prefers_strong_low_vol_trend():
    rng = np.random.default_rng(3)
    n = 900
    winner = 100 * np.cumprod(1 + 0.0012 + rng.normal(0, 0.004, n))
    loser = 100 * np.cumprod(1 - 0.0012 + rng.normal(0, 0.004, n))
    choppy = 100 * np.cumprod(1 + 0.0012 + rng.normal(0, 0.03, n))
    scores = composite_scores(
        {"WIN": winner, "LOSE": loser, "CHOP": choppy}, use_low_vol=True
    )
    assert scores["WIN"] > scores["LOSE"]
    assert scores["WIN"] > scores["CHOP"], "risk-adjusted: choppy must score lower"
