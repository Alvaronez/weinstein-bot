"""Convierte las decisiones de la estrategia en órdenes (ciclo semanal y guardián diario)."""
import json
import math
import uuid
from pathlib import Path

from . import strategy
from .broker import BrokerError, to_alpaca, to_yahoo

PREFIX = "wb"


# ------------------------------------------------------------------ estado

def load_state(state_dir: Path) -> dict:
    def read(name):
        p = state_dir / name
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    return {"positions": read("positions.json"), "pending": read("pending.json")}


def save_state(state_dir: Path, state: dict) -> None:
    state_dir.mkdir(exist_ok=True)
    for name in ("positions", "pending"):
        (state_dir / f"{name}.json").write_text(
            json.dumps(state[name], indent=2, ensure_ascii=False), encoding="utf-8")


def sync_fills(positions: list[dict], state: dict, today: str) -> None:
    """Alinea el estado con el bróker: altas (entradas ejecutadas) y bajas (posiciones cerradas)."""
    held = {p["symbol"] for p in positions}
    for sym in held - set(state["positions"]):
        pend = state["pending"].pop(sym, None)
        state["positions"][sym] = {
            "stop": pend["stop"] if pend else None,
            "entry_date": today,
            "flags": [],
            "reason": pend["reason"] if pend else "posición ya existente en la cuenta",
        }
    for sym in set(state["positions"]) - held:
        del state["positions"][sym]


# ----------------------------------------------------------------- órdenes

def _cid(kind: str, sym: str) -> str:
    return f"{PREFIX}-{kind}-{sym}-{uuid.uuid4().hex[:8]}"


def _cancel_sells(broker, sym: str, orders: list[dict]) -> None:
    ids = [o["id"] for o in orders if o["symbol"] == sym and o["side"] == "sell"]
    for i in ids:
        broker.cancel(i)
    broker.wait_cancelled(ids)


def _sell_market(broker, sym: str, qty: float, kind: str) -> None:
    broker.submit({"symbol": sym, "qty": str(qty), "side": "sell", "type": "market",
                   "time_in_force": "day", "client_order_id": _cid(kind, sym)})


def _place_stop(broker, sym: str, qty: float, stop: float) -> None:
    broker.submit({"symbol": sym, "qty": str(qty), "side": "sell", "type": "stop",
                   "stop_price": str(stop), "time_in_force": "gtc",
                   "client_order_id": _cid("stp", sym)})


def ensure_stop(broker, pos: dict, stop: float, orders: list[dict]) -> tuple[float, str]:
    """R-S2: deja exactamente un sell stop por toda la posición. Devuelve (stop, qué se hizo)."""
    sym, qty = pos["symbol"], pos["qty"]
    stops = [o for o in orders if o["symbol"] == sym and o["side"] == "sell" and o["type"] == "stop"]
    if stops:
        stop = max(stop, max(o["stop_price"] for o in stops))   # R-S4
    if len(stops) == 1 and stops[0]["qty"] == qty and abs(stops[0]["stop_price"] - stop) < 0.005:
        return stop, "stop vigente"
    _cancel_sells(broker, sym, orders)
    if stop >= pos["current_price"]:
        _sell_market(broker, sym, qty, "exit")
        return stop, "precio bajo el stop: venta a mercado"
    _place_stop(broker, sym, qty, stop)
    return stop, "stop colocado"


def _submit_entry(broker, sym: str, qty: int, s: dict) -> str:
    order = {"symbol": sym, "qty": str(qty), "side": "buy", "type": "stop_limit",
             "stop_price": str(s["entry"]), "limit_price": str(s["limit"]),
             "time_in_force": "gtc", "client_order_id": _cid("ent", sym)}
    try:
        broker.submit({**order, "order_class": "oto", "stop_loss": {"stop_price": str(s["stop"])}})
        return "con stop asociado (OTO)"
    except BrokerError:
        # Alpaca puede no admitir OTO con entrada stop: el guardián pondrá el stop (R-S5)
        broker.submit({**order, "client_order_id": _cid("ent", sym)})
        return "stop a cargo del guardián"


# ----------------------------------------------------------- ciclo semanal

