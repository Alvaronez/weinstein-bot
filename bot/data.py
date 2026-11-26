"""Descarga de datos diarios (Yahoo Finance) y agregación a velas semanales (R-U2)."""
import datetime as dt

import pandas as pd

AGG = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}


def last_complete_friday(today: dt.date) -> dt.date:
    wd = today.weekday()  # lunes = 0
    back = wd - 4 if wd >= 5 else wd + 3
    return today - dt.timedelta(days=back)


def to_weekly(daily: pd.DataFrame, today: dt.date) -> pd.DataFrame:
    """daily: columnas Open/High/Low/Close/Volume. Descarta la semana en curso."""
    d = daily.rename(columns=str.lower)[list(AGG)].dropna(subset=["close"])
    if getattr(d.index, "tz", None) is not None:
        d.index = d.index.tz_localize(None)
    w = d.resample("W-FRI").agg(AGG).dropna(subset=["close"])
    return w[w.index <= pd.Timestamp(last_complete_friday(today))]


def download_daily(tickers: list[str], period="4y", chunk=100) -> dict[str, pd.DataFrame]:
    import yfinance as yf
    out = {}
    for i in range(0, len(tickers), chunk):
        part = tickers[i:i + chunk]
        try:
            df = yf.download(part, period=period, interval="1d", auto_adjust=False,
                             group_by="ticker", threads=True, progress=False)
        except Exception as exc:
            print(f"  aviso: fallo al descargar un bloque ({exc})")
            continue
        for t in part:
            try:
                d = df[t] if isinstance(df.columns, pd.MultiIndex) else df
                d = d.dropna(subset=["Close"])
                if len(d):
                    out[t] = d
            except KeyError:
                pass
    return out


def adj_close(ticker: str, start: str) -> pd.Series:
    """Cierre ajustado por dividendos (rentabilidad total) desde 'start'."""
    import yfinance as yf
    begin = pd.Timestamp(start) - pd.Timedelta(days=7)
    df = yf.download([ticker], start=begin.strftime("%Y-%m-%d"), interval="1d",
                     auto_adjust=True, group_by="ticker", progress=False)
    d = df[ticker] if isinstance(df.columns, pd.MultiIndex) else df
    s = d["Close"].dropna()
    if getattr(s.index, "tz", None) is not None:
        s.index = s.index.tz_localize(None)
    return s
