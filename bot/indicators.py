"""Indicadores semanales (R-F1)."""
import pandas as pd


def add_indicators(w: pd.DataFrame, bench_close: pd.Series, cfg: dict) -> pd.DataFrame:
    """w: velas semanales con columnas open, high, low, close, volume."""
    c = cfg["stages"]
    w = w.copy()
    w["sma"] = w["close"].rolling(c["ma_weeks"]).mean()
    w["slope"] = w["sma"] / w["sma"].shift(c["slope_weeks"]) - 1
    rp = w["close"] / bench_close.reindex(w.index).ffill()
    w["mrs"] = (rp / rp.rolling(c["rs_weeks"]).mean() - 1) * 100
    prev_avg = w["volume"].shift(1).rolling(c["vol_weeks"]).mean()
    w["vol_ratio"] = w["volume"] / prev_avg
    return w
