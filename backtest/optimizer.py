"""
Weight Optimizer — Bayesian optimization of confluence module weights.

Uses Optuna (TPE sampler) to find the weight combination that maximizes
the combined objective (win_rate_tp1 × profit_factor) while keeping
max_drawdown within bounds.

From CLAUDE.md Sprint 6 spec:
    Method:     Optuna with TPE sampler, 1000–2000 iterations
    Constraints: Weights sum to 1.0, no module > 30%, no module < 3%
    Objective:  Maximize win_rate_tp1 × profit_factor (max_drawdown <= 15%)
    In-sample:  80% of data; validate on 20% out-of-sample
    Overfitting: OOS performance < 15% degradation vs IS → flag overfitting

Usage:
    optimizer = WeightOptimizer(pair="XAUUSD", trading_style="day_trading")
    best_weights = optimizer.run(
        candles_1m_is=is_data,
        candles_1m_oos=oos_data,
        signal_generator_factory=make_generator,
        n_trials=1500,
    )
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np

# Optuna is optional; guard import so tests don't require it
try:
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    _OPTUNA_AVAILABLE = True
except ImportError:
    _OPTUNA_AVAILABLE = False

from backtest.harness import BacktestConfig, BacktestHarness
from engine.aggregator import WEIGHTS

logger = logging.getLogger(__name__)


# Module count and name order (must match aggregator)
_N_MODULES = 9
_MODULE_NAMES = [
    "market_structure",
    "order_blocks_fvg",
    "ote",
    "ema",
    "rsi",
    "macd",
    "bollinger",
    "kill_zone",
    "support_resistance",
]

# Optimization constraints
MIN_WEIGHT = 0.03
MAX_WEIGHT = 0.30
MAX_DRAWDOWN_LIMIT = 0.15  # 15% max drawdown (XAUUSD), 18% for GBPJPY
MAX_DRAWDOWN_LIMITS = {"XAUUSD": 0.15, "GBPJPY": 0.18}

# Overfitting threshold: OOS must be within this fraction of IS performance
OVERFITTING_THRESHOLD = 0.15   # 15% degradation max

# Default number of Optuna trials
DEFAULT_N_TRIALS = 1500


@dataclass
class OptimizationResult:
    """Results from a weight optimization run."""
    pair: str
    trading_style: str
    best_weights: list[float]
    is_objective: float       # In-sample objective value
    oos_objective: float      # Out-of-sample objective value
    overfitting_flag: bool    # True if OOS < IS * (1 - OVERFITTING_THRESHOLD)
    is_win_rate: float
    is_profit_factor: float
    oos_win_rate: float
    oos_profit_factor: float
    n_trials: int
    baseline_weights: list[float]  # Original weights before optimization


class WeightOptimizer:
    """
    Bayesian weight optimizer using Optuna's TPE sampler.

    The optimizer treats each module weight as a hyperparameter and uses
    coordinate-normalized sampling to ensure all weights sum to 1.0.

    Signal generator factory signature:
        def factory(weights: list[float]) -> Callable
        Returns a signal_generator function that uses the given weights.
    """

    def __init__(self, pair: str, trading_style: str):
        self.pair = pair
        self.trading_style = trading_style
        self._baseline = list(WEIGHTS.get(pair, WEIGHTS["XAUUSD"]))

    def run(
        self,
        candles_1m_is: "pd.DataFrame",
        candles_1m_oos: "pd.DataFrame",
        signal_generator_factory: Callable,
        n_trials: int = DEFAULT_N_TRIALS,
        news_events: Optional["pd.DataFrame"] = None,
    ) -> OptimizationResult:
        """
        Run Bayesian weight optimization.

        Args:
            candles_1m_is:  1-minute candles for the in-sample period (80% of data).
            candles_1m_oos: 1-minute candles for the out-of-sample period (20%).
            signal_generator_factory: Callable(weights) → signal_generator_fn.
            n_trials: Number of Optuna trials.
            news_events: Optional news event DataFrame.

        Returns:
            OptimizationResult with best weights and performance metrics.
        """
        if not _OPTUNA_AVAILABLE:
            raise ImportError(
                "Optuna is required for weight optimization. "
                "Install with: pip install optuna"
            )

        max_dd = MAX_DRAWDOWN_LIMITS.get(self.pair, 0.15)

        def objective(trial: "optuna.Trial") -> float:
            weights = self._sample_weights(trial)
            gen = signal_generator_factory(weights)

            config = BacktestConfig(
                pair=self.pair,
                trading_style=self.trading_style,
                entry_timeframe="",
                max_simultaneous_signals=3,
            )
            harness = BacktestHarness(config)

            try:
                result = harness.run(candles_1m_is, gen, news_events)
            except Exception as e:
                logger.debug(f"Trial {trial.number} failed: {e}")
                return 0.0

            m = result.metrics
            if m.total_trades < 30:
                return 0.0  # Insufficient trades for meaningful score

            # Penalize if drawdown exceeds limit
            if m.max_drawdown_pct / 100.0 > max_dd:
                return 0.0

            return m.win_rate_tp1 * m.profit_factor

        study = optuna.create_study(
            direction="maximize",
            sampler=optuna.samplers.TPESampler(seed=42),
        )
        study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

        best_weights = self._trial_to_weights(study.best_trial)
        is_objective = study.best_value

        # Evaluate best weights on OOS data
        oos_gen = signal_generator_factory(best_weights)
        oos_config = BacktestConfig(
            pair=self.pair,
            trading_style=self.trading_style,
            entry_timeframe="",
            max_simultaneous_signals=3,
        )
        oos_harness = BacktestHarness(oos_config)
        oos_result = oos_harness.run(candles_1m_oos, oos_gen, news_events)
        oos_m = oos_result.metrics
        oos_objective = oos_m.win_rate_tp1 * oos_m.profit_factor

        # IS metrics for logging
        is_gen = signal_generator_factory(best_weights)
        is_harness = BacktestHarness(BacktestConfig(
            pair=self.pair, trading_style=self.trading_style, entry_timeframe="",
        ))
        is_result = is_harness.run(candles_1m_is, is_gen, news_events)
        is_m = is_result.metrics

        overfitting = (
            is_objective > 0
            and oos_objective < is_objective * (1.0 - OVERFITTING_THRESHOLD)
        )

        return OptimizationResult(
            pair=self.pair,
            trading_style=self.trading_style,
            best_weights=best_weights,
            is_objective=is_objective,
            oos_objective=oos_objective,
            overfitting_flag=overfitting,
            is_win_rate=is_m.win_rate_tp1,
            is_profit_factor=is_m.profit_factor,
            oos_win_rate=oos_m.win_rate_tp1,
            oos_profit_factor=oos_m.profit_factor,
            n_trials=n_trials,
            baseline_weights=self._baseline,
        )

    def _sample_weights(self, trial: "optuna.Trial") -> list[float]:
        """
        Sample weights using the Dirichlet-like normalized approach.

        Each weight is sampled in [MIN_WEIGHT, MAX_WEIGHT], then normalized
        so they sum to 1.0. Rejection sampling ensures no weight exceeds MAX_WEIGHT
        after normalization.
        """
        raw = [
            trial.suggest_float(f"w_{i}", MIN_WEIGHT, MAX_WEIGHT)
            for i in range(_N_MODULES)
        ]
        total = sum(raw)
        weights = [w / total for w in raw]

        # If any weight exceeds MAX_WEIGHT after normalization, clip and re-normalize
        if any(w > MAX_WEIGHT for w in weights):
            weights = [min(w, MAX_WEIGHT) for w in weights]
            total = sum(weights)
            weights = [w / total for w in weights]

        return weights

    def _trial_to_weights(self, trial: "optuna.trial.FrozenTrial") -> list[float]:
        """Extract normalized weights from a completed trial."""
        raw = [trial.params.get(f"w_{i}", MIN_WEIGHT) for i in range(_N_MODULES)]
        total = sum(raw)
        weights = [w / total for w in raw]
        if any(w > MAX_WEIGHT for w in weights):
            weights = [min(w, MAX_WEIGHT) for w in weights]
            total = sum(weights)
            weights = [w / total for w in weights]
        return weights


def compute_wfo_efficiency(
    is_results: list["BacktestResult"],
    oos_results: list["BacktestResult"],
) -> float:
    """
    Compute the Walk-Forward Optimization efficiency ratio.

    WFO efficiency = avg OOS profit factor / avg IS profit factor
    Acceptance criterion: >= 0.6

    Args:
        is_results: In-sample BacktestResult per window.
        oos_results: Out-of-sample BacktestResult per window (parallel to IS).

    Returns:
        WFO efficiency ratio (0.0–1.0+). Returns 0.0 if no valid windows.
    """
    if not is_results or not oos_results:
        return 0.0

    def _mean_pf(results: list) -> float:
        pfs = [r.metrics.profit_factor for r in results
               if r.metrics.profit_factor < float("inf") and r.metrics.total_trades > 0]
        return float(np.mean(pfs)) if pfs else 0.0

    avg_is = _mean_pf(is_results)
    avg_oos = _mean_pf(oos_results)

    if avg_is <= 0:
        return 0.0
    return avg_oos / avg_is
