"""Universo de valores (R-U1, R-U3). Tickers en formato Yahoo."""
import io
from pathlib import Path

import pandas as pd
import requests

from .config import ROOT

UA = {"User-Agent": "Mozilla/5.0 (weinstein-bot; uso personal)"}
WIKI = {
    "sp500": "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
    "nasdaq100": "https://en.wikipedia.org/wiki/Nasdaq-100",
}
SP500_ALT = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"


def _from_wikipedia(url: str) -> list[str]:
    html = requests.get(url, headers=UA, timeout=30).text
    for t in pd.read_html(io.StringIO(html)):
        cols = [str(c) for c in t.columns]
        for name in ("Symbol", "Ticker"):
            if name in cols and len(t) >= 90:
                return [str(s).strip().replace(".", "-") for s in t[name]]
    raise ValueError("tabla de componentes no encontrada")


def _index(name: str) -> list[str]:
    """Descarga los componentes; si falla, usa la última lista guardada."""
    cache: Path = ROOT / "universe" / f"{name}.txt"
    try:
        try:
            tickers = _from_wikipedia(WIKI[name])
        except Exception:
            if name != "sp500":
                raise
            df = pd.read_csv(io.StringIO(requests.get(SP500_ALT, headers=UA, timeout=30).text))
            tickers = [s.replace(".", "-") for s in df["Symbol"]]
        cache.write_text("\n".join(tickers) + "\n", encoding="utf-8")
        return tickers
    except Exception as exc:
        if cache.exists():
            print(f"  aviso: no se pudo actualizar {name} ({exc}); se usa la lista guardada")
            return cache.read_text(encoding="utf-8").split()
        print(f"  aviso: {name} no disponible ({exc})")
        return []


def build(cfg: dict) -> dict[str, str]:
    """Devuelve {ticker: 'US'|'EU'}."""
    u = cfg["universe"]
    markets: dict[str, str] = {}
    if u.get("stoxx600"):
        for t in pd.read_csv(ROOT / "universe" / "stoxx600.csv")["ticker"]:
            markets[t] = "EU"
    for name in ("sp500", "nasdaq100"):
        if u.get(name):
            for t in _index(name):
                markets[t] = "US"
    for t in u.get("extra") or []:
        markets[t] = "US"
    return markets
