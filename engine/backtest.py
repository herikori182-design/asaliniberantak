import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# Ensure parent repo's backtesting package is importable
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

def crossover(series1: List[float], series2: List[float]) -> bool:
    """
    Lightweight crossover helper (avoid importing `backtesting` at module import time).

    Returns True if series1 crosses above series2 between the previous and current value.
    """
    if series1 is None or series2 is None:
        return False
    if len(series1) < 2 or len(series2) < 2:
        return False
    try:
        prev1, curr1 = float(series1[-2]), float(series1[-1])
        prev2, curr2 = float(series2[-2]), float(series2[-1])
    except Exception:
        return False
    return prev1 <= prev2 and curr1 > curr2

from .data import DEFAULT_DAYS, TIMEFRAMES, _tf_to_ms, load_cached
from .schema import RuleCond, Strategy as DSLStrategy

logger = logging.getLogger(__name__)


# --- Indicator helpers ---
def _sma(series: pd.Series, period: int) -> np.ndarray:
    return series.rolling(period).mean().to_numpy()


def _ema(series: pd.Series, period: int) -> np.ndarray:
    return series.ewm(span=period, adjust=False).mean().to_numpy()


def _rsi(series: pd.Series, period: int = 14) -> np.ndarray:
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    roll_up = up.ewm(span=period, adjust=False).mean()
    roll_down = down.ewm(span=period, adjust=False).mean()
    rs = roll_up / roll_down.replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi.fillna(50).to_numpy()


def _atr(df: pd.DataFrame, period: int = 14) -> np.ndarray:
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low).abs(), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    atr = tr.ewm(span=period, adjust=False).mean()
    return atr.to_numpy()


def _macd(series: pd.Series, fast=12, slow=26, signal=9) -> Dict[str, np.ndarray]:
    fast_ema = _ema(series, fast)
    slow_ema = _ema(series, slow)
    mac = fast_ema - slow_ema
    sig = pd.Series(mac).ewm(span=signal, adjust=False).mean().to_numpy()
    hist = mac - sig
    return {"macLine": mac, "signal": sig, "histogram": hist}


def _boll(series: pd.Series, period=20, std=2.0) -> Dict[str, np.ndarray]:
    ma = series.rolling(period).mean()
    sd = series.rolling(period).std().fillna(0)
    upper = ma + std * sd
    lower = ma - std * sd
    return {"middle": ma.to_numpy(), "upper": upper.to_numpy(), "lower": lower.to_numpy()}


def _support_resistance(high: pd.Series, low: pd.Series, lookback: int = 20) -> Tuple[np.ndarray, np.ndarray]:
    sup = low.rolling(lookback).min().to_numpy()
    res = high.rolling(lookback).max().to_numpy()
    return sup, res


def _fib_level(start: float, end: float, ratio: float) -> float:
    """
    Direction-safe Fibonacci retracement level for a swing.

    `start` and `end` can be (low->high) or (high->low).
    """
    return float(end) - (float(end) - float(start)) * float(ratio)


def _pivot_flags(series: pd.Series, left: int, right: int, kind: str) -> np.ndarray:
    """
    Pivot definition (fractal-style), computed offline but intended to be used only after confirmation:
    - Pivot high at i if High[i] is the max of [i-left .. i+right]
    - Pivot low  at i if Low[i]  is the min of [i-left .. i+right]
    """
    if left < 1 or right < 1:
        raise ValueError("pivot left/right must be >= 1")
    window = left + right + 1
    if kind == "high":
        roll = series.rolling(window, center=True).max()
        flags = (series == roll).fillna(False)
    elif kind == "low":
        roll = series.rolling(window, center=True).min()
        flags = (series == roll).fillna(False)
    else:
        raise ValueError("kind must be 'high' or 'low'")
    return flags.to_numpy(dtype=bool)


