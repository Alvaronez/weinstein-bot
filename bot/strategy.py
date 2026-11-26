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

def find_breakout(w: pd.DataFrame, cfg: dict) -> dict | None:
    """Ruptura más reciente de una resistencia válida (R-E2).

    Recorre las últimas semanas y, para cada una, reconstruye las resistencias tal
    como estaban la semana anterior. Hay ruptura si el cierre las supera.
    """
    e, rc = cfg["entry"], cfg["resistance"]
    closes = w["close"].values
    n = len(w)
    for back in range(e["breakout_window_weeks"]):
        b = n - 1 - back
        prior = w.iloc[:b]
        if len(prior) < 40:
            break
        broken = [z for z in zones_above(prior, cfg)
                  if (z["touches"] >= 2 or z["age"] >= rc["min_base_weeks"])
                  and closes[b] > z["level"] * (1 + e["trigger_buffer"])]
        if broken:
            z = max(broken, key=lambda z: z["level"])
            return {"index": b, "weeks_ago": back, "level": z["level"], "touches": z["touches"],
                    "base_weeks": max(z["age"], rc["min_base_weeks"]),
                    "vol_ratio": float(w["vol_ratio"].iloc[b]),
                    "mrs": float(w["mrs"].iloc[b])}
    return None


def check_entry(w: pd.DataFrame, cfg: dict) -> tuple[dict | None, str, bool]:
    """Devuelve (setup, motivo, hubo_ruptura).

    setup es None si no procede colocar órdenes; motivo lo explica (R-E8).
    Un setup lleva una o dos órdenes: compra tras la confirmación y compra en el retroceso.
    """
    e = cfg["entry"]
    r = w.iloc[-1]
    close, sma, stage = float(r["close"]), float(r["sma"]), int(r["stage"])

    # R-E1 · Fase 2, o salida de la base con la MM30 ya girando
    starting = stage == 1 and close > sma and r["slope"] >= 0
    if stage != 2 and not starting:
        return None, f"no está en Fase 2 ({STAGE_NAMES[stage]})", False
    if pd.isna(r["mrs"]) or r["mrs"] <= 0:
        return None, "fuerza relativa de Mansfield negativa", False
    if close < e["min_price"]:
        return None, "precio por debajo del mínimo", False

    # R-E2 · ruptura reciente y confirmada por volumen
    bo = find_breakout(w, cfg)
    if bo is None:
        return None, f"sin ruptura de resistencia en las últimas {e['breakout_window_weeks']} semanas", False
    level, ago = bo["level"], bo["weeks_ago"]
    cuando = "esta semana" if ago == 0 else f"hace {ago} sem."
    if pd.isna(bo["vol_ratio"]) or bo["vol_ratio"] < e["breakout_volume_mult"]:
        return None, (f"ruptura de {level:.2f} {cuando} sin volumen suficiente "
                      f"({bo['vol_ratio']:.1f}× la media, se exige {e['breakout_volume_mult']}×)"), True
    if (w["close"].iloc[bo["index"]:] < level * (1 - e["fail_tolerance"])).any():
        return None, f"ruptura de {level:.2f} fallida: el precio volvió a perder el nivel", True
    ext = close / sma - 1
    if ext > e["max_extension"]:
        return None, f"extendida un {ext:.0%} sobre la MM30", True

    # R-S1 · stop bajo el mínimo de la base y la MM30
    start = max(0, bo["index"] - bo["base_weeks"])
    base_low = float(w["low"].iloc[start:].min())
    stop = round_price(min(base_low, sma) * (1 - cfg["stops"]["buffer"]))

    # R-E3 · dos compras posibles
    orders, notes = [], []
    if ago == 0:
        if close <= level * (1 + e["max_chase"]):
            orders.append({"kind": "confirmación", "limit": round_price(close * (1 + e["confirm_buffer"]))})
        else:
            notes.append(f"cierre un {close / level - 1:.0%} sobre el nivel roto: solo se espera el retroceso")
    orders.append({"kind": "retroceso", "limit": round_price(level * (1 + e["pullback_buffer"]))})

    # R-E4 · resistencias anteriores a la ruptura que queden por encima
    top = max(o["limit"] for o in orders)
    above = [z["level"] for z in zones_above(w, cfg)
             if z["confirmed"] and z["age"] > ago and z["level"] > top]
    next_res = min(above) if above else None

    kept, why = [], ""
    for o in orders:
        risk = o["limit"] - stop
        if risk <= 0 or risk / o["limit"] > e["max_stop_distance"]:
            why = f"stop a un {risk / o['limit']:.1%} de la entrada: riesgo excesivo"
            continue
        if next_res is not None:
            rr = (next_res - o["limit"]) / risk
            if rr < e["min_reward_risk"]:
                why = (f"resistencia superior en {next_res:.2f}: "
                       f"recorrido/riesgo {rr:.1f} < {e['min_reward_risk']:.0f}")
                continue
        kept.append(o)
    if not kept:
        return None, why, True

    libre = "subida libre" if next_res is None else f"siguiente resistencia {next_res:.2f}"
    reason = (f"{STAGE_NAMES[stage]}; rompió {level:.2f} ({bo['touches']} toques) {cuando} con "
              f"{bo['vol_ratio']:.1f}× de volumen; MRS {r['mrs']:+.1f}; {libre}")
    if notes:
        reason += "; " + "; ".join(notes)
    return {
        "orders": kept, "entry": kept[0]["limit"], "stop": stop,
        "zone": round_price(level), "weeks_ago": ago,
        "vol_ratio": round(bo["vol_ratio"], 1), "mrs": round(float(r["mrs"]), 1),
        "next_resistance": None if next_res is None else round_price(next_res),
        "reason": reason,
    }, reason, True


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