def weekly_cycle(broker, analyzed: dict, markets: dict, cfg: dict, state: dict, today: str) -> dict:
    """analyzed: {ticker Yahoo: velas analizadas}; markets: {ticker: 'US'|'EU'}."""
    acct = broker.account()
    positions = broker.positions()
    orders = broker.open_orders()
    sync_fills(positions, state, today)
    decisions, rejected, europe = [], [], []
    reason_counts: dict[str, int] = {}

    # R-E7 · se cancelan las entradas no ejecutadas
    for o in orders:
        if o["side"] == "buy" and o["client_order_id"].startswith(f"{PREFIX}-ent"):
            broker.cancel(o["id"])
    state["pending"] = {}
    orders = [o for o in broker.open_orders() if o["side"] == "sell" and o["status"] != "held"]

    # Posiciones abiertas
    exiting = set()
    for p in positions:
        sym, st = p["symbol"], state["positions"][p["symbol"]]
        try:
            w = analyzed.get(to_yahoo(sym))
            if w is None:
                stop = st["stop"] or strategy.round_price(
                    p["avg_entry_price"] * (1 - cfg["stops"]["fallback_pct"]))
                st["stop"], note = ensure_stop(broker, p, stop, orders)
                decisions.append({"symbol": sym, "action": "Mantener",
                                  "detail": f"sin datos esta semana; {note}"})
                continue
            d = strategy.manage(w, st, cfg)
            st["flags"], st["stop"] = d["flags"], d["stop"]
            st["stage"] = int(w["stage"].iloc[-1])
            why = "; ".join(d["reasons"])
            if d["action"] == "exit":
                _cancel_sells(broker, sym, orders)
                _sell_market(broker, sym, p["qty"], "exit")
                exiting.add(sym)
                decisions.append({"symbol": sym, "action": "Salida total", "detail": why})
                continue
            n = 0
            if d["action"] == "reduce":
                n = max(1, math.floor(p["qty"] * d["fraction"]))
            if 0 < n < p["qty"]:
                _cancel_sells(broker, sym, orders)
                _sell_market(broker, sym, n, "red")
                rest = p["qty"] - n
                if d["stop"] < p["current_price"]:
                    _place_stop(broker, sym, rest, d["stop"])
                else:
                    _sell_market(broker, sym, rest, "exit")
                    exiting.add(sym)
                decisions.append({"symbol": sym, "action": f"Reducir {d['fraction']:.0%}",
                                  "detail": f"venta de {n:g} títulos: {why}"})
            else:
                st["stop"], note = ensure_stop(broker, p, d["stop"], orders)
                decisions.append({"symbol": sym, "action": "Mantener", "detail": f"{why}; {note}"})
        except Exception as exc:  # R-X4
            decisions.append({"symbol": sym, "action": "Error", "detail": str(exc)[:200]})

    # Filtro de mercado (R-E3e, R-E4)
    bench = analyzed.get(cfg["benchmark"]["us"])
    market_stage = int(bench["stage"].iloc[-1]) if bench is not None else 0

    # Candidatos
    setups = []
    for ysym, w in analyzed.items():
        if ysym not in markets:
            continue
        try:
            setup, reason, near = strategy.check_entry(w, cfg)
        except Exception as exc:
            setup, reason, near = None, f"error: {exc}", False
        if setup:
            setups.append({"symbol": to_alpaca(ysym), "market": markets[ysym], **setup})
        elif near:
            rejected.append({"symbol": to_alpaca(ysym), "market": markets[ysym], "reason": reason})
        else:
            key = reason.split(" (")[0]
            reason_counts[key] = reason_counts.get(key, 0) + 1
    setups.sort(key=lambda s: -s["mrs"])   # R-E6

    slots = cfg["risk"]["max_positions"] - (len(positions) - len(exiting))
    budget = acct["cash"]
    held = {p["symbol"] for p in positions}
    for s in setups:
        sym = s["symbol"]
        if s["market"] != "US":
            europe.append(s)
            continue
        if sym in held:
            continue
        if market_stage == 4:
            rejected.append({"symbol": sym, "market": "US",
                             "reason": "S&P 500 en Fase 4: no se abren posiciones"})
            continue
        qty = strategy.position_size(acct["equity"], s["entry"], s["stop"], cfg, market_stage)
        cost = qty * s["limit"]
        if qty < 1:
            rejected.append({"symbol": sym, "market": "US", "reason": "tamaño inferior a 1 título"})
        elif slots <= 0:
            rejected.append({"symbol": sym, "market": "US",
                             "reason": "cartera completa: candidatos con más MRS por delante"})
        elif cost > budget:
            rejected.append({"symbol": sym, "market": "US", "reason": "liquidez insuficiente"})
        else:
            try:
                note = _submit_entry(broker, sym, qty, s)
            except BrokerError as exc:
                rejected.append({"symbol": sym, "market": "US",
                                 "reason": f"orden rechazada por Alpaca: {str(exc)[:120]}"})
                continue
            slots -= 1
            budget -= cost
            state["pending"][sym] = {"stop": s["stop"], "entry": s["entry"], "limit": s["limit"],
                                     "qty": qty, "reason": s["reason"]}
            decisions.append({"symbol": sym, "action": "Orden de compra",
                              "detail": f"{qty} títulos, stop de compra {s['entry']:.2f}, "
                                        f"stop de pérdidas {s['stop']:.2f} ({note}). {s['reason']}"})

    return {
        "date": today,
        "market": {"stage": market_stage,
                   **(strategy.snapshot(bench) if bench is not None else {})},
        "universe_size": len(markets),
        "decisions": decisions,
        "rejected": rejected,
        "reason_counts": reason_counts,
        "europe_signals": europe[:40],
    }


# --------------------------------------------------------- guardián diario

def guard_cycle(broker, cfg: dict, state: dict, today: str) -> list[str]:
    """R-S5: asegura que cada posición tiene su stop. No toma otras decisiones."""
    positions = broker.positions()
    sync_fills(positions, state, today)
    orders = [o for o in broker.open_orders() if o["side"] == "sell" and o["status"] != "held"]
    log = []
    for p in positions:
        st = state["positions"][p["symbol"]]
        if any(o["symbol"] == p["symbol"] and o["type"] == "market" for o in orders):
            log.append(f"{p['symbol']}: venta pendiente de ejecutar, no se toca")
            continue
        stop = st["stop"] or strategy.round_price(
            p["avg_entry_price"] * (1 - cfg["stops"]["fallback_pct"]))
        try:
            st["stop"], note = ensure_stop(broker, p, stop, orders)
        except BrokerError as exc:
            note = f"error: {exc}"
        log.append(f"{p['symbol']}: {note} ({st['stop']})")
    return log
