"""Ciclo semanal: analizar, decidir y dejar las órdenes colocadas con el mercado cerrado.

    python -m bot.run_weekly            ejecución real contra Alpaca
    python -m bot.run_weekly --dry-run  calcula y muestra, no envía nada (R-X2)
"""
import argparse
import datetime as dt
import json
import os
import sys

from . import config, data, executor, report, strategy, universe
from .broker import AlpacaBroker, DryRun, SimBroker, to_yahoo


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="ejecutar aunque el mercado esté abierto")
    ap.add_argument("--limit", type=int, help="analizar solo los N primeros valores (pruebas)")
    args = ap.parse_args(argv)

    cfg = config.load()
    today = dt.date.today()
    state_dir = config.ROOT / "state"
    state = executor.load_state(state_dir)

    if os.environ.get("ALPACA_API_KEY"):
        broker = AlpacaBroker(cfg["alpaca"]["base_url"])
    elif args.dry_run:
        print("Sin claves de Alpaca: se simula una cuenta vacía de 100.000 $")
        broker = SimBroker()
    else:
        sys.exit("Faltan ALPACA_API_KEY / ALPACA_SECRET_KEY")
    if broker.is_market_open() and not args.force:   # R-X1
        sys.exit("El mercado está abierto: el ciclo semanal solo se ejecuta con el mercado cerrado")
    if args.dry_run:
        broker = DryRun(broker)

    print("1/4 Universo")
    markets = universe.build(cfg)
    if args.limit:
        markets = dict(list(markets.items())[:args.limit])
    held = [to_yahoo(p["symbol"]) for p in broker.positions()]
    benches = {"US": cfg["benchmark"]["us"], "EU": cfg["benchmark"]["eu"]}
    tickers = sorted(set(markets) | set(held) | set(benches.values()))

    print(f"2/4 Datos de {len(tickers)} valores")
    weekly = {t: data.to_weekly(d, today) for t, d in data.download_daily(tickers).items()}
    if benches["US"] not in weekly:
        sys.exit("No hay datos del índice de referencia; se cancela el ciclo sin tocar nada")

    print("3/4 Análisis y órdenes")
    analyzed = {}
    for t, w in weekly.items():
        if len(w) < cfg["universe"]["min_weeks"]:   # R-U4
            continue
        bench = weekly.get(benches.get(markets.get(t, "US")), weekly[benches["US"]])
        try:
            analyzed[t] = strategy.analyze(w, bench["close"], cfg)
        except Exception as exc:   # R-X4
            print(f"  aviso: {t} omitido ({exc})")
    analysis = executor.weekly_cycle(broker, analyzed, markets, cfg, state, today.isoformat())

    for d in analysis["decisions"]:
        print(f"  {d['symbol']:<7} {d['action']:<16} {d['detail']}")
    print(f"  {len(analysis['rejected'])} candidatos en Fase 2 descartados; "
          f"mercado en {strategy.STAGE_NAMES[analysis['market']['stage']]}")
    if args.dry_run:
        print("Dry-run: no se ha guardado estado ni actualizado la web")
        return

    print("4/4 Estado e informe")
    executor.save_state(state_dir, state)
    (state_dir / "analysis.json").write_text(
        json.dumps(analysis, ensure_ascii=False, indent=1), encoding="utf-8")
    equity = report.record_equity(state_dir, today.isoformat(), broker.account())
    spy = data.adj_close(benches["US"], equity["date"].iloc[0])
    report.build(broker, state, analysis, equity, spy, config.ROOT / "docs" / "data.json")


if __name__ == "__main__":
    main()
