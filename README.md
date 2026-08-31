# trading-engine

An event-driven backtesting engine for stock trading strategies. Replays
15+ years of daily market data one closed bar at a time, simulates every
trade through a broker model with slippage and commissions, and reports
performance with a mandatory in-sample/out-of-sample split.

Phase 1 of three:

1. **Backtesting engine** — test strategies on the past. ✅
2. **Paper trading** — the same strategy classes run on live prices with fake
   money via Alpaca's paper API. ✅
2b. **Honest validation** — every backtest is logged and its Sharpe is judged
   against the number of configurations ever tried. ✅
3. **AI assistant** — describe a strategy in plain English; an LLM compiles
   it to a validated config, the engine backtests it and reports. The AI
   suggests; it never trades.

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

Measured, not assumed — sector ETFs, 2006–2026:

| Strategy | CAGR | Sharpe | max drawdown |
|---|---|---|---|
| SPY buy-and-hold | **11.1%** | 0.65 | −55.2% |
| multifactor (best of 9 configs) | 9.9% | 0.67 | −49.9% |

After 11 logged configurations the luck hurdle is a Sharpe of **1.62**. Our best
is **0.67**, so the verdict is *not distinguishable from luck* — and it earned
less money than buying the index. That is the honest result, and the engine is
built to surface it rather than hide it.

Two known reasons it is weak, both real limitations rather than excuses: the
universe is 9 sector ETFs, so there is almost no cross-sectional breadth to
rank; and the composite is price-only, missing quality (gross profits/assets)
and value (book-to-market) — the two best-documented factors for large caps —
because they need point-in-time fundamentals. The SEC's XBRL API
(`data.sec.gov/api/xbrl/companyconcept/...`) provides those free back to ~2009,
with a `filed` date on every fact, which is the route to adding them without
look-ahead bias.

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
