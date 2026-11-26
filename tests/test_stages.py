from .helpers import CFG, STAGE2_SETUP, STAGE3, STAGE4, analyzed, ramp


def test_r_f2_cuatro_fases():
    assert analyzed(STAGE2_SETUP)["stage"].iloc[-1] == 2
    assert analyzed(STAGE3)["stage"].iloc[-1] == 3
    assert analyzed(STAGE4)["stage"].iloc[-1] == 4
    suelo = analyzed(STAGE4 + [60] * 40)
    assert suelo["stage"].iloc[-1] == 1


def test_r_f2_secuencia_completa():
    w = analyzed([50] * 40 + ramp(50, 100, 50) + [100] * 15 + ramp(100, 60, 25) + [60] * 40)
    vistos = [s for i, s in enumerate(w["stage"]) if s and (i == 0 or s != w["stage"].iloc[i - 1])]
    assert vistos == [1, 2, 3, 4, 1]


def test_r_f3_antiguedad_no_se_reinicia_por_una_semana_de_transicion():
    w = analyzed(STAGE2_SETUP)
    assert w["trend_age"].iloc[-1] > 40


def test_r_f1_mansfield_positiva_si_supera_al_indice():
    assert analyzed(STAGE2_SETUP)["mrs"].iloc[-1] > 0
    assert analyzed(STAGE4)["mrs"].iloc[-1] < 0
