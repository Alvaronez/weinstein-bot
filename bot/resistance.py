"""Pivotes y zonas de resistencia (R-R1..R-R3)."""
import numpy as np
import pandas as pd


def _pivots(values: np.ndarray, k: int, kind: str) -> list[int]:
    """Índices i confirmados: extremo de la ventana [i-k, i+k]."""
    out = []
    for i in range(k, len(values) - k):
        win = values[i - k:i + k + 1]
        if kind == "high" and values[i] == win.max():
            out.append(i)
        if kind == "low" and values[i] == win.min():
            out.append(i)
    return out


def swing_lows(w: pd.DataFrame, k: int) -> list[tuple[pd.Timestamp, float]]:
    """Mínimos de corrección confirmados (fecha, precio)."""
    lows = w["low"].values
    return [(w.index[i], float(lows[i])) for i in _pivots(lows, k, "low")]


def zones_above(w: pd.DataFrame, cfg: dict) -> list[dict]:
    """Zonas de resistencia por encima del último cierre, de la más cercana a la más lejana.

    Cada zona: level (máximo de la zona), touches, age (semanas desde el último toque),
    confirmed (False si solo la forma el máximo reciente sin confirmar).
    """
    c = cfg["resistance"]
    k, tol = c["pivot_window"], c["zone_tolerance"]
    win = w.iloc[-c["lookback_weeks"]:]
    highs = win["high"].values
    n = len(highs)
    close = float(win["close"].iloc[-1])

    points = [(float(highs[i]), i, True) for i in _pivots(highs, k, "high")]
    # Máximo reciente aún sin confirmar (R-R2)
    j = n - k + int(np.argmax(highs[-k:]))
    if all(i != j for _, i, _ in points):
        points.append((float(highs[j]), j, False))

    # Se agrupa de arriba abajo: cada zona la define su máximo y absorbe
    # los máximos menores situados hasta un 'tol' por debajo.
    points = sorted((p for p in points if p[0] > close), reverse=True)   # R-R3
    zones, cur = [], []
    for p in points:
        if cur and p[0] < cur[0][0] * (1 - tol):
            zones.append(cur)
            cur = []
        cur.append(p)
    if cur:
        zones.append(cur)

    out = []
    for z in zones:
        level = max(p[0] for p in z)
        last_idx = max(p[1] for p in z)
        out.append({
            "level": level,
            "touches": len(z),
            "age": n - 1 - last_idx,
            "confirmed": any(p[2] for p in z),
        })
    return sorted(out, key=lambda z: z["level"])
