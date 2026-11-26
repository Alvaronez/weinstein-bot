"""Guardián diario: coloca los stops que falten y actualiza la web. No decide nada más (R-S5).

    python -m bot.guard
"""
import datetime as dt
import json

from . import config, data, executor, report
from .broker import AlpacaBroker


def main():
    cfg = config.load()
    today = dt.date.today().isoformat()
    state_dir = config.ROOT / "state"
    state = executor.load_state(state_dir)
    broker = AlpacaBroker(cfg["alpaca"]["base_url"])

    for line in executor.guard_cycle(broker, cfg, state, today):
        print(" ", line)
    executor.save_state(state_dir, state)

    path = state_dir / "analysis.json"
    analysis = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    equity = report.record_equity(state_dir, today, broker.account())
    spy = data.adj_close(cfg["benchmark"]["us"], equity["date"].iloc[0])
    report.build(broker, state, analysis, equity, spy, config.ROOT / "docs" / "data.json")


if __name__ == "__main__":
    main()
