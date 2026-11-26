import pandas as pd

from bot import strategy

from .helpers import BASE, CFG, OVERHEAD, STAGE2_SETUP, STAGE3, STAGE4, analyzed, ramp


def pos(w, stop=None, flags=None, weeks_ago=5):
    return {"stop": stop, "entry_date": w.index[-weeks_ago].strftime("%Y-%m-%d"),
            "flags": list(flags or [])}


def test_r_e2_orden_sobre_la_resistencia_en_fase_2_consolidada():
    setup, reason, _ = strategy.check_entry(analyzed(STAGE2_SETUP), CFG)
    assert setup, reason
    assert setup["entry"] > setup["zone"] > 100
    assert setup["limit"] > setup["entry"] > setup["stop"]
    assert setup["next_resistance"] is None and "subida libre" in setup["reason"]


def test_r_e1_no_compra_fuera_de_fase_2():
    for closes in (STAGE3, STAGE4):
        setup, reason, _ = strategy.check_entry(analyzed(closes), CFG)
        assert setup is None and "Fase 2" in reason


def test_r_e3a_resistencia_demasiado_lejos():
    setup, reason, _ = strategy.check_entry(analyzed(STAGE2_SETUP[:-1] + [93]), CFG)
    assert setup is None and "demasiado lejos" in reason


def test_r_e3b_sin_base_formada():
    setup, reason, _ = strategy.check_entry(analyzed(BASE + [100, 98]), CFG)
    assert setup is None and "sin base" in reason


def test_r_e3c_resistencia_superior_cercana():
    setup, reason, _ = strategy.check_entry(analyzed(OVERHEAD), CFG)
    assert setup is None and "resistencia superior" in reason


def test_r_e1_extendida_sobre_la_media():
    setup, reason, _ = strategy.check_entry(analyzed([50] * 60 + ramp(50, 150, 25)), CFG)
    assert setup is None and "extendida" in reason


def test_r_e5_tamano_por_riesgo_y_peso_maximo():
    assert strategy.position_size(100_000, 100, 90, CFG, 2) == 100     # 1 % / 10 $
    assert strategy.position_size(100_000, 100, 99, CFG, 2) == 100     # tope del 10 %
    assert strategy.position_size(100_000, 100, 90, CFG, 3) == 50      # R-E4


def test_r_d5_salida_en_fase_4():
    w = analyzed(STAGE4)
    assert strategy.manage(w, pos(w, stop=50), CFG)["action"] == "exit"


def test_r_d1_y_r_d4_reduccion_unica_en_fase_3():
    w = analyzed(STAGE3)
    d = strategy.manage(w, pos(w, stop=50, flags=["volume"]), CFG)
    assert d["action"] == "reduce" and d["fraction"] == 0.5 and "stage3" in d["flags"]
    again = strategy.manage(w, {"stop": d["stop"], "entry_date": "2026-01-01", "flags": d["flags"]}, CFG)
    assert again["action"] == "hold"


def test_r_d3_ruptura_sin_volumen():
    closes = STAGE2_SETUP + [103, 104]
    flojo = analyzed(closes)
    d = strategy.manage(flojo, pos(flojo, stop=90, weeks_ago=2), CFG)
    assert d["action"] == "reduce" and "sin volumen" in d["reasons"][0]
    vol = [1e6] * (len(closes) - 2) + [2.5e6, 1e6]
    fuerte = analyzed(closes, vol)
    assert strategy.manage(fuerte, pos(fuerte, stop=90, weeks_ago=2), CFG)["action"] == "hold"


def test_r_d2_fuerza_relativa_negativa():
    w = analyzed(STAGE2_SETUP).copy()
    w.loc[w.index[-2:], "mrs"] = -1.0
    d = strategy.manage(w, pos(w, stop=80, flags=["volume"]), CFG)
    assert d["action"] == "reduce" and d["fraction"] == 0.25


def test_r_s3_y_r_s4_el_stop_sube_y_nunca_baja():
    closes = STAGE2_SETUP + ramp(103, 130, 12) + [124, 121, 126, 131, 134]
    w = analyzed(closes)
    d = strategy.manage(w, pos(w, stop=85, flags=["volume"], weeks_ago=17), CFG)
    assert d["stop"] > 85 and d["stop"] < w["close"].iloc[-1]
    alto = strategy.manage(w, pos(w, stop=125, flags=["volume"], weeks_ago=17), CFG)
    assert alto["stop"] == 125
