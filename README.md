# trading-engine

An event-driven backtesting engine for stock trading strategies. Replays
15+ years of daily market data one closed bar at a time, simulates every
trade through a broker model with slippage and commissions, and reports
performance with a mandatory in-sample/out-of-sample split.

The design goal is not to find a winning strategy. It is to make it hard to
fool yourself into thinking you have found one.

1. **Backtesting engine** — test strategies against history. ✅
2. **Honest validation** — every backtest is logged, and its Sharpe ratio is
   judged against how many configurations have ever been tried. ✅
3. **Paper trading** — the same strategy classes run on live market prices
   with fake money via Alpaca's paper API. ✅
4. **AI assistant** — describe a strategy in plain English; an LLM compiles it
   to a validated config, the engine backtests it and reports. Planned. The AI
   suggests; it never trades.

Everything here runs on simulated or paper money. No real-money trading, and
nothing in this repo constitutes investment advice.

## Honest validation

Every `trade backtest` run appends its configuration to `trials.jsonl` and then
judges the Sharpe ratio against how many configurations have *ever* been tried
— including the failures. This is automatic and cannot be opted out of, because
a trial count assembled after the fact is exactly the biased number the
correction exists to remove.

```bash
trade trials     # every configuration ever tried
```

Why it matters, from the source papers: testing only **10** variants of a
worthless strategy is expected to produce an in-sample Sharpe of **1.57**
(Bailey & López de Prado). With 5 years of data, testing more than ~45
configurations all but guarantees a Sharpe of 1.0 whose true value is zero.
Both figures are reproduced exactly by `tests/test_validation.py`.

### What this found about our own strategies

Measured, not assumed. Individual stocks (67 US large caps from a 2010
constituent list), 2010–2026, split into in-sample and out-of-sample:

| | CAGR | Sharpe | max drawdown |
|---|---|---|---|
| **momentum + low-vol + quality** | 12.3% | 0.90 | −26.4% |
| &nbsp;&nbsp;in-sample (2010–2018) | 11.9% | **1.01** | **−14.5%** |
| &nbsp;&nbsp;**out-of-sample (2019+)** | **12.8%** | **0.83** | −26.4% |
| **SPY buy-and-hold** | **14.2%** | 0.86 | −33.7% |
| &nbsp;&nbsp;in-sample (2010–2018) | 11.4% | 0.80 | −19.3% |
| &nbsp;&nbsp;**out-of-sample (2019+)** | **17.5%** | **0.93** | −33.7% |

Read the two bold rows together, because that is the whole lesson. **In-sample
the strategy beat the index on every measure** — more return, better Sharpe,
half the drawdown. **Out-of-sample it lost**, by 4.7 points of annual return
and on Sharpe too. That is the textbook signature of a strategy fitted to its
own test period, and it is exactly what this repo is built to expose rather
than bury.

Adding point-in-time quality *did* help, consistent with the literature:
10.7% → 12.3% CAGR and Sharpe 0.81 → 0.90 versus price factors alone. It just
did not help enough to beat buying the index.

And the honesty check, after 12 logged configurations:

```
  observed Sharpe (annual) :   0.90
  configurations tried     : 12
  luck hurdle (annual)     :   1.66
  P(real edge > hurdle)    :   0.1%
  VERDICT: NOT distinguishable from luck
```

**Three reasons to treat even these numbers as optimistic:**

1. **Survivorship bias, measured at 17%.** The 2010 universe had 81 names;
   14 have no usable price history today (13 genuine corporate deaths, plus
   BK which still trades but fails to download). The backtest silently runs
   without them, so it is biased upward by however badly they did. Run
   `survivorship_report()` to see the list.
2. **The quality signal ranks only 66% of the universe.** Sleeves are
   intersected, and banks, utilities and energy filers report no
   cost-of-goods line — so a third of the universe is excluded from every
   ranking by accounting convention rather than by merit.
3. **Only 67 names.** Real factor investing works across thousands of
   securities; breadth is where statistical power comes from.

## Point-in-time fundamentals

`data/fundamentals.py` reads the SEC's XBRL `companyfacts` API, which stamps
every reported number with the date it was **filed**. Filtering on
`filed <= as_of` reproduces exactly what was public that day:

```
AAPL Assets, same query, three different dates:
  as of 2019-06-01: FY ending 2018-09-29 = 365,725,000,000 (filed 2018-11-05)
  as of 2019-10-31: FY ending 2019-09-28 = 338,516,000,000 (filed 2019-10-31)
  as of 2024-06-30: FY ending 2023-09-30 = 352,583,000,000 (filed 2023-11-03)
```

This matters because using today's *restated* figures is look-ahead bias:
sampling shows net income is revised in ~10% of firm-years, by a median 14%
when it changes — and net income is the numerator of ROE.

