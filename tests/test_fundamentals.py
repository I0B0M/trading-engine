"""Point-in-time fundamentals logic. No network: the selection rules are pure
functions, and they are where look-ahead bias would actually creep in."""

import datetime as dt

import pytest

from trading_engine.data.fundamentals import (
    Fact,
    book_to_market,
    gross_profits_over_assets,
    parse_facts,
    point_in_time,
)

D = dt.date

# Apple's real Assets facts, abridged from the SEC API. The same fiscal period
# appears twice, filed a year apart -- which is exactly the situation that makes
# naive fundamentals loaders leak the future.
APPLE_ASSETS = {
    "units": {
        "USD": [
            {"end": "2018-09-29", "val": 365725000000, "filed": "2018-11-05",
             "form": "10-K", "accn": "x"},
            {"end": "2019-09-28", "val": 338516000000, "filed": "2019-10-31",
             "form": "10-K", "accn": "y"},
            {"end": "2019-09-28", "val": 338516000000, "filed": "2020-10-30",
             "form": "10-K", "accn": "z"},
        ]
    }
}


def test_parse_facts_reads_filed_dates():
    facts = parse_facts(APPLE_ASSETS)
    assert len(facts) == 3
    assert facts[0].end == D(2018, 9, 29)
    assert facts[0].filed == D(2018, 11, 5)
    assert facts[0].value == 365725000000


def test_parse_facts_skips_malformed_rows_without_crashing():
    payload = {
        "units": {
            "USD": [
                {"end": "not-a-date", "val": 1, "filed": "2020-01-01", "form": "10-K"},
                {"end": "2020-01-01", "filed": "2020-03-01", "form": "10-K"},  # no val
                {"end": "2020-01-01", "val": 5, "filed": "2020-03-01", "form": "10-K"},
            ]
        }
    }
    facts = parse_facts(payload)
    assert len(facts) == 1
    assert facts[0].value == 5


def test_ignores_facts_filed_after_the_as_of_date():
    # THE test. On 2019-06-01, Apple's FY2019 balance sheet did not exist yet;
    # only FY2018, filed 2018-11-05, was public.
    facts = parse_facts(APPLE_ASSETS)
    got = point_in_time(facts, D(2019, 6, 1))
    assert got is not None
    assert got.end == D(2018, 9, 29)
    assert got.value == 365725000000


def test_picks_up_the_new_year_once_it_is_actually_filed():
    facts = parse_facts(APPLE_ASSETS)
    day_before = point_in_time(facts, D(2019, 10, 30))
    day_of = point_in_time(facts, D(2019, 10, 31))
    assert day_before.end == D(2018, 9, 29)
    assert day_of.end == D(2019, 9, 28)


def test_uses_latest_restatement_available_at_the_time():
    # Two filings cover FY2019. Asked as of 2021, the later one (filed
    # 2020-10-30) was genuinely the best number available.
    facts = parse_facts(APPLE_ASSETS)
    got = point_in_time(facts, D(2021, 1, 1))
    assert got.end == D(2019, 9, 28)
    assert got.filed == D(2020, 10, 30)


def test_returns_none_when_nothing_was_public_yet():
    facts = parse_facts(APPLE_ASSETS)
    assert point_in_time(facts, D(2017, 1, 1)) is None


def test_annual_filter_rejects_quarterly_durations():
    quarterly = Fact(D(2020, 3, 31), D(2020, 5, 1), 100.0, "10-Q", D(2020, 1, 1))
    annual = Fact(D(2020, 12, 31), D(2021, 2, 1), 400.0, "10-K", D(2020, 1, 1))
    assert not quarterly.is_annual
    assert annual.is_annual
    got = point_in_time([quarterly, annual], D(2021, 6, 1), annual_only=True)
    assert got.value == 400.0


def test_instant_fact_counts_as_annual_only_from_a_10k():
    from_10k = Fact(D(2020, 12, 31), D(2021, 2, 1), 1.0, "10-K")
    from_10q = Fact(D(2020, 9, 30), D(2020, 11, 1), 2.0, "10-Q")
    assert from_10k.is_annual
    assert not from_10q.is_annual


def test_gross_profits_over_assets_hand_computed():
    # revenue 1000, COGS 600 -> gross profit 400; assets 2000 -> 0.20
    assert gross_profits_over_assets(1000, 600, 2000) == pytest.approx(0.20)


def test_gpoa_guards_against_missing_and_zero_denominators():
    assert gross_profits_over_assets(None, 600, 2000) is None
    assert gross_profits_over_assets(1000, None, 2000) is None
    assert gross_profits_over_assets(1000, 600, 0) is None
    assert gross_profits_over_assets(1000, 600, None) is None


def test_book_to_market_hand_computed_and_guarded():
    assert book_to_market(500, 2000) == pytest.approx(0.25)
    assert book_to_market(500, 0) is None
    assert book_to_market(None, 2000) is None
