"""Genera docs/data.json con datos de ejemplo para ver el panel antes de la primera ejecución.

    python -m tools.make_demo
"""
import json

import numpy as np
import pandas as pd

from bot import config, executor, report
from bot.broker import SimBroker
from tests.helpers import CFG, OVERHEAD, STAGE2_SETUP, STAGE3, analyzed, ramp


def main():
    days = pd.bdate_range(end="2026-11-20", periods=130)
    rng = np.random.default_rng(7)
    r = rng.normal(0.0012, 0.009, len(days))
    spy = pd.Series(500 * np.cumprod(1 + r), index=days)
    equity = pd.DataFrame({"date": days.strftime("%Y-%m-%d"),
                           "equity": 100_000 * np.cumprod(1 + 0.8 * r + rng.normal(0.0004, 0.004, len(days))),
                           "cash": 40_000.0})
    last = float(equity["equity"].iloc[-1])
    trend = STAGE2_SETUP + ramp(103, 130, 12) + [124, 121, 126, 131, 134]
    broker = SimBroker(equity=last, cash=40_000, positions=[
        {"symbol": "EJEMPLO1", "qty": 80.0, "avg_entry_price": 101.6, "current_price": 134.0},
        {"symbol": "EJEMPLO2", "qty": 100.0, "avg_entry_price": 92.0, "current_price": 100.0},
    ])
    state = {"positions": {
        "EJEMPLO1": {"stop": 91.5, "entry_date": "2026-07-31", "flags": ["volume"]},
        "EJEMPLO2": {"stop": 84.0, "entry_date": "2026-03-06", "flags": ["volume"]}}, "pending": {}}
    for sym, qty, stop in (("EJEMPLO1", 80, 91.5), ("EJEMPLO2", 100, 84.0)):
        broker.submit({"symbol": sym, "qty": str(qty), "side": "sell", "type": "stop",
                       "stop_price": str(stop), "time_in_force": "gtc"})
    data = {"SPY": analyzed(STAGE2_SETUP), "EJEMPLO1": analyzed(trend), "EJEMPLO2": analyzed(STAGE3),
            "EJEMPLO3": analyzed(STAGE2_SETUP), "EJEMPLO4": analyzed(OVERHEAD),
            "EJEMPLO5": analyzed(STAGE2_SETUP[:-1] + [93]), "EJEMPLO.DE": analyzed(STAGE2_SETUP)}
    markets = {"EJEMPLO3": "US", "EJEMPLO4": "US", "EJEMPLO5": "US", "EJEMPLO.DE": "EU"}
    analysis = executor.weekly_cycle(broker, data, markets, CFG, state, "2026-11-21")
    out = config.ROOT / "docs" / "data.json"
    d = report.build(broker, state, analysis, equity, spy, out)
    d["demo"] = True
    out.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
