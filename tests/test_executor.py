import copy

from bot import executor
from bot.broker import DryRun, SimBroker

from .helpers import (BREAKOUT, CFG, OVERHEAD, PULLBACK, STAGE2_SETUP, STAGE3, STAGE4, analyzed,
                      ramp, spike)

TODAY = "2026-11-21"


def empty_state():
    return {"positions": {}, "pending": {}}


def position(sym, qty=100, price=100.0):
    return {"symbol": sym, "qty": float(qty), "avg_entry_price": 90.0, "current_price": price}


def universe():
    over = OVERHEAD + [104]
    data = {"SPY": analyzed(STAGE2_SETUP), "AAA": analyzed(BREAKOUT, spike(BREAKOUT)),
            "BBB": analyzed(over, spike(over)), "CCC": analyzed(STAGE4),
            "DDD": analyzed(BREAKOUT), "SAP.DE": analyzed(BREAKOUT, spike(BREAKOUT))}
    markets = {"AAA": "US", "BBB": "US", "CCC": "US", "DDD": "US", "SAP.DE": "EU"}
    return data, markets


def test_dos_compras_con_stop_asociado_y_descartes_con_motivo():
    broker, state = SimBroker(), empty_state()
    data, markets = universe()
    out = executor.weekly_cycle(broker, data, markets, CFG, state, TODAY)
    buys = [o for o in broker.orders if o["side"] == "buy"]
    assert [(o["symbol"], o["type"], o["limit_price"]) for o in buys] == [
        ("AAA", "limit", 105.04), ("AAA", "limit", 102.01)]             # R-E3
    assert buys[0]["qty"] == buys[1]["qty"] and buys[0]["time_in_force"] == "gtc"
    assert len([o for o in broker.orders if o["status"] == "held" and o["type"] == "stop"]) == 2
    assert state["pending"]["AAA"]["qtys"] == [buys[0]["qty"]] * 2
    motivos = {r["symbol"]: r["reason"] for r in out["rejected"]}       # R-E8
    assert "resistencia superior" in motivos["BBB"] and "sin volumen" in motivos["DDD"]
    assert [s["symbol"] for s in out["europe_signals"]] == ["SAP.DE"]   # R-U3
    assert all(o["symbol"] != "SAP.DE" for o in broker.orders)


def test_r_e6_a_una_posicion_abierta_solo_se_le_anade_el_retroceso_una_vez():
    data = {"SPY": analyzed(STAGE2_SETUP), "AAA": analyzed(PULLBACK, spike(PULLBACK, 2))}
    broker = SimBroker(positions=[position("AAA", 40, 103.0)])
    state = {"positions": {"AAA": {"stop": 91.0, "entry_date": "2026-11-09", "flags": [],
                                   "tranches": 1, "qty": 40.0}}, "pending": {}}
    executor.weekly_cycle(broker, data, {"AAA": "US"}, CFG, state, TODAY)
    buys = [o for o in broker.orders if o["side"] == "buy"]
    assert [(o["type"], o["limit_price"]) for o in buys] == [("limit", 102.01)]
    # la segunda compra se ejecuta: el guardián unifica el stop y ya no se añade más
    broker.orders.clear()
    broker._positions[0]["qty"] = 40.0 + buys[0]["qty"]
    executor.guard_cycle(broker, CFG, state, "2026-11-24")
    (stop,) = broker.orders
    assert stop["type"] == "stop" and stop["qty"] == 40.0 + buys[0]["qty"]
    assert state["positions"]["AAA"]["tranches"] == 2
    executor.weekly_cycle(broker, data, {"AAA": "US"}, CFG, state, "2026-11-28")
    assert not [o for o in broker.orders if o["side"] == "buy"]


def test_r_e7_las_entradas_pendientes_se_renuevan_sin_duplicarse():
    broker, state = SimBroker(), empty_state()
    data, markets = universe()
    executor.weekly_cycle(broker, data, markets, CFG, state, TODAY)
    executor.weekly_cycle(broker, data, markets, CFG, state, TODAY)
    assert len([o for o in broker.orders if o["side"] == "buy"]) == 2


def test_r_e3e_mercado_en_fase_4_no_abre_posiciones():
    broker, state = SimBroker(), empty_state()
    data, markets = universe()
    data["SPY"] = analyzed(STAGE4)
    out = executor.weekly_cycle(broker, data, markets, CFG, state, TODAY)
    assert not broker.orders
    assert any("Fase 4" in r["reason"] for r in out["rejected"])


def test_r_e5_sin_apalancamiento():
    broker, state = SimBroker(equity=100_000, cash=5_000), empty_state()
    data, markets = universe()
    out = executor.weekly_cycle(broker, data, markets, CFG, state, TODAY)
    assert not broker.orders
    assert any(r["reason"] == "liquidez insuficiente" for r in out["rejected"])


