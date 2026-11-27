"""Genera docs/demo.json: datos de ejemplo para ver la estructura del panel (…/?demo).

    python -m tools.make_demo
"""
import json

import numpy as np
import pandas as pd

from bot import config, report

R1 = "Fase 2; rompió 101.00 (3 toques) esta semana con 2.5× de volumen; MRS +24.5; subida libre"
R2 = "Fase 2; rompió 48.20 (2 toques) hace 2 sem. con 2.1× de volumen; MRS +12.3; siguiente resistencia 61.40"


def main():
    days = pd.bdate_range(end="2026-11-20", periods=130)
    rng = np.random.default_rng(11)
    r = rng.normal(0.0006, 0.009, len(days))
    spy = pd.Series(500 * np.cumprod(1 + r), index=days)
    equity = pd.DataFrame({"date": days.strftime("%Y-%m-%d"),
                           "equity": 100_000 * np.cumprod(1 + 0.8 * r + rng.normal(0.0005, 0.004, len(days)))})
    perf = report.performance(equity, spy)
    data = {
        "demo": True,
        "updated": "2026-11-21 08:20 UTC",
        "cash": 61_500.0,
        **perf,
        "positions": [
            {"symbol": "EJEMPLO1", "qty": 80, "avg": 101.6, "price": 134.0, "pnl_pct": 31.89, "weight_pct": 10.2,
             "stage": 2, "stop": 108.21, "entry_date": "2026-07-31", "flags": []},
            {"symbol": "EJEMPLO2", "qty": 100, "avg": 92.0, "price": 100.0, "pnl_pct": 8.7, "weight_pct": 9.5,
             "stage": 3, "stop": 97.03, "entry_date": "2026-03-06", "flags": ["stage3"]},
            {"symbol": "EJEMPLO3", "qty": 150, "avg": 49.1, "price": 47.3, "pnl_pct": -3.67, "weight_pct": 6.7,
             "stage": 2, "stop": 43.8, "entry_date": "2026-11-09", "flags": []},
        ],
        "orders": [
            {"symbol": "EJEMPLO4", "kind": "Compra tras ruptura confirmada a 105,04 $", "reason": R1},
            {"symbol": "EJEMPLO4", "kind": "Stop de pérdidas en 92,22 $", "reason": "Se activará si la compra se ejecuta"},
            {"symbol": "EJEMPLO4", "kind": "Compra en retroceso a 102,01 $", "reason": R1},
            {"symbol": "EJEMPLO4", "kind": "Stop de pérdidas en 92,22 $", "reason": "Se activará si la compra se ejecuta"},
            {"symbol": "EJEMPLO1", "kind": "Stop de pérdidas en 108,21 $",
             "reason": "Stop subido de 91,50 $ a 108,21 $"},
            {"symbol": "EJEMPLO2", "kind": "Venta parcial (50 % de la posición)",
             "reason": "entra en Fase 3 (la MM30 se aplana o el precio la pierde)"},
            {"symbol": "EJEMPLO2", "kind": "Stop de pérdidas en 97,03 $", "reason": "Protege la posición abierta"},
            {"symbol": "EJEMPLO5", "kind": "Salida total", "reason": "Fase 4: cierre bajo la MM30 descendente"},
        ],
        "trades": [
            {"date": "2026-11-17", "symbol": "EJEMPLO2", "side": "sell", "qty": 50, "price": 99.4},
            {"date": "2026-11-10", "symbol": "EJEMPLO3", "side": "buy", "qty": 150, "price": 49.1},
            {"date": "2026-11-03", "symbol": "EJEMPLO5", "side": "sell", "qty": 60, "price": 71.25},
        ],
        "analysis": {
            "date": "2026-11-21",
            "market": {"stage": 2},
            "universe_size": 588,
            "decisions": [
                {"symbol": "EJEMPLO4", "action": "Orden de compra",
                 "detail": f"36 títulos por compra: confirmación a 105.04 y retroceso a 102.01; "
                           f"stop de pérdidas 92.22 (con stop asociado). {R1}"},
                {"symbol": "EJEMPLO2", "action": "Reducir 50%",
                 "detail": "venta de 50 títulos: entra en Fase 3 (la MM30 se aplana o el precio la pierde)"},
                {"symbol": "EJEMPLO1", "action": "Mantener",
                 "detail": "stop subido de 91.50 a 108.21; stop colocado"},
            ],
            "rejected": [
                {"symbol": "EJEMPLO6", "market": "US",
                 "reason": "ruptura de 77.40 esta semana sin volumen suficiente (1.1× la media, se exige 2.0×)"},
                {"symbol": "EJEMPLO7", "market": "US",
                 "reason": "resistencia superior en 111.10: recorrido/riesgo 1.0 < 2"},
                {"symbol": "EJEMPLO8", "market": "US",
                 "reason": "ruptura de 65.30 fallida: el precio volvió a perder el nivel"},
            ],
            "reason_counts": {"no está en Fase 2": 301, "sin ruptura de resistencia en las últimas 6 semanas": 198,
                              "fuerza relativa de Mansfield negativa": 82},
            "europe_signals": [
                {"symbol": "EJEMPLO.DE", "entry": 105.04, "stop": 92.22, "mrs": 24.5, "currency": "€"},
                {"symbol": "EJEMPLO.L", "entry": 486.8, "stop": 429.0, "mrs": 12.3, "currency": "p"},
                {"symbol": "EJEMPLO.SW", "entry": 173.5, "stop": 156.0, "mrs": 8.9, "currency": "CHF"},
            ],
        },
    }
    out = config.ROOT / "docs" / "demo.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
