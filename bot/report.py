"""Rentabilidad, alfa frente al S&P 500 y generación de docs/data.json (R-W)."""
import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd

MIN_WEEKS_JENSEN = 8
MIN_DAYS_CAGR = 90


def record_equity(state_dir: Path, today: str, acct: dict) -> pd.DataFrame:
    """Añade (o sustituye) la fila del día en equity.csv."""
    path = state_dir / "equity.csv"
    df = pd.read_csv(path) if path.exists() else pd.DataFrame(columns=["date", "equity", "cash"])
    df = df[df["date"] != today]
    df.loc[len(df)] = [today, round(acct["equity"], 2), round(acct["cash"], 2)]
    df = df.sort_values("date").reset_index(drop=True)
    state_dir.mkdir(exist_ok=True)
    df.to_csv(path, index=False)
    return df


def performance(equity: pd.DataFrame, spy: pd.Series) -> dict:
    """equity: columnas date, equity. spy: cierre ajustado indexado por fecha."""
    eq = equity.set_index(pd.to_datetime(equity["date"]))["equity"].astype(float)
    bench = spy.reindex(eq.index.union(spy.index)).ffill().reindex(eq.index)
    bot_idx = eq / eq.iloc[0] * 100
    spy_idx = bench / bench.iloc[0] * 100
    bot_ret, spy_ret = bot_idx.iloc[-1] / 100 - 1, spy_idx.iloc[-1] / 100 - 1
    # CAGR: rentabilidad anualizada. Con poco histórico anualizar engaña, así que se espera.
    days = int((eq.index[-1] - eq.index[0]).days)
    cagr = spy_cagr = None
    if days >= MIN_DAYS_CAGR:
        cagr = (1 + bot_ret) ** (365 / days) - 1
        spy_cagr = (1 + spy_ret) ** (365 / days) - 1

    jensen = beta = None
    wk = pd.DataFrame({"b": bot_idx, "s": spy_idx}).resample("W-FRI").last().dropna().pct_change().dropna()
    if len(wk) >= MIN_WEEKS_JENSEN and wk["s"].var() > 0:
        beta = float(wk["b"].cov(wk["s"]) / wk["s"].var())
        jensen = float((wk["b"].mean() - beta * wk["s"].mean()) * 52)

    def pct(x):
        return None if x is None or np.isnan(x) else round(float(x) * 100, 2)

    return {
        "summary": {
            "start_date": equity["date"].iloc[0], "last_date": equity["date"].iloc[-1],
            "equity": round(float(eq.iloc[-1]), 2), "start_equity": round(float(eq.iloc[0]), 2),
            "return_pct": pct(bot_ret), "spy_return_pct": pct(spy_ret),
            "alpha_pct": pct(bot_ret - spy_ret),
            "jensen_alpha_pct": pct(jensen), "beta": None if beta is None else round(beta, 2),
            "cagr_pct": pct(cagr), "spy_cagr_pct": pct(spy_cagr), "days": days,
            "weeks": int(len(wk)),
        },
        "curve": [{"d": d.strftime("%Y-%m-%d"), "bot": round(float(b), 2),
                   "spy": None if np.isnan(s) else round(float(s), 2)}
                  for d, b, s in zip(eq.index, bot_idx, spy_idx)],
    }


def _order_row(o: dict, state: dict) -> dict:
    sym = o["symbol"]
    if o["side"] == "buy":
        kind = "Compra en retroceso" if "-entp-" in o["client_order_id"] else "Compra tras ruptura confirmada"
        reason = state["pending"].get(sym, {}).get("reason", "")
    elif o["type"] == "stop":
        kind = "Stop de pérdidas"
        reason = ("Se activará si la compra se ejecuta" if o["status"] == "held"
                  else "Protege la posición abierta")
    else:
        kind = "Venta a mercado"
        reason = "Reducción o salida decidida el fin de semana"
    return {"symbol": sym, "kind": kind, "side": o["side"], "qty": o["qty"],
            "stop_price": o["stop_price"], "limit_price": o["limit_price"],
            "status": o["status"], "tif": o["time_in_force"], "reason": reason}


def build(broker, state: dict, analysis: dict, equity: pd.DataFrame, spy: pd.Series, out: Path) -> dict:
    acct = broker.account()
    perf = performance(equity, spy)
    positions = []
    for p in broker.positions():
        st = state["positions"].get(p["symbol"], {})
        value = p["qty"] * p["current_price"]
        positions.append({
            "symbol": p["symbol"], "qty": p["qty"], "avg": round(p["avg_entry_price"], 2),
            "price": round(p["current_price"], 2),
            "pnl_pct": round((p["current_price"] / p["avg_entry_price"] - 1) * 100, 2),
            "weight_pct": round(value / acct["equity"] * 100, 1),
            "stage": st.get("stage"), "stop": st.get("stop"),
            "entry_date": st.get("entry_date"), "flags": st.get("flags", []),
        })
    trades = [{"symbol": o["symbol"], "side": o["side"], "qty": o["filled_qty"],
               "price": o["filled_avg_price"], "date": (o["filled_at"] or "")[:10]}
              for o in broker.closed_orders(100) if o["filled_qty"] > 0][:30]
    data = {
        "updated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "cash": round(acct["cash"], 2),
        **perf,
        "positions": sorted(positions, key=lambda x: -x["weight_pct"]),
        "orders": [_order_row(o, state) for o in broker.open_orders()],
        "trades": trades,
        "analysis": analysis,
    }
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data