def test_r_s5_guardian_pone_el_stop_si_alpaca_rechaza_oto():
    broker, state = SimBroker(reject_oto=True), empty_state()
    data, markets = universe()
    executor.weekly_cycle(broker, data, markets, CFG, state, TODAY)
    assert [o["side"] for o in broker.orders] == ["buy", "buy"]
    stop = state["pending"]["AAA"]["stop"]
    # la compra se ejecuta entre semana
    broker.orders.clear()
    broker._positions.append(position("AAA", 50, 103.0))
    executor.guard_cycle(broker, CFG, state, "2026-11-24")
    (o,) = broker.orders
    assert (o["side"], o["type"], o["qty"], o["stop_price"]) == ("sell", "stop", 50.0, stop)
    assert state["positions"]["AAA"]["entry_date"] == "2026-11-24" and not state["pending"]
    executor.guard_cycle(broker, CFG, state, "2026-11-25")              # idempotente
    assert len(broker.orders) == 1


def test_r_d5_salida_total_en_fase_4():
    broker = SimBroker(positions=[position("CCC", 100, 60.0)])
    state = {"positions": {"CCC": {"stop": 50.0, "entry_date": "2026-01-02", "flags": []}},
             "pending": {}}
    broker.submit({"symbol": "CCC", "qty": "100", "side": "sell", "type": "stop",
                   "stop_price": "50", "time_in_force": "gtc"})
    data, markets = universe()
    out = executor.weekly_cycle(broker, data, markets, CFG, state, TODAY)
    sells = [o for o in broker.orders if o["symbol"] == "CCC"]
    assert [(o["type"], o["qty"]) for o in sells] == [("market", 100.0)]
    assert out["decisions"][0]["action"] == "Salida total"


def test_r_d1_y_r_d6_reduccion_y_stop_por_el_resto():
    broker = SimBroker(positions=[position("DDD", 100, 100.0)])
    state = {"positions": {"DDD": {"stop": 60.0, "entry_date": "2026-01-02", "flags": []}},
             "pending": {}}
    broker.submit({"symbol": "DDD", "qty": "100", "side": "sell", "type": "stop",
                   "stop_price": "60", "time_in_force": "gtc"})
    data = {"SPY": analyzed(STAGE2_SETUP), "DDD": analyzed(STAGE3)}
    executor.weekly_cycle(broker, data, {}, CFG, state, TODAY)
    got = sorted((o["type"], o["qty"]) for o in broker.orders)
    assert got == [("market", 50.0), ("stop", 50.0)]
    stop = next(o for o in broker.orders if o["type"] == "stop")
    assert stop["stop_price"] >= 60.0                                   # R-S4
    assert "stage3" in state["positions"]["DDD"]["flags"]


def test_r_s2_stop_de_seguimiento_se_recoloca():
    closes = STAGE2_SETUP + ramp(103, 130, 12) + [124, 121, 126, 131, 134]
    broker = SimBroker(positions=[position("EEE", 80, 134.0)])
    state = {"positions": {"EEE": {"stop": 85.0, "entry_date": "2026-07-31", "flags": []}},
             "pending": {}}
    broker.submit({"symbol": "EEE", "qty": "80", "side": "sell", "type": "stop",
                   "stop_price": "85", "time_in_force": "gtc"})
    data = {"SPY": analyzed(STAGE2_SETUP), "EEE": analyzed(closes)}
    executor.weekly_cycle(broker, data, {}, CFG, state, TODAY)
    (o,) = broker.orders
    assert o["type"] == "stop" and o["qty"] == 80.0 and 85 < o["stop_price"] < 134
    assert state["positions"]["EEE"]["stop"] == o["stop_price"]


def test_r_x2_dry_run_no_envia_nada():
    inner = SimBroker()
    data, markets = universe()
    executor.weekly_cycle(DryRun(inner), data, markets, CFG, empty_state(), TODAY)
    assert not inner.orders


def test_r_x4_un_error_no_detiene_el_ciclo():
    broker = SimBroker(positions=[position("ZZZ"), position("DDD")])
    state = empty_state()
    data = {"SPY": analyzed(STAGE2_SETUP), "ZZZ": analyzed(STAGE2_SETUP).drop(columns=["low"]),
            "DDD": analyzed(STAGE2_SETUP)}
    out = executor.weekly_cycle(broker, data, {}, CFG, state, TODAY)
    actions = {d["symbol"]: d["action"] for d in out["decisions"]}
    assert actions == {"ZZZ": "Error", "DDD": "Mantener"}