def _compute_fib_from_confirmed_pivots(
    df: pd.DataFrame,
    *,
    left: int = 2,
    right: int = 2,
    ratios: Tuple[float, ...] = (0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0),
) -> Dict[str, np.ndarray]:
    """
    Compute stepwise Fibonacci levels based on the last *confirmed* swing pivots.

    Anti-lookahead:
    - A pivot at index i is only usable starting at index (i + right).
    - Levels only update when a new opposite-type pivot becomes confirmed.
    """
    n = len(df)
    if n <= 0:
        return {}

    high = df["High"]
    low = df["Low"]

    ph = _pivot_flags(high, left=left, right=right, kind="high")
    pl = _pivot_flags(low, left=left, right=right, kind="low")

    start_arr = np.full(n, np.nan, dtype=float)
    end_arr = np.full(n, np.nan, dtype=float)
    dir_arr = np.zeros(n, dtype=float)  # 1=up, -1=down, 0=unknown

    level_arrs: Dict[str, np.ndarray] = {}
    for r in ratios:
        # keep keys stable; avoid scientific formatting
        r_key = str(float(r)).rstrip("0").rstrip(".")
        level_arrs[r_key] = np.full(n, np.nan, dtype=float)

    prev_type: Optional[str] = None  # "high" or "low"
    prev_price: float = float("nan")
    swing_start: float = float("nan")
    swing_end: float = float("nan")

    for t in range(n):
        idx = t - right
        if idx >= 0:
            # Process low first, then high, for determinism if both happen at same idx.
            if pl[idx]:
                p = float(low.iloc[idx])
                if prev_type is None:
                    prev_type, prev_price = "low", p
                elif prev_type == "low":
                    # Keep the more extreme low for stability
                    prev_price = min(prev_price, p) if np.isfinite(prev_price) else p
                else:
                    swing_start, swing_end = prev_price, p
                    prev_type, prev_price = "low", p

            if ph[idx]:
                p = float(high.iloc[idx])
                if prev_type is None:
                    prev_type, prev_price = "high", p
                elif prev_type == "high":
                    # Keep the more extreme high for stability
                    prev_price = max(prev_price, p) if np.isfinite(prev_price) else p
                else:
                    swing_start, swing_end = prev_price, p
                    prev_type, prev_price = "high", p

        if np.isfinite(swing_start) and np.isfinite(swing_end):
            start_arr[t] = swing_start
            end_arr[t] = swing_end
            if swing_end > swing_start:
                dir_arr[t] = 1.0
            elif swing_end < swing_start:
                dir_arr[t] = -1.0
            else:
                dir_arr[t] = 0.0
            for r in ratios:
                r_key = str(float(r)).rstrip("0").rstrip(".")
                level_arrs[r_key][t] = _fib_level(swing_start, swing_end, r)

    out: Dict[str, np.ndarray] = {
        "start": start_arr,
        "end": end_arr,
        "dir": dir_arr,
    }
    out.update(level_arrs)
    # Convenience alias
    if "0.5" in level_arrs:
        out["mid"] = level_arrs["0.5"]
    return out


