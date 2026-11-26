from bot.resistance import swing_lows, zones_above

from .helpers import CFG, OVERHEAD, STAGE2_SETUP, analyzed, ramp


def test_r_r1_agrupa_los_toques_en_una_zona():
    zones = zones_above(analyzed(STAGE2_SETUP), CFG)
    assert len(zones) == 1
    assert zones[0]["touches"] >= 2 and 100 < zones[0]["level"] < 102


def test_r_r1_detecta_la_resistencia_superior():
    zones = zones_above(analyzed(OVERHEAD), CFG)
    assert len(zones) == 2 and zones[1]["level"] > 110


def test_r_r2_maximo_reciente_no_confirmado():
    w = analyzed([50] * 60 + ramp(50, 100, 50) + [100, 98])
    zones = zones_above(w, CFG)
    assert zones and zones[0]["touches"] == 1 and zones[0]["age"] < 3 and not zones[0]["confirmed"]


def test_r_r3_las_zonas_superadas_no_cuentan():
    w = analyzed(STAGE2_SETUP + [103, 106])
    assert all(z["level"] > 106 for z in zones_above(w, CFG))


def test_minimos_de_correccion():
    lows = swing_lows(analyzed(STAGE2_SETUP), 2)
    assert any(abs(p - 93 * 0.99) < 0.01 for _, p in lows)
