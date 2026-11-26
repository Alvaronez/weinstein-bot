"""Clasificación en las 4 fases de Weinstein (R-F2, R-F3)."""
import numpy as np
import pandas as pd


def classify(w: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Añade 'stage' (0 = sin datos, 1-4) y 'trend_age' (semanas de la tendencia vigente)."""
    thr = cfg["stages"]["flat_threshold"]
    stages, ages = [], []
    last_trend, age = None, 0
    for close, sma, slope in zip(w["close"].values, w["sma"].values, w["slope"].values):
        if np.isnan(sma) or np.isnan(slope):
            stages.append(0)
            ages.append(0)
            continue
        if slope > thr and close > sma:
            stage = 2
        elif slope < -thr and close < sma:
            stage = 4
        else:
            stage = 3 if last_trend == 2 else 1
        if stage in (2, 4):
            if stage != last_trend:
                last_trend, age = stage, 0
        age += 1
        stages.append(stage)
        ages.append(age)
    w = w.copy()
    w["stage"] = stages
    w["trend_age"] = ages
    return w