def compute_indicator_map(df: pd.DataFrame, indicators: List[Any]) -> Dict[str, np.ndarray]:
    """Compute indicator arrays for a given timeframe."""
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    vol = df["Volume"]
    ind_map: Dict[str, np.ndarray] = {}

    # Regime detection (always available)
    ema200 = close.ewm(span=200, adjust=False).mean()
    slope = ema200 - ema200.shift(5)
    ind_map["regime_up"] = (slope > 0).astype(float).to_numpy()
    ind_map["regime_down"] = (slope < 0).astype(float).to_numpy()

    # Volume context (always available)
    vol_sma20 = vol.rolling(20).mean()
    vol_sma50 = vol.rolling(50).mean()
    ind_map["vol_sma20"] = vol_sma20.to_numpy()
    ind_map["vol_sma50"] = vol_sma50.to_numpy()
    # Ratios to detect spikes without hardcoding threshold in code; rules can use gt
    safe_sma20 = vol_sma20.replace(0, np.nan)
    safe_sma50 = vol_sma50.replace(0, np.nan)
    ind_map["vol_ratio20"] = (vol / safe_sma20).fillna(0).to_numpy()
    ind_map["vol_ratio50"] = (vol / safe_sma50).fillna(0).to_numpy()

    for ind in indicators:
        try:
            if ind.type == "SMA":
                p = ind.period or 14
                ind_map[ind.id] = _sma(close, p)
            elif ind.type == "EMA":
                p = ind.period or 14
                ind_map[ind.id] = _ema(close, p)
            elif ind.type == "RSI":
                p = ind.period or 14
                ind_map[ind.id] = _rsi(close, p)
            elif ind.type == "ATR":
                p = ind.period or 14
                ind_map[ind.id] = _atr(df, p)
            elif ind.type == "MACD":
                f = ind.periodFast or 12
                s = ind.periodSlow or 26
                sig = ind.period or 9
                res = _macd(close, f, s, sig)
                for k, arr in res.items():
                    ind_map[f"{ind.id}.{k}"] = arr
            elif ind.type == "BOLL":
                p = ind.period or 20
                sd = ind.stdDev or 2.0
                res = _boll(close, p, sd)
                for k, arr in res.items():
                    ind_map[f"{ind.id}.{k}"] = arr
            elif ind.type == "FIB":
                # Pivot-based fib levels (confirmed pivots to avoid lookahead).
                # period -> left, period2 -> right
                left = ind.period or 2
                right = ind.period2 or left
                fib = _compute_fib_from_confirmed_pivots(df, left=left, right=right)
                for k, arr in fib.items():
                    ind_map[f"{ind.id}.{k}"] = arr
        except Exception as e:
            logger.error(f"Indicator {ind.id} failed: {e}")

    sup, res = _support_resistance(high, low, lookback=20)
    ind_map["sr_lower"] = sup
    ind_map["sr_upper"] = res
    return ind_map


def _get_val(source: Any, idx: int, ind_map: Dict[str, np.ndarray], df: pd.DataFrame) -> float:
    if isinstance(source, (int, float)):
        return float(source)
    if source is None:
        return 0.0
    key = str(source)
    if key in ("price", "close"):
        return float(df["Close"].iloc[idx])
    if key == "open":
        return float(df["Open"].iloc[idx])
    if key == "high":
        return float(df["High"].iloc[idx])
    if key == "low":
        return float(df["Low"].iloc[idx])
    if key == "volume":
        return float(df["Volume"].iloc[idx])
    if key in ind_map:
        arr = ind_map[key]
        if 0 <= idx < len(arr):
            return float(arr[idx])
    # dotted names already handled above
    try:
        return float(key)
    except Exception:
        return 0.0


def _norm_fib_level(level: Any) -> Optional[str]:
    """
    Normalize fib level input to match keys in ind_map:
    - Accept "0.618", 0.618, "61.8" (percent), etc.
    - Return string like "0.618", "0.5", "1", "1.618".
    """
    if level is None:
        return None
    s = str(level).strip()
    if not s:
        return None
    try:
        v = float(s)
    except Exception:
        return None
    # Allow percent-style input (e.g., 61.8 -> 0.618)
    if v > 2.5 and v <= 100.0:
        v = v / 100.0
    # stable formatting (avoid scientific)
    return str(float(v)).rstrip("0").rstrip(".")


