import datetime as dt
import json

import numpy as np
import pandas as pd

from bot import data, report
from bot.broker import SimBroker


def test_r_w1_r_w2_rentabilidad_y_alfa():
    days = pd.bdate_range("2026-01-02", periods=120)
    r = np.random.default_rng(1).normal(0.0005, 0.01, 120)
    spy = pd.Series(100 * np.cumprod(1 + r), index=days)
    # el bot replica al índice (beta 1) y suma un 0,05 % diario
    eq = pd.DataFrame({"date": days.strftime("%Y-%m-%d"),
                       "equity": 100_000 * np.cumprod(1 + r + 0.0005)})
    s = report.performance(eq, spy)["summary"]
    assert s["return_pct"] > s["spy_return_pct"]
    assert abs(s["alpha_pct"] - (s["return_pct"] - s["spy_return_pct"])) < 0.011
    assert abs(s["beta"] - 1) < 0.05
    assert 10 < s["jensen_alpha_pct"] < 16          # ≈ 0,05 % × 5 × 52
    esperado = ((1 + s["return_pct"] / 100) ** (365 / s["days"]) - 1) * 100
    assert abs(s["cagr_pct"] - esperado) < 0.01 and s["cagr_pct"] > s["spy_cagr_pct"]


def test_alfa_de_jensen_necesita_historico():
    eq = pd.DataFrame({"date": ["2026-11-20", "2026-11-23"], "equity": [100_000, 101_000]})
    spy = pd.Series([500.0, 502.5], index=pd.to_datetime(["2026-11-20", "2026-11-23"]))
    s = report.performance(eq, spy)["summary"]
    assert s["return_pct"] == 1.0 and s["spy_return_pct"] == 0.5 and s["alpha_pct"] == 0.5
    assert s["jensen_alpha_pct"] is None and s["cagr_pct"] is None   # 3 días: no se anualiza


def test_r_w4_data_json(tmp_path):
    broker = SimBroker(positions=[{"symbol": "AAA", "qty": 10.0, "avg_entry_price": 100.0,
                                   "current_price": 110.0}])
    broker.submit({"symbol": "AAA", "qty": "10", "side": "sell", "type": "stop",
                   "stop_price": "95", "time_in_force": "gtc"})
    state = {"positions": {"AAA": {"stop": 95.0, "stage": 2, "entry_date": "2026-11-02", "flags": []}},
             "pending": {}}
    eq = report.record_equity(tmp_path, "2026-11-20", broker.account())
    eq = report.record_equity(tmp_path, "2026-11-20", broker.account())   # misma fecha: no duplica
    assert len(eq) == 1
    spy = pd.Series([500.0], index=pd.to_datetime(["2026-11-20"]))
    report.build(broker, state, {}, eq, spy, tmp_path / "data.json")
    d = json.loads((tmp_path / "data.json").read_text(encoding="utf-8"))
    assert d["orders"][0]["kind"] == "Stop de pérdidas en 95,00 $"                 # R-W4
    assert d["positions"][0]["pnl_pct"] == 10.0 and d["summary"]["return_pct"] == 0.0


def test_r_u2_velas_semanales_descartan_la_semana_en_curso():
    days = pd.bdate_range("2026-11-02", "2026-11-25")
    daily = pd.DataFrame({"Open": 1.0, "High": 2.0, "Low": 0.5, "Close": 1.5, "Volume": 10.0}, index=days)
    w = data.to_weekly(daily, dt.date(2026, 11, 25))            # miércoles
    assert w.index[-1] == pd.Timestamp("2026-11-20") and w["volume"].iloc[-1] == 50
    assert data.to_weekly(daily, dt.date(2026, 11, 28)).index[-1] == pd.Timestamp("2026-11-27")


def test_r_w4_texto_de_cada_tipo_de_orden():
    from bot import executor
    from .helpers import BREAKOUT, CFG, STAGE2_SETUP, STAGE3, STAGE4, analyzed, ramp, spike

    trend = STAGE2_SETUP + ramp(103, 130, 12) + [124, 121, 126, 131, 134]
    pos = lambda sym, qty, price: {"symbol": sym, "qty": float(qty), "avg_entry_price": 90.0, "current_price": price}
    broker = SimBroker(positions=[pos("SUBE", 80, 134.0), pos("FLOJA", 100, 100.0), pos("CAE", 10, 60.0)])
    state = {"positions": {s: {"stop": 50.0, "entry_date": "2026-07-31", "flags": []}
                           for s in ("SUBE", "FLOJA", "CAE")}, "pending": {}}
    state["positions"]["SUBE"]["stop"] = 85.0
    data = {"SPY": analyzed(STAGE2_SETUP), "SUBE": analyzed(trend), "FLOJA": analyzed(STAGE3),
            "CAE": analyzed(STAGE4), "NUEVA": analyzed(BREAKOUT, spike(BREAKOUT))}
    out = executor.weekly_cycle(broker, data, {"NUEVA": "US"}, CFG, state, "2026-11-21")
    import re
    semana = {(r["symbol"], re.split(r" (?:a|en) \d", r["kind"])[0]): r for r in out["week_orders"]}
    assert semana[("NUEVA", "Compra tras ruptura confirmada")]["kind"].endswith("a 105,04 $ · stop en 92,22 $")
    assert ("NUEVA", "Compra en retroceso") in semana and ("CAE", "Salida total") in semana
    assert ("FLOJA", "Venta parcial (50 % de la posición)") in semana
    assert semana[("SUBE", "Subir el stop de pérdidas")]["reason"].startswith("Estaba en 85,00 $")
    assert [r["symbol"] for r in out["week_orders"]] == sorted(r["symbol"] for r in out["week_orders"])
    rows = {(r["symbol"], re.split(r" (?:a|en) \d", r["kind"])[0]): r
            for r in (report._order_row(o, state) for o in broker.open_orders())}
    assert rows[("NUEVA", "Compra tras ruptura confirmada")]["kind"].endswith("a 105,04 $")
    assert rows[("NUEVA", "Compra en retroceso")]["kind"].endswith("a 102,01 $")
    assert rows[("FLOJA", "Venta parcial (50 % de la posición)")]["reason"].startswith("entra en Fase 3")
    assert rows[("CAE", "Salida total")]["reason"].startswith("Fase 4")
    sube = rows[("SUBE", "Stop de pérdidas")]
    assert sube["reason"].startswith("Stop subido de 85,00 $ a ") and sube["kind"].endswith(" $")


def test_divisa_del_activo():
    from bot.broker import currency
    assert [currency(t) for t in ("AAPL", "BRK-B", "SAP.DE", "SHEL.L", "NESN.SW", "SAN.MC")] == [
        "$", "$", "€", "p", "CHF", "€"]
