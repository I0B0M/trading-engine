"""Point-in-time fundamentals from the SEC's XBRL API.

Why this exists: the two best-documented factors for large-cap stocks are
quality (gross profits / assets, Novy-Marx 2013) and value (book-to-market).
Both need accounting data, and using today's *restated* accounting data in a
backtest is look-ahead bias -- you would be trading on numbers nobody had.

The SEC's API solves this because every reported fact carries the date it was
actually filed:

    {"end": "2019-09-28", "val": 338516000000,
     "accn": "0000320193-19-000119", "filed": "2019-10-31", "form": "10-K"}

Filtering on `filed <= as_of` reproduces exactly what was knowable that day.
This matters more than it sounds: sampling SEC filings shows net income is
revised in ~10% of firm-years, and when it is revised the median change is
~14%. Net income is the numerator of ROE, so a backtest on restated data is
quietly trading on information from the future.

Endpoints (free, no key, ~10 requests/second limit):
    https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json
    https://www.sec.gov/files/company_tickers.json

We use companyfacts, NOT companyconcept, for a measured reason: the
companyconcept endpoint returns an empty {"units": {"USD": {}}} for some
company/tag pairs that genuinely do have data. Coca-Cola's Assets came back
empty from companyconcept while companyfacts returned 144 facts for the same
tag. companyfacts is also one request per company rather than one per tag.

NOTE the SEC requires a User-Agent naming you and a contact address, so they
can reach whoever is loading their servers. There is deliberately no default:
set SEC_USER_AGENT in .env to something like "yourname you@example.com".
Sending a fake or someone else's address would defeat the point.

Verified quirk: the SEC returns 403 for any User-Agent containing
"github.com", regardless of format. Do not put a repo URL in it.

COVERAGE, measured rather than assumed. Across 20 large caps as of
2024-06-30, gross-profits-over-assets was computable for 14 (70%). The six
failures are structural, not bugs:

  JPM, BAC   banks report no cost-of-goods line. Novy-Marx (2013) explicitly
             excludes financials (one-digit SIC 6), so returning None here is
             the CORRECT behaviour, not a gap to patch.
  NEE, MCD   utility and franchise models: no standard COGS element.
  XOM        energy filers break costs into "crude oil and product purchases"
             etc.; the standard COGS tag does not exist for them. XOM also
             has only 2 Assets facts in companyfacts, both quarterly.
  T          telecom: revenue tagged under elements outside CONCEPTS.

The lesson for a strategy built on this: a quality factor cannot rank a
universe uniformly, so either restrict the universe to non-financials with
complete data (what the literature does) or the missing names silently drop
out of every ranking -- which is itself a selection bias worth naming.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
MIN_REQUEST_INTERVAL = 0.12  # stay under the SEC's ~10/sec guidance

# Concept tags differ by filer and era, so each logical field needs fallbacks
# tried in order. Revenue tagging in particular changed with ASC 606 in 2018.
CONCEPTS: dict[str, tuple[str, ...]] = {
    "revenue": (
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
    ),
    "cogs": (
        "CostOfGoodsAndServicesSold",
        "CostOfRevenue",
        "CostOfGoodsSold",
    ),
    "assets": ("Assets",),
    "equity": (
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ),
}

ANNUAL_DAYS_MIN, ANNUAL_DAYS_MAX = 300, 430


@dataclass(frozen=True)
class Fact:
    """One reported number, with the date it became public."""

    end: dt.date
    filed: dt.date
    value: float
    form: str
    start: dt.date | None = None

    @property
    def duration_days(self) -> int | None:
        return (self.end - self.start).days if self.start else None

    @property
    def is_annual(self) -> bool:
        """Instant facts (no start) count as annual only from a 10-K."""
        d = self.duration_days
        if d is None:
            return self.form.startswith("10-K")
        return ANNUAL_DAYS_MIN <= d <= ANNUAL_DAYS_MAX


def parse_facts(payload: dict) -> list[Fact]:
    """Turn one tag's JSON payload into Facts, skipping malformed rows.

    Accepts either a bare {"units": ...} block or a full concept payload. The
    SEC sometimes serves `units: {"USD": {}}` -- an empty DICT where a list of
    facts belongs -- so the value is type-checked rather than trusted.
    """
    facts: list[Fact] = []
    for unit_rows in payload.get("units", {}).values():
        if not isinstance(unit_rows, list):
            continue  # the empty-dict case; no facts here
        for row in unit_rows:
            if not isinstance(row, dict):
                continue
            try:
                end = dt.date.fromisoformat(row["end"])
                filed = dt.date.fromisoformat(row["filed"])
                value = float(row["val"])
            except (KeyError, TypeError, ValueError):
                continue
            start = None
            if row.get("start"):
                try:
                    start = dt.date.fromisoformat(row["start"])
                except ValueError:
                    start = None
            facts.append(
                Fact(end, filed, value, str(row.get("form", "")), start)
            )
    return facts


def point_in_time(
    facts: list[Fact], as_of: dt.date, annual_only: bool = True
) -> Fact | None:
    """The value a trader could actually have used on `as_of`.

    Rules, in order:
      1. discard anything filed after `as_of` -- this is the whole point
      2. keep the most recent fiscal period end among what remains
      3. within that period, take the latest filing, since a restatement
         published before `as_of` was genuinely the best available number
    """
    visible = [f for f in facts if f.filed <= as_of]
    if annual_only:
        visible = [f for f in visible if f.is_annual]
    if not visible:
        return None
    latest_end = max(f.end for f in visible)
    same_period = [f for f in visible if f.end == latest_end]
    return max(same_period, key=lambda f: f.filed)


def gross_profits_over_assets(
    revenue: float | None, cogs: float | None, assets: float | None
) -> float | None:
    """Novy-Marx (2013) quality signal: (revenue - COGS) / total assets.

    Scaled by assets rather than book equity deliberately -- gross profit is an
    asset-level measure, unreduced by interest payments, so this is independent
    of leverage. Novy-Marx: "the cleanest accounting measure of true economic
    profitability."
    """
    if revenue is None or cogs is None or not assets or assets <= 0:
        return None
    return (revenue - cogs) / assets


def book_to_market(equity: float | None, market_cap: float | None) -> float | None:
    if equity is None or not market_cap or market_cap <= 0:
        return None
    return equity / market_cap


class MissingUserAgent(RuntimeError):
    pass


class SecClient:
    """Cached, rate-limited reader for the SEC XBRL API."""

    def __init__(self, cache_dir: Path | None = None, user_agent: str | None = None):
        self.cache_dir = cache_dir or (
            Path(__file__).resolve().parents[3] / "data_cache" / "sec"
        )
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        from ..live.env import load_env_file

        load_env_file()
        self.user_agent = user_agent or os.environ.get("SEC_USER_AGENT") or ""
        if not self.user_agent.strip():
            raise MissingUserAgent(
                "The SEC requires a User-Agent naming you and a contact address, "
                "so they can reach whoever is loading their servers.\n\n"
                "Add this line to .env:\n"
                "  SEC_USER_AGENT=yourname you@example.com\n\n"
                "Use a real address you read. Note the SEC returns 403 for any "
                "User-Agent containing 'github.com'."
            )
        self._last_request = 0.0

    def _get(self, url: str, cache_key: str) -> dict | None:
        cached = self.cache_dir / f"{cache_key}.json"
        if cached.is_file():
            try:
                return json.loads(cached.read_text())
            except json.JSONDecodeError:
                cached.unlink(missing_ok=True)

        elapsed = time.monotonic() - self._last_request
        if elapsed < MIN_REQUEST_INTERVAL:
            time.sleep(MIN_REQUEST_INTERVAL - elapsed)
        self._last_request = time.monotonic()

        request = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 404:  # concept not reported by this filer; expected
                cached.write_text("{}")
                return {}
            raise
        cached.write_text(json.dumps(payload))
        return payload

    def cik_for_ticker(self, ticker: str) -> str | None:
        payload = self._get(TICKERS_URL, "company_tickers")
        if not payload:
            return None
        wanted = ticker.strip().upper()
        for row in payload.values():
            if str(row.get("ticker", "")).upper() == wanted:
                return f"{int(row['cik_str']):010d}"
        return None

    def company_facts(self, cik: str) -> dict:
        """Every us-gaap tag for one company, in a single cached request."""
        payload = self._get(FACTS_URL.format(cik=cik), f"{cik}_companyfacts")
        return (payload or {}).get("facts", {}).get("us-gaap", {})

    def concept_facts(self, cik: str, field: str) -> list[Fact]:
        """Facts for a logical field, MERGED across every candidate tag.

        Merging rather than first-match is load-bearing. Revenue tagging
        changed with ASC 606 in 2018: modern filers report
        RevenueFromContractWithCustomerExcludingAssessedTax, which has no
        pre-2018 history, while their older years sit under Revenues or
        SalesRevenueNet. Taking the first tag that has any facts therefore
        resolves to the modern tag and silently returns nothing for earlier
        dates -- measured at 4% quality coverage in 2012 versus 70% in 2024
        before this was fixed.

        Duplicate periods across tags are left for point_in_time() to resolve
        by filing date, which is the same rule it applies to restatements.
        """
        gaap = self.company_facts(cik)
        merged: list[Fact] = []
        for tag in CONCEPTS[field]:
            merged.extend(parse_facts(gaap.get(tag, {})))
        return merged

    def snapshot(self, ticker: str, as_of: dt.date) -> dict[str, float | None]:
        """Every tracked fundamental for `ticker` as known on `as_of`."""
        cik = self.cik_for_ticker(ticker)
        if cik is None:
            return {field: None for field in CONCEPTS}
        out: dict[str, float | None] = {}
        for field in CONCEPTS:
            fact = point_in_time(self.concept_facts(cik, field), as_of)
            out[field] = fact.value if fact else None
        return out
