"""Performance metrics and the backtest report card."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import numpy as np
import pandas as pd

TRADING_DAYS = 252


@dataclass(frozen=True)
class Metrics:
    label: str
    start: dt.date
    end: dt.date
    total_return: float
    cagr: float
    sharpe: float
    max_drawdown: float
    days: int


def compute_metrics(equity: pd.Series, label: str) -> Metrics:
    equity = equity.dropna()
    if len(equity) < 2:
        raise ValueError("equity curve too short for metrics")
    returns = equity.pct_change().dropna()
    total = float(equity.iloc[-1] / equity.iloc[0] - 1.0)
    years = len(equity) / TRADING_DAYS
    cagr = float((equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1.0)
    vol = float(returns.std(ddof=1))
    sharpe = float(returns.mean() / vol * np.sqrt(TRADING_DAYS)) if vol > 0 else 0.0
    running_max = equity.cummax()
    max_dd = float((equity / running_max - 1.0).min())
    return Metrics(
        label=label,
        start=equity.index[0],
        end=equity.index[-1],
        total_return=total,
        cagr=cagr,
        sharpe=sharpe,
        max_drawdown=max_dd,
        days=len(equity),
    )


def split_metrics(
    equity: pd.Series, split: dt.date | None, label: str
) -> list[Metrics]:
    """Full-period metrics, plus in-sample/out-of-sample when `split` is set."""
    out = [compute_metrics(equity, f"{label} (full)")]
    if split is not None:
        in_sample = equity[equity.index < split]
        out_sample = equity[equity.index >= split]
        if len(in_sample) >= 2:
            out.append(compute_metrics(in_sample, f"{label} (in-sample)"))
        if len(out_sample) >= 2:
            out.append(compute_metrics(out_sample, f"{label} (out-of-sample)"))
    return out


def format_report(
    strategy_metrics: list[Metrics],
    benchmark_metrics: list[Metrics] | None,
    n_fills: int,
) -> str:
    rows = list(strategy_metrics) + list(benchmark_metrics or [])
    width = max(len(m.label) for m in rows)
    lines = [
        f"{'':<{width}}  {'period':>21}  {'total':>8}  {'CAGR':>7}  {'Sharpe':>6}  {'max DD':>7}",
    ]
    for m in rows:
        lines.append(
            f"{m.label:<{width}}  {m.start} → {m.end}  "
            f"{m.total_return:>7.1%}  {m.cagr:>6.1%}  {m.sharpe:>6.2f}  {m.max_drawdown:>7.1%}"
        )
    lines.append(f"\ntrades executed: {n_fills}")
    return "\n".join(lines)


def save_equity_chart(
    equity: pd.Series,
    benchmark: pd.Series | None,
    path: str,
    title: str,
    split: dt.date | None = None,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(11, 6))
    (equity / equity.iloc[0]).plot(ax=ax, label="strategy", lw=1.6)
    if benchmark is not None:
        aligned = benchmark.reindex(equity.index).ffill()
        (aligned / aligned.iloc[0]).plot(ax=ax, label="benchmark", lw=1.2, alpha=0.8)
    if split is not None:
        ax.axvline(split, color="gray", ls="--", lw=1, label="in/out-of-sample split")
    ax.set_title(title)
    ax.set_ylabel("growth of $1")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
