import numpy as np
import pandas as pd

NY = "America/New_York"


def synthetic(days=60, freq="5min", seed=1, start=6000.0, first="2026-07-01"):
    """Marché simulé (marche aléatoire) 24h/24 en semaine — uniquement pour tester le code."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(first, periods=days * 24 * 60 // int(freq.rstrip("min")), freq=freq, tz=NY)
    idx = idx[idx.weekday < 5]
    step = int(freq.rstrip("min"))
    r = rng.normal(0, 0.9 * step ** 0.5, len(idx))
    close = start + np.cumsum(r)
    open_ = np.r_[start, close[:-1]]
    hi = np.maximum(open_, close) + rng.uniform(0, 1.2, len(idx))
    lo = np.minimum(open_, close) - rng.uniform(0, 1.2, len(idx))
    return pd.DataFrame({"Open": open_, "High": hi, "Low": lo, "Close": close, "Volume": 100}, index=idx)


def daily_from(df):
    d = df.resample("1D").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()
    d.index = pd.DatetimeIndex(d.index.date)
    return d


def day_bars(rows, day="2026-10-26", freq="5min"):
    """Construit une séance précise à partir de (open, high, low, close) depuis 9h30."""
    idx = pd.date_range(f"{day} 09:30", periods=len(rows), freq=freq, tz=NY)
    return pd.DataFrame(rows, columns=["Open", "High", "Low", "Close"], index=idx)
