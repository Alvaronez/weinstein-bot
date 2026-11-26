"""Reglas de Weinstein: entradas, tamaño, stops, reducciones y salidas.

Funciones puras: reciben velas semanales ya analizadas y devuelven decisiones.
No conocen el bróker.
"""
import math

import pandas as pd

from .indicators import add_indicators
from .resistance import swing_lows, zones_above
from .stages import classify

STAGE_NAMES = {0: "sin datos", 1: "Fase 1", 2: "Fase 2", 3: "Fase 3", 4: "Fase 4"}


def analyze(w: pd.DataFrame, bench_close: pd.Series, cfg: dict) -> pd.DataFrame:
    return classify(add_indicators(w, bench_close, cfg), cfg)


def snapshot(w: pd.DataFrame) -> dict:
    r = w.iloc[-1]

    def num(x, nd=2):
        return None if pd.isna(x) else round(float(x), nd)

    return {
        "stage": int(r["stage"]),
        "trend_age": int(r["trend_age"]),
        "close": num(r["close"]),
        "sma": num(r["sma"]),
        "slope_pct": num(r["slope"] * 100),
        "mrs": num(r["mrs"]),
        "vol_ratio": num(r["vol_ratio"]),
    }


def round_price(p: float) -> float:
    return round(p, 2) if p >= 1 else round(p, 4)


# ---------------------------------------------------------------- entradas

def check_entry(w: pd.DataFrame, cfg: dict) -> tuple[dict | None, str, bool]:
    """Devuelve (setup, motivo, pasa_filtro_de_fase).

    setup es None si no procede colocar orden; motivo lo explica (R-E8).
    """
    e = cfg["entry"]
    r = w.iloc[-1]
    close, sma = float(r["close"]), float(r["sma"])

    # R-E1 · Fase 2 consolidada
    if r["stage"] != 2:
        return None, f"no está en Fase 2 ({STAGE_NAMES[int(r['stage'])]})", False
    if r["trend_age"] < e["min_weeks_in_stage2"]:
        return None, f"Fase 2 demasiado reciente ({int(r['trend_age'])} sem.)", False
    if pd.isna(r["mrs"]) or r["mrs"] <= 0:
        return None, "fuerza relativa de Mansfield negativa", False
    if close < e["min_price"]:
        return None, "precio por debajo del mínimo", False
    ext = close / sma - 1
    if ext > e["max_extension"]:
        return None, f"extendida un {ext:.0%} sobre la MM30", True

    # R-R · resistencias
    zones = zones_above(w, cfg)
    if not zones:
        return None, "en máximos sin base formada: esperar consolidación", True
    zone = zones[0]
    dist = zone["level"] / close - 1
    if dist > e["max_breakout_distance"]:
        return None, f"resistencia en {zone['level']:.2f}, a un {dist:.1%}: demasiado lejos", True
    valid = zone["touches"] >= 2 or zone["age"] >= cfg["resistance"]["min_base_weeks"]
    if not valid:
        return None, f"máximo reciente en {zone['level']:.2f} sin base formada", True

    entry = round_price(zone["level"] * (1 + e["trigger_buffer"]))
    limit = round_price(entry * (1 + e["limit_buffer"]))

    # R-S1 · stop inicial bajo el mínimo de la base y la MM30
    base_weeks = max(zone["age"], cfg["resistance"]["min_base_weeks"])
    base_low = float(w["low"].iloc[-base_weeks:].min())
    stop = round_price(min(base_low, sma) * (1 - cfg["stops"]["buffer"]))
    risk = entry - stop
    risk_pct = risk / entry
    if risk_pct > e["max_stop_distance"]:
        return None, f"stop a un {risk_pct:.1%} de la entrada: riesgo excesivo", True

    # R-E3c · resistencia superior
    next_res = zones[1]["level"] if len(zones) > 1 else None
    rr = None
    if next_res is not None:
        rr = (next_res - entry) / risk
        if rr < e["min_reward_risk"]:
            return None, (f"resistencia superior en {next_res:.2f}: "
                          f"recorrido/riesgo {rr:.1f} < {e['min_reward_risk']:.0f}"), True

    libre = "subida libre" if next_res is None else f"siguiente resistencia {next_res:.2f} (R/R {rr:.1f})"
    setup = {
        "entry": entry, "limit": limit, "stop": stop,
        "zone": round_price(zone["level"]), "touches": zone["touches"],
        "next_resistance": None if next_res is None else round_price(next_res),
        "reward_risk": None if rr is None else round(rr, 1),
        "risk_pct": round(risk_pct * 100, 1),
        "mrs": round(float(r["mrs"]), 1),
        "trend_age": int(r["trend_age"]),
        "reason": (f"Fase 2 de {int(r['trend_age'])} sem., MRS {r['mrs']:+.1f}; "
                   f"ruptura de {zone['level']:.2f} ({zone['touches']} toques); {libre}"),
    }
    return setup, setup["reason"], True


