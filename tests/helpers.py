"""Series semanales sintéticas para los tests."""
import numpy as np
import pandas as pd

from bot import config, strategy

CFG = config.load()


def series(closes, volume=1_000_000.0, end="2026-11-20"):
    closes = np.asarray(closes, dtype=float)
    idx = pd.date_range(end=end, periods=len(closes), freq="W-FRI")
    opens = np.r_[closes[0], closes[:-1]]
    vol = np.full(len(closes), volume) if np.isscalar(volume) else np.asarray(volume, dtype=float)
    return pd.DataFrame({"open": opens, "high": np.maximum(opens, closes) * 1.01,
                         "low": np.minimum(opens, closes) * 0.99, "close": closes,
                         "volume": vol}, index=idx)


def ramp(a, b, n):
    return list(np.linspace(a, b, n, endpoint=False))


def analyzed(closes, volume=1_000_000.0):
    w = series(closes, volume)
    bench = pd.Series(100.0, index=w.index)
    return strategy.analyze(w, bench, CFG)


# Suelo, tendencia alcista y consolidación bajo 100 con dos toques
BASE = [50] * 60 + ramp(50, 100, 50)
CONSOLIDATION = [100, 97, 94, 93, 95, 98, 99.5, 97, 95, 96, 97]
STAGE2_SETUP = BASE + CONSOLIDATION

# Lo mismo, pero con un techo previo en 110 dentro de las 104 semanas
OVERHEAD = [110] * 30 + ramp(110, 75, 20) + [75] * 10 + ramp(75, 100, 35) + CONSOLIDATION

STAGE4 = [50] * 40 + ramp(50, 100, 50) + ramp(100, 60, 25)
STAGE3 = [50] * 40 + ramp(50, 100, 50) + [100, 99, 101, 100, 99, 100, 101, 99, 100, 99] * 3 + [100, 100]