def _eval_cond(cond: RuleCond, idx: int, ind_map: Dict[str, np.ndarray], df: pd.DataFrame) -> bool:
    if cond.op == "all":
        return bool(cond.of) and all(_eval_cond(c, idx, ind_map, df) for c in cond.of or [])
    if cond.op == "any":
        return bool(cond.of) and any(_eval_cond(c, idx, ind_map, df) for c in cond.of or [])

    if idx <= 0 and cond.op in ("crossOver", "crossUnder"):
        return False

    left_now = _get_val(cond.left, idx, ind_map, df)
    right_now = _get_val(cond.right, idx, ind_map, df)

    if cond.op == "gt":
        return left_now > right_now
    if cond.op == "lt":
        return left_now < right_now
    if cond.op == "gte":
        return left_now >= right_now
    if cond.op == "lte":
        return left_now <= right_now
    if cond.op == "between":
        mn = cond.min if cond.min is not None else -np.inf
        mx = cond.max if cond.max is not None else np.inf
        return mn <= left_now <= mx
    if cond.op == "crossOver":
        left_prev = _get_val(cond.left, idx - 1, ind_map, df)
        right_prev = _get_val(cond.right, idx - 1, ind_map, df)
        return crossover([left_prev, left_now], [right_prev, right_now])
    if cond.op == "crossUnder":
        left_prev = _get_val(cond.left, idx - 1, ind_map, df)
        right_prev = _get_val(cond.right, idx - 1, ind_map, df)
        return crossover([right_prev, right_now], [left_prev, left_now])
    if cond.op == "touchUpperBand":
        upper = _get_val(cond.right or "sr_upper", idx, ind_map, df)
        return left_now >= upper
    if cond.op == "touchLowerBand":
        lower = _get_val(cond.right or "sr_lower", idx, ind_map, df)
        return left_now <= lower
    if cond.op in ("fibAtOrAbove", "fibAtOrBelow"):
        # Prefer explicit fields (id + level). Fallback: if right is str, treat as fib id.
        fib_id = str(cond.id or "").strip()
        if not fib_id and isinstance(cond.right, str):
            fib_id = str(cond.right).strip()
        if not fib_id:
            fib_id = "fib"
        level_key = _norm_fib_level(cond.level)
        if not level_key:
            return False
        fib_key = f"{fib_id}.{level_key}"
        if fib_key not in ind_map:
            return False
        fib_val = _get_val(fib_key, idx, ind_map, df)
        if cond.op == "fibAtOrAbove":
            return left_now >= fib_val
        return left_now <= fib_val
    return False


def _all_conds(conds: Optional[List[RuleCond]], idx: int, ind_map: Dict[str, np.ndarray], df: pd.DataFrame) -> bool:
    if not conds:
        return False
    return all(_eval_cond(c, idx, ind_map, df) for c in conds)


def _build_entry_masks(
    df_analysis: pd.DataFrame,
    df_confirm: Optional[pd.DataFrame],
    ind_map_analysis: Dict[str, np.ndarray],
    ind_map_confirm: Optional[Dict[str, np.ndarray]],
    rule_set: Any,
    confirm_rule_set: Optional[Any],
    confirm_tf_ms: Optional[int],
    confirm_window_bars: int,
) -> Tuple[List[bool], List[bool]]:
    n = len(df_analysis)
    long_mask = [False] * n
    short_mask = [False] * n
    confirm_enabled = df_confirm is not None and confirm_rule_set is not None and confirm_tf_ms is not None

    for i in range(n):
        ts = df_analysis.index[i]

        # LONG
        if rule_set.entryLong and _all_conds(rule_set.entryLong, i, ind_map_analysis, df_analysis):
            if confirm_enabled and confirm_rule_set.confirmLong:
                until = ts + pd.Timedelta(milliseconds=confirm_tf_ms * confirm_window_bars)
                df_slice = df_confirm.loc[(df_confirm.index >= ts) & (df_confirm.index <= until)]
                ok = False
                for t in df_slice.index:
                    idx_c = df_confirm.index.get_loc(t)
                    if _all_conds(confirm_rule_set.confirmLong, idx_c, ind_map_confirm, df_confirm):  # type: ignore
                        ok = True
                        break
                long_mask[i] = ok
            else:
                long_mask[i] = True

        # SHORT
        if rule_set.entryShort and _all_conds(rule_set.entryShort, i, ind_map_analysis, df_analysis):
            if confirm_enabled and confirm_rule_set.confirmShort:
                until = ts + pd.Timedelta(milliseconds=confirm_tf_ms * confirm_window_bars)
                df_slice = df_confirm.loc[(df_confirm.index >= ts) & (df_confirm.index <= until)]
                ok = False
                for t in df_slice.index:
                    idx_c = df_confirm.index.get_loc(t)
                    if _all_conds(confirm_rule_set.confirmShort, idx_c, ind_map_confirm, df_confirm):  # type: ignore
                        ok = True
                        break
                short_mask[i] = ok
            else:
                short_mask[i] = True

    return long_mask, short_mask