def position_size(equity: float, entry: float, stop: float, cfg: dict, market_stage: int) -> int:
    """R-E5 y R-E4: tamaño por riesgo, limitado por peso máximo."""
    risk_pct = cfg["risk"]["risk_per_trade"] * (0.5 if market_stage == 3 else 1.0)
    by_risk = equity * risk_pct / (entry - stop)
    by_weight = equity * cfg["risk"]["max_position_pct"] / entry
    return max(0, math.floor(min(by_risk, by_weight)))


# ------------------------------------------------- gestión de la posición

def manage(w: pd.DataFrame, pos: dict, cfg: dict) -> dict:
    """Decide qué hacer con una posición abierta.

    pos: {'stop': float|None, 'entry_date': 'YYYY-MM-DD', 'flags': [..]}
    Devuelve {'action': 'hold'|'reduce'|'exit', 'fraction', 'stop', 'reasons', 'flags'}.
    """
    wk, st = cfg["weakness"], cfg["stops"]
    r = w.iloc[-1]
    close, sma, stage = float(r["close"]), float(r["sma"]), int(r["stage"])
    flags = list(pos.get("flags", []))
    cur_stop = pos.get("stop")
    entry_date = pd.Timestamp(pos["entry_date"])

    # R-D5 · Fase 4: fuera
    if stage == 4:
        return {"action": "exit", "fraction": 1.0, "stop": cur_stop, "flags": flags,
                "reasons": ["Fase 4: cierre bajo la MM30 descendente"]}

    # R-D1..R-D4 · reducciones, cada una una sola vez
    fraction, reasons = 0.0, []
    if stage == 3 and "stage3" not in flags:
        flags.append("stage3")
        fraction = max(fraction, wk["stage3_reduce"])
        reasons.append("entra en Fase 3 (la MM30 se aplana o el precio la pierde)")
    if "volume" not in flags:
        since = w[w.index >= entry_date]
        if len(since):
            flags.append("volume")
            ratio = since["vol_ratio"].iloc[0]
            if not pd.isna(ratio) and ratio < wk["breakout_volume_mult"]:
                fraction = max(fraction, wk["no_volume_reduce"])
                reasons.append(f"ruptura sin volumen ({ratio:.1f}× la media, "
                               f"se exige {wk['breakout_volume_mult']}×)")
    n = wk["rs_negative_weeks"]
    if "rs" not in flags and len(w) >= n and (w["mrs"].iloc[-n:] < 0).all():
        flags.append("rs")
        fraction = max(fraction, wk["rs_negative_reduce"])
        reasons.append(f"MRS negativa {n} semanas seguidas")

    # R-S3, R-S4 · stop de seguimiento, nunca baja
    lows = [p for d, p in swing_lows(w, st["swing_window"])
            if cur_stop is None or d >= entry_date]
    candidate = None
    if lows:
        ref = lows[-1] if stage == 3 else min(lows[-1], sma)
        candidate = ref * (1 - st["buffer"])
    elif cur_stop is None:
        candidate = sma * (1 - st["buffer"])
    new_stop = cur_stop
    if candidate is not None and candidate < close and (cur_stop is None or candidate > cur_stop):
        new_stop = round_price(candidate)
        if cur_stop is not None:
            reasons.append(f"stop subido de {cur_stop:.2f} a {new_stop:.2f}")
    if new_stop is None:  # sin referencia válida por debajo del precio
        new_stop = round_price(close * (1 - st["fallback_pct"]))

    return {"action": "reduce" if fraction > 0 else "hold", "fraction": fraction,
            "stop": new_stop, "flags": flags, "reasons": reasons or ["sin cambios"]}
