"""Persistent log of every backtest ever run.

Why this exists: the deflated Sharpe ratio needs N, the number of strategy
configurations tried. N cannot be reconstructed honestly after the fact --
nobody remembers the variants that failed, and that is exactly the bias the
correction is meant to remove. So every backtest appends a row here
automatically, whether it succeeded or not.

Arnott, Harvey & Markowitz's backtesting protocol opens with this:
"Did the researcher keep track of all models and variables that were tried,
both successful and unsuccessful?"
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

LOG_NAME = "trials.jsonl"


def log_path(root: Path | None = None) -> Path:
    base = root or Path(__file__).resolve().parents[3]
    return base / LOG_NAME


@dataclass(frozen=True)
class Trial:
    strategy: str
    symbols: str
    params: str
    start: str
    end: str
    annual_sharpe: float
    cagr: float

    def key(self) -> str:
        """Identity of a configuration: same key = same trial, not a new one."""
        return f"{self.strategy}|{self.symbols}|{self.params}|{self.start}|{self.end}"


def record(trial: Trial, root: Path | None = None) -> int:
    """Append `trial` and return the total number of DISTINCT configurations
    tried so far. Re-running an identical configuration does not inflate N."""
    path = log_path(root)
    with path.open("a") as fh:
        fh.write(json.dumps(trial.__dict__) + "\n")
    return count_distinct(root)


def count_distinct(root: Path | None = None) -> int:
    path = log_path(root)
    if not path.is_file():
        return 0
    keys = set()
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        keys.add(
            "|".join(
                str(row.get(f, ""))
                for f in ("strategy", "symbols", "params", "start", "end")
            )
        )
    return len(keys)


def summary(root: Path | None = None) -> str:
    path = log_path(root)
    if not path.is_file():
        return "No trials logged yet."
    rows = [
        json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()
    ]
    distinct = count_distinct(root)
    by_strategy: dict[str, int] = {}
    for row in rows:
        by_strategy[row.get("strategy", "?")] = (
            by_strategy.get(row.get("strategy", "?"), 0) + 1
        )
    best = max(rows, key=lambda r: r.get("annual_sharpe", float("-inf")))
    lines = [
        f"{len(rows)} backtest runs, {distinct} distinct configurations",
        "",
        "runs per strategy:",
    ]
    lines += [f"  {name:16} {n}" for name, n in sorted(by_strategy.items())]
    lines += [
        "",
        f"best observed Sharpe: {best.get('annual_sharpe', float('nan')):.2f}"
        f"  ({best.get('strategy')} on {best.get('symbols')})",
        "",
        "Remember: the best of N tries is not the same as a real edge.",
        f"Every 'trade backtest' run prints the Sharpe that {distinct} worthless",
        "strategies would produce by luck alone -- compare against that, not zero.",
    ]
    return "\n".join(lines)