def _to_output(stats: pd.Series, pair: str, schema: DSLStrategy) -> Dict[str, Any]:
    trades_df = stats._trades if hasattr(stats, "_trades") else pd.DataFrame()
    trades = trades_df.to_dict("records") if not trades_df.empty else []
    loss_trades = trades_df[trades_df.PnL < 0].to_dict("records") if not trades_df.empty else []

    initial_cash = float(stats.get("Equity Initial [$]", 100000.0) if hasattr(stats, "get") else 100000.0)
    final_cash = float(stats.get("Equity Final [$]", initial_cash))

    # Directional stats
    long_trades_df = trades_df[trades_df.Size > 0] if not trades_df.empty else pd.DataFrame()
    short_trades_df = trades_df[trades_df.Size < 0] if not trades_df.empty else pd.DataFrame()
    long_wr = float((long_trades_df.PnL > 0).mean() * 100) if not long_trades_df.empty else 0.0
    short_wr = float((short_trades_df.PnL > 0).mean() * 100) if not short_trades_df.empty else 0.0
    long_tr = int(len(long_trades_df)) if not long_trades_df.empty else 0
    short_tr = int(len(short_trades_df)) if not short_trades_df.empty else 0

    return {
        "meta": {"symbol": pair, "strategyId": schema.id, "strategyName": schema.name},
        "stats": {
            "initialBalance": initial_cash,
            "finalBalance": final_cash,
            "netProfit": final_cash - initial_cash,
            "winRate": float(stats.get("Win Rate [%]", 0.0)),
            "totalTrades": int(stats.get("# Trades", 0)),
            "returnPct": float(stats.get("Return [%]", 0.0)),
            "longWinRate": long_wr,
            "longTrades": long_tr,
            "shortWinRate": short_wr,
            "shortTrades": short_tr,
        },
        "trades": trades,
        "lossTrades": loss_trades,
    }