**Coverage is 70%, measured not assumed.** Across 20 large caps, gross
profits / assets computed for 14. The failures are structural: banks (JPM,
BAC) report no cost-of-goods line — and since Novy-Marx (2013) excludes
financials outright, returning nothing there is *correct*. Utilities,
franchises and energy filers (NEE, MCD, XOM) don't use the standard COGS
element either. A quality factor therefore cannot rank a universe uniformly,
and letting those names silently drop out of every ranking is itself a
selection bias worth naming.

Two quirks worth knowing if you use this: the SEC returns **403 for any
User-Agent containing "github.com"**, and the `companyconcept` endpoint
returns empty data for some tags that `companyfacts` has in full (Coca-Cola's
`Assets` came back empty from one and 144 facts from the other).

## Paper trading (Phase 2)

```bash
trade live sma_cross --symbols SPY            # dry-run: prints the trade plan
trade live sma_cross --symbols SPY --execute  # submits to the PAPER account
trade account                                 # paper equity and positions
```

How it works: the runner replays recent history through the exact same
strategy class and engine used for backtesting to reconstruct the portfolio
the strategy wants *today*, diffs that against the paper account's actual
positions, and submits only the difference (rebalances under 0.5% of equity
are skipped). Run it once per day after the close — orders queue for the next
open, the same fill timing the backtester assumes.

Safety: `paper=True` is hard-coded — no code path in this project can reach a
live-money endpoint — and without `--execute` nothing is ever submitted.

### Credentials

Free account at [alpaca.markets](https://alpaca.markets), generate **paper**
API keys from the dashboard, then:

```bash
trade keys
```

It prompts for the key and secret (the secret is not echoed) and writes them
to `.env` with mode 0600, so nothing lands in shell history. Editing `.env` by
hand works too — note it is a dotfile, so Finder hides it unless you press
Cmd+Shift+period.

`.env` is gitignored, so keys stay off the command line, out of shell history,
and out of git. Shell exports still work and take precedence if you prefer
them. Never put live-money keys in this file — the client only ever talks to
the paper endpoint, so live keys would simply fail.

## Design rules

- **No lookahead, structurally.** Strategies read history through a cursor
  that only the engine advances; a signal computed on day T fills at day
  T+1's open, never at T's prices. There is no API through which a strategy
  can see the future.
- **Costs always on.** 5 bps slippage against the trader and 1 bp commission
  by default. Free-trading fantasies flatter every strategy.
- **Out-of-sample verdicts.** `--split` reports tuned-period and unseen-period
  results separately, because strategies that only work on the data they were
  tuned on are memorizing, not predicting.
- **Engine verified against reality.** Buy-and-hold SPY through the simulator
  must reproduce SPY's actual return (it does, within 0.5pp over 16 years),
  and broker math is pytest-checked against hand-computed fills.

## Usage

```bash
uv sync
uv run trade backtest sma_cross --symbols SPY --from 2010-01-01 --split 2021-01-01
uv run trade backtest momentum --symbols XLK,XLF,XLE,XLV,XLI,XLP,XLY,XLU,XLB
uv run trade backtest rsi_reversion --symbols SPY --param entry_below=15
```

Each run prints a report card (total return, CAGR, Sharpe, max drawdown,
against a buy-the-index benchmark) and saves an equity-curve chart to
`reports/`.

## Strategies

| Name | Idea |
|---|---|
| `buy_and_hold` | Buy on day one, never sell. The benchmark and the engine's sanity check. |
| `sma_cross` | Golden cross: invested while the 50-day average is above the 200-day. |
| `momentum` | Monthly, hold the 3 sector ETFs with the strongest 6-month return. |
| `rsi_reversion` | In an uptrend, buy sharp 2-day dips, exit on recovery. |

A strategy is a small class; the engine does everything else:

```python
class SmaCross(Strategy):
    params = {"fast": 50, "slow": 200}

    def on_bar(self, bar, history):
        closes = history.closes(bar.symbol, self.p.slow)
        if sma(closes, self.p.fast) > sma(closes, self.p.slow):
            self.target_position(bar.symbol, 1.0)
        else:
            self.target_position(bar.symbol, 0.0)
```

## Layout

```
src/trading_engine/
├── engine/      # events, history window, portfolio, broker sim, replay loop
├── data/        # yfinance loader with local parquet cache
├── strategies/  # one class per strategy + shared indicators
├── metrics/     # CAGR / Sharpe / drawdown, report, equity charts
└── cli.py       # `trade backtest ...`
tests/           # broker & metrics vs hand-computed numbers; no-lookahead proof
```

## Tests

```bash
uv run pytest
```

Disclaimer: educational project. Simulated and paper results are not
investment advice, and past performance does not predict future returns.
