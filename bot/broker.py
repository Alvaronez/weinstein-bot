"""Cliente REST de Alpaca y bróker simulado para tests y --dry-run.

Ambos exponen la misma interfaz y devuelven números ya convertidos a float.
"""
import itertools
import os
import time

import requests


class BrokerError(Exception):
    pass


def to_alpaca(sym: str) -> str:
    return sym.replace("-", ".")   # Yahoo BRK-B → Alpaca BRK.B


def to_yahoo(sym: str) -> str:
    return sym.replace(".", "-")


def _f(x):
    return None if x in (None, "") else float(x)


def _order(o: dict) -> dict:
    return {
        "id": o["id"], "client_order_id": o.get("client_order_id") or "",
        "symbol": o["symbol"], "side": o["side"], "type": o["type"],
        "qty": _f(o.get("qty")), "filled_qty": _f(o.get("filled_qty")) or 0.0,
        "stop_price": _f(o.get("stop_price")), "limit_price": _f(o.get("limit_price")),
        "filled_avg_price": _f(o.get("filled_avg_price")),
        "status": o["status"], "time_in_force": o.get("time_in_force"),
        "submitted_at": o.get("submitted_at"), "filled_at": o.get("filled_at"),
    }


class AlpacaBroker:
    def __init__(self, base_url: str):
        key, secret = os.environ.get("ALPACA_API_KEY"), os.environ.get("ALPACA_SECRET_KEY")
        if not key or not secret:
            raise BrokerError("Faltan ALPACA_API_KEY / ALPACA_SECRET_KEY en el entorno")
        self.base = base_url.rstrip("/")
        self.s = requests.Session()
        self.s.headers.update({"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret})

    def _req(self, method, path, **kw):
        r = self.s.request(method, f"{self.base}{path}", timeout=30, **kw)
        if r.status_code >= 400:
            raise BrokerError(f"{method} {path} → {r.status_code}: {r.text[:300]}")
        return r.json() if r.text else None

    def is_market_open(self) -> bool:
        return bool(self._req("GET", "/v2/clock")["is_open"])

    def account(self) -> dict:
        a = self._req("GET", "/v2/account")
        return {"equity": float(a["equity"]), "cash": float(a["cash"])}

    def positions(self) -> list[dict]:
        return [{"symbol": p["symbol"], "qty": float(p["qty"]),
                 "avg_entry_price": float(p["avg_entry_price"]),
                 "current_price": _f(p.get("current_price")) or float(p["avg_entry_price"])}
                for p in self._req("GET", "/v2/positions")]

    def open_orders(self) -> list[dict]:
        raw = self._req("GET", "/v2/orders", params={"status": "open", "limit": 500, "nested": "false"})
        return [_order(o) for o in raw]

    def closed_orders(self, limit=100) -> list[dict]:
        raw = self._req("GET", "/v2/orders",
                        params={"status": "closed", "limit": limit, "direction": "desc"})
        return [_order(o) for o in raw]

    def submit(self, order: dict) -> dict:
        return _order(self._req("POST", "/v2/orders", json=order))

    def cancel(self, order_id: str) -> None:
        self._req("DELETE", f"/v2/orders/{order_id}")

    def wait_cancelled(self, order_ids: list[str], timeout=15) -> None:
        """Las acciones quedan retenidas hasta que la cancelación se confirma."""
        end = time.time() + timeout
        while order_ids and time.time() < end:
            open_ids = {o["id"] for o in self.open_orders()}
            if not open_ids & set(order_ids):
                return
            time.sleep(1)


class SimBroker:
    """Bróker en memoria. Valida que no se vendan más títulos de los que hay."""

    def __init__(self, equity=100_000.0, cash=None, positions=None, reject_oto=False, market_open=False):
        self._equity, self._cash = equity, equity if cash is None else cash
        self._positions = list(positions or [])
        self.orders: list[dict] = []
        self.reject_oto, self.market_open = reject_oto, market_open
        self._ids = itertools.count(1)

    def is_market_open(self):
        return self.market_open

    def account(self):
        return {"equity": self._equity, "cash": self._cash}

    def positions(self):
        return [dict(p) for p in self._positions]

    def open_orders(self):
        return [dict(o) for o in self.orders]

    def closed_orders(self, limit=100):
        return []

    def submit(self, order: dict) -> dict:
        if order.get("order_class") == "oto" and self.reject_oto:
            raise BrokerError("422: oto no admite entradas stop")
        qty = float(order["qty"])
        if order["side"] == "sell":
            held = sum(o["qty"] for o in self.orders
                       if o["symbol"] == order["symbol"] and o["side"] == "sell" and o["status"] != "held")
            have = sum(p["qty"] for p in self._positions if p["symbol"] == order["symbol"])
            if held + qty > have:
                raise BrokerError(f"403: títulos insuficientes en {order['symbol']}")
        o = {"id": f"sim-{next(self._ids)}", "client_order_id": order.get("client_order_id", ""),
             "symbol": order["symbol"], "side": order["side"], "type": order["type"], "qty": qty,
             "filled_qty": 0.0, "stop_price": _f(order.get("stop_price")),
             "limit_price": _f(order.get("limit_price")), "filled_avg_price": None,
             "status": "new", "time_in_force": order.get("time_in_force"),
             "submitted_at": None, "filled_at": None}
        self.orders.append(o)
        if order.get("order_class") == "oto":
            self.orders.append({**o, "id": f"sim-{next(self._ids)}", "client_order_id": "",
                                "side": "sell", "type": "stop", "limit_price": None, "status": "held",
                                "stop_price": _f(order["stop_loss"]["stop_price"]), "parent": o["id"]})
        return dict(o)

    def cancel(self, order_id):
        self.orders = [o for o in self.orders if o["id"] != order_id and o.get("parent") != order_id]

    def wait_cancelled(self, order_ids, timeout=0):
        return


class DryRun:
    """Envuelve un bróker: lee de verdad, pero no envía ni cancela nada (R-X2)."""

    def __init__(self, inner):
        self.inner = inner
        self.sent: list[dict] = []

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def submit(self, order):
        self.sent.append(order)
        print("  [dry-run] orden no enviada:", order)
        return {"id": f"dry-{len(self.sent)}", **order}

    def cancel(self, order_id):
        print("  [dry-run] cancelación no enviada:", order_id)

    def wait_cancelled(self, order_ids, timeout=0):
        return