async def backtest_strategy(strategy: DSLStrategy, pair: str, *, timeframe: Optional[str] = None) -> Dict[str, Any]:
    """
    Run a 1-year backtest for the pair using cached data. If data missing, returns empty result.
    Supports optional multi-timeframe confirmation: strategy.confirmRuleSet + analysisTimeframe + confirmTimeframe.
    """
    if strategy.mode not in ("SCALPING", "INTRADAY"):
        raise ValueError("Mode harus SCALPING atau INTRADAY (tidak mendukung SWING).")

    analysis_tf = strategy.analysisTimeframe or strategy.preferredTimeframe or timeframe or "1h"
    confirm_tf = strategy.confirmTimeframe if strategy.confirmRuleSet else None

    df_analysis = load_cached(pair, analysis_tf, days=DEFAULT_DAYS)
    if df_analysis.empty:
        logger.warning(f"No cached data for {pair} {analysis_tf}. Run /getalldata first.")
        return {
            "meta": {"symbol": pair, "strategyId": strategy.id, "strategyName": strategy.name},
            "stats": {
                "initialBalance": 1000.0,
                "finalBalance": 1000.0,
                "netProfit": 0.0,
                "winRate": 0.0,
                "totalTrades": 0,
                "returnPct": 0.0,
            },
            "trades": [],
            "lossTrades": [],
        }

    df_analysis = df_analysis.rename(columns={"Open": "Open", "High": "High", "Low": "Low", "Close": "Close", "Volume": "Volume"})
    df_analysis = df_analysis[["Open", "High", "Low", "Close", "Volume"]].dropna()
    df_analysis.index.name = "Date"

    df_confirm: Optional[pd.DataFrame] = None
    ind_map_confirm: Optional[Dict[str, np.ndarray]] = None
    confirm_tf_ms: Optional[int] = None
    confirm_window = strategy.confirmWindowBars or 5

    if confirm_tf:
        if confirm_tf not in TIMEFRAMES:
            logger.warning(f"Confirm timeframe {confirm_tf} not in supported set; skipping confirm.")
        else:
            df_confirm = load_cached(pair, confirm_tf, days=DEFAULT_DAYS)
            if df_confirm.empty:
                logger.warning(f"No cached data for {pair} {confirm_tf}; skipping confirm.")
                df_confirm = None
            else:
                df_confirm = df_confirm.rename(columns={"Open": "Open", "High": "High", "Low": "Low", "Close": "Close", "Volume": "Volume"})
                df_confirm = df_confirm[["Open", "High", "Low", "Close", "Volume"]].dropna()
                df_confirm.index.name = "Date"
                confirm_tf_ms = _tf_to_ms(confirm_tf)

    ind_map_analysis = compute_indicator_map(df_analysis, strategy.indicators)
    if df_confirm is not None:
        ind_map_confirm = compute_indicator_map(df_confirm, strategy.indicators)

    entry_long_mask, entry_short_mask = _build_entry_masks(
        df_analysis,
        df_confirm,
        ind_map_analysis,
        ind_map_confirm,
        strategy.ruleSet,
        strategy.confirmRuleSet,
        confirm_tf_ms,
        confirm_window,
    )

    # Import backtesting runtime lazily so non-backtest utilities (screening/indicators)
    # don't require heavy plotting deps like `bokeh`.
    try:
        from backtesting import Backtest as BT  # type: ignore
        from backtesting import Strategy as BTStrategy  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "Backtest runtime unavailable. Install missing dependencies (usually `bokeh`) in your venv:\n"
            "  python -m pip install bokeh\n"
            "Or reinstall requirements:\n"
            "  python -m pip install -r requirements.txt -r requirements_dewan_ai.txt"
        ) from e

    class Adapter(BTStrategy):
        def init(self):
            self._ind_map = ind_map_analysis
            self._df = df_analysis
            self._entry_long_mask = entry_long_mask
            self._entry_short_mask = entry_short_mask
            self._rule_set = strategy.ruleSet
            self._bar_idx = -1  # will increment each next()
            self._entry_idx: Optional[int] = None

        def _atr_for_sl(self, idx: int) -> float:
            for key in self._ind_map:
                if "atr" in key.lower():
                    val = float(self._ind_map[key][idx])
                    if val > 0:
                        return abs(val)
            return float(self.data.Close[idx]) * 0.01

        def _size_and_brackets(self, direction: str, idx: int):
            price = float(self.data.Close[idx])
            equity = getattr(self, "equity", 100000)
            atr = abs(self._atr_for_sl(idx))
            sl_mult = strategy.backtestParams.atrStopMult
            tp_mult = strategy.backtestParams.atrTakeMult

            # Full-notional sizing: allocate all equity to the position
            units = equity / price if price > 0 else 0
            units = int(units)
            if units <= 0:
                return 0.0, None, None

            sl_dist = atr * sl_mult if atr > 0 else price * 0.01

            if direction == "long":
                sl = price - sl_dist
                tp = price + atr * tp_mult
                if not (0 < sl < price < tp):
                    sl, tp = None, None
            else:
                sl = price + sl_dist
                tp = price - atr * tp_mult
                if not (0 < tp < price < sl):
                    sl, tp = None, None
            return units, sl, tp

        def _exit_hit(self, idx: int, conds: Optional[List[RuleCond]]) -> bool:
            if not conds:
                return False
            return all(_eval_cond(c, idx, self._ind_map, self._df) for c in conds)

        def next(self):
            self._bar_idx += 1
            idx = self._bar_idx  # current bar index in full data
            # Exit logic: rely on SL/TP only (no rule-based premature exits)

            # Entry logic based on precomputed masks
            if not self.position:
                if idx < len(self._entry_long_mask) and self._entry_long_mask[idx]:
                    size, sl, tp = self._size_and_brackets("long", idx)
                    if size <= 0:
                        return
                    try:
                        self.buy(size=size, sl=sl, tp=tp)
                        self._entry_idx = idx
                    except ValueError:
                        pass
                elif idx < len(self._entry_short_mask) and self._entry_short_mask[idx] and strategy.backtestParams.allowShort:
                    size, sl, tp = self._size_and_brackets("short", idx)
                    if size <= 0:
                        return
                    try:
                        self.sell(size=size, sl=sl, tp=tp)
                        self._entry_idx = idx
                    except ValueError:
                        pass

    BTClass = BT
    cash_amount = 100_000_000.0
    bt = BTClass(
        df_analysis,
        Adapter,
        cash=cash_amount,  # higher cash to avoid price>>cash issues; size is fractional
        commission=0.0,
        trade_on_close=False,
        exclusive_orders=True,
        hedging=strategy.backtestParams.allowShort,
        finalize_trades=True,
    )
    stats = bt.run()
    return _to_output(stats, pair, strategy)
