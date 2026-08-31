"""Multiple-testing corrections, checked against the source papers'
own published worked examples -- the only way to know the formulas are right."""

import numpy as np
import pytest

from trading_engine.validation.deflated import (
    assess,
    expected_max_sharpe,
    min_backtest_length,
    probabilistic_sharpe,
)
from trading_engine.validation.trials import Trial, count_distinct, record


def test_matches_bailey_ten_trials_gives_sharpe_1_57():
    # Bailey & Lopez de Prado: "if the researcher tries only N = 10
    # alternative configurations... expected to find a strategy with a
    # Sharpe ratio IS of 1.57, despite... zero OOS."
    assert expected_max_sharpe(10, 1.0) == pytest.approx(1.57, abs=0.01)


def test_matches_bailey_forty_five_trials_needs_five_years():
    # Bailey et al.: "if only 5 years of data are available, no more than 45
    # independent model configurations should be tried."
    assert min_backtest_length(45, 1.0) == pytest.approx(5.0, abs=0.05)


def test_hurdle_rises_with_more_trials():
    # The whole point: trying more variants raises the bar.
    assert expected_max_sharpe(5, 1.0) < expected_max_sharpe(50, 1.0)
    assert expected_max_sharpe(50, 1.0) < expected_max_sharpe(500, 1.0)


def test_psr_normal_case_reduces_to_plain_significance():
    # Normal returns (skew 0, kurtosis 3): denominator is sqrt(1 + SR^2/2).
    p = probabilistic_sharpe(0.1, n_obs=101, skew=0.0, kurtosis=3.0)
    expected_z = 0.1 * 10.0 / (1 + 0.5 * 0.01) ** 0.5
    from scipy.stats import norm

    assert p == pytest.approx(float(norm.cdf(expected_z)), abs=1e-9)


def test_negative_skew_and_fat_tails_lower_confidence():
    base = probabilistic_sharpe(0.1, 1000, skew=0.0, kurtosis=3.0)
    skewed = probabilistic_sharpe(0.1, 1000, skew=-2.0, kurtosis=3.0)
    fat = probabilistic_sharpe(0.1, 1000, skew=0.0, kurtosis=20.0)
    assert skewed < base, "negative skew must reduce confidence"
    assert fat < base, "fat tails must reduce confidence"


def test_lucky_strategy_fails_when_many_trials_declared():
    # A genuinely worthless strategy that happened to look decent.
    rng = np.random.default_rng(0)
    returns = rng.normal(0.0004, 0.01, 2520)  # 10 years, Sharpe ~0.6 annual
    honest = assess(returns, n_trials=200)
    assert not honest.passes, "should not survive 200 declared trials"
    assert honest.hurdle_annual > honest.annual_sharpe


def test_strong_edge_survives_a_single_trial_but_not_many():
    # Daily Sharpe 0.1 -> ~1.6 annualized over 10 years. Real by any standard.
    rng = np.random.default_rng(0)
    returns = rng.normal(0.0008, 0.008, 2520)

    single = assess(returns, n_trials=1)
    assert single.hurdle_annual == 0.0  # nothing tried, nothing to deflate
    assert single.passes

    # The same returns, honestly declaring a wide parameter sweep.
    swept = assess(returns, n_trials=5000)
    assert swept.hurdle_annual > 3.0
    assert not swept.passes, "a 1.6 Sharpe cannot survive 5000 declared trials"


def test_trial_log_counts_distinct_not_repeats(tmp_path):
    t = Trial("sma_cross", "SPY", "fast=50,slow=200", "2010-01-01",
              "2026-01-01", 0.5, 0.09)
    assert record(t, root=tmp_path) == 1
    assert record(t, root=tmp_path) == 1, "re-running the same config is not a new trial"
    other = Trial("sma_cross", "SPY", "fast=20,slow=100", "2010-01-01",
                  "2026-01-01", 0.6, 0.11)
    assert record(other, root=tmp_path) == 2
    assert count_distinct(root=tmp_path) == 2
