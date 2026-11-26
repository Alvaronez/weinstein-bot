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
    assert d["orders"][0]["kind"] == "Stop de pérdidas" and d["orders"][0]["stop_price"] == 95.0
    assert d["positions"][0]["pnl_pct"] == 10.0 and d["summary"]["return_pct"] == 0.0


def test_r_u2_velas_semanales_descartan_la_semana_en_curso():
    days = pd.bdate_range("2026-11-02", "2026-11-25")
    daily = pd.DataFrame({"Open": 1.0, "High": 2.0, "Low": 0.5, "Close": 1.5, "Volume": 10.0}, index=days)
    w = data.to_weekly(daily, dt.date(2026, 11, 25))            # miércoles
    assert w.index[-1] == pd.Timestamp("2026-11-20") and w["volume"].iloc[-1] == 50
    assert data.to_weekly(daily, dt.date(2026, 11, 28)).index[-1] == pd.Timestamp("2026-11-27")
