import pandas as pd

from bot import strategy

from .helpers import (BASE, BREAKOUT, CFG, OVERHEAD, PULLBACK, STAGE2_SETUP, STAGE3, STAGE4,
                      analyzed, ramp, spike)


def pos(w, stop=None, flags=None, weeks_ago=5):
    return {"stop": stop, "entry_date": w.index[-weeks_ago].strftime("%Y-%m-%d"),
            "flags": list(flags or [])}


def test_r_e2_ruptura_confirmada_compra_en_confirmacion_y_en_retroceso():
    setup, reason, _ = strategy.check_entry(analyzed(BREAKOUT, spike(BREAKOUT)), CFG)
    assert setup, reason
    conf, pull = setup["orders"]
    assert (conf["kind"], pull["kind"]) == ("confirmación", "retroceso")
    assert conf["limit"] == 105.04                       # cierre 104 + 1 %
    assert pull["limit"] == 102.01                       # nivel roto 101 + 1 %
    assert setup["stop"] < 101 and "subida libre" in setup["reason"]


def test_r_e3_semanas_despues_solo_queda_el_retroceso():
    setup, reason, _ = strategy.check_entry(analyzed(PULLBACK, spike(PULLBACK, 2)), CFG)
    assert setup, reason
    assert [o["kind"] for o in setup["orders"]] == ["retroceso"]
    assert setup["weeks_ago"] == 2


def test_r_e2_sin_volumen_no_hay_compra():
    setup, reason, hubo = strategy.check_entry(analyzed(BREAKOUT), CFG)
    assert setup is None and hubo and "sin volumen" in reason


def test_r_e2_sin_ruptura_no_hay_compra():
    setup, reason, hubo = strategy.check_entry(analyzed(STAGE2_SETUP), CFG)
    assert setup is None and not hubo and "sin ruptura" in reason


def test_r_e2_ruptura_fallida():
    closes = STAGE2_SETUP + [104, 96.5]
    setup, reason, _ = strategy.check_entry(analyzed(closes, spike(closes, 1)), CFG)
    assert setup is None and "fallida" in reason


def test_r_e3_demasiado_lejos_para_confirmacion():
    closes = STAGE2_SETUP + [110]
    setup, reason, _ = strategy.check_entry(analyzed(closes, spike(closes)), CFG)
    assert setup and [o["kind"] for o in setup["orders"]] == ["retroceso"]


def test_r_e1_no_compra_fuera_de_fase_2():
    for closes in (STAGE3, STAGE4):
        setup, reason, _ = strategy.check_entry(analyzed(closes), CFG)
        assert setup is None and "Fase 2" in reason


def test_r_e4_resistencia_superior_cercana():
    closes = OVERHEAD + [104]
    setup, reason, _ = strategy.check_entry(analyzed(closes, spike(closes)), CFG)
    assert setup is None and "resistencia superior" in reason


def test_r_e1_extendida_sobre_la_media():
    closes = [50] * 60 + ramp(50, 100, 16) + [100, 97, 95, 96, 98, 104]
    setup, reason, _ = strategy.check_entry(analyzed(closes, spike(closes)), CFG)
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
    d = strategy.manage(w, pos(w, stop=50, flags=[]), CFG)
    assert d["action"] == "reduce" and d["fraction"] == 0.5 and "stage3" in d["flags"]
    again = strategy.manage(w, {"stop": d["stop"], "entry_date": "2026-01-01", "flags": d["flags"]}, CFG)
    assert again["action"] == "hold"


def test_r_d2_fuerza_relativa_negativa():
    w = analyzed(STAGE2_SETUP).copy()
    w.loc[w.index[-2:], "mrs"] = -1.0
    d = strategy.manage(w, pos(w, stop=80, flags=[]), CFG)
    assert d["action"] == "reduce" and d["fraction"] == 0.25


def test_r_s3_y_r_s4_el_stop_sube_y_nunca_baja():
    closes = STAGE2_SETUP + ramp(103, 130, 12) + [124, 121, 126, 131, 134]
    w = analyzed(closes)
    d = strategy.manage(w, pos(w, stop=85, flags=[], weeks_ago=17), CFG)
    assert d["stop"] > 85 and d["stop"] < w["close"].iloc[-1]
    alto = strategy.manage(w, pos(w, stop=125, flags=[], weeks_ago=17), CFG)
    assert alto["stop"] == 125


def test_r_w5_analisis_de_la_posicion():
    txt = strategy.describe(analyzed(STAGE3), ["stage3"], CFG)
    assert txt.startswith("Fase 3") and "MM30" in txt and txt.endswith("posición reducida por Fase 3")
    assert strategy.describe(analyzed(STAGE4), [], CFG).startswith("Fase 4: tendencia bajista; precio un")
