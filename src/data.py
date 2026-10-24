"""Récupération et nettoyage des données de marché (Yahoo Finance, ou CSV)."""
from __future__ import annotations

from datetime import time

import pandas as pd

NY = "America/New_York"
RTH_OPEN, RTH_CLOSE = time(9, 30), time(16, 0)


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns=str.title)
    cols = ["Open", "High", "Low", "Close"] + (["Volume"] if "Volume" in df.columns else [])
    df = df[cols].copy()
    idx = pd.DatetimeIndex(df.index)
    df.index = idx.tz_localize(NY) if idx.tz is None else idx.tz_convert(NY)
    return df.dropna(subset=["Open", "High", "Low", "Close"]).sort_index()


def fetch_intraday(symbol: str, period: str = "60d", interval: str = "5m") -> pd.DataFrame:
    import yfinance as yf
    df = yf.Ticker(symbol).history(period=period, interval=interval, prepost=True, auto_adjust=False)
    return normalize(df)


def fetch_daily(symbol: str, period: str = "1y") -> pd.DataFrame:
    import yfinance as yf
    df = normalize(yf.Ticker(symbol).history(period=period, interval="1d", auto_adjust=False))
    df.index = pd.DatetimeIndex(df.index.date)
    return df


def load_csv(path: str) -> pd.DataFrame:
    """CSV : datetime, open, high, low, close[, volume] (heure de New York si sans fuseau)."""
    df = pd.read_csv(path)
    df.columns = [c.lower() for c in df.columns]
    df = df.set_index(pd.to_datetime(df.pop(df.columns[0])))
    return normalize(df)


def rth(df: pd.DataFrame) -> pd.DataFrame:
    t = df.index.time
    return df[(t >= RTH_OPEN) & (t < RTH_CLOSE)]


def daily_atr(daily: pd.DataFrame, n: int = 14, shift: bool = True) -> pd.Series:
    """ATR. Avec shift=True, valeur connue AVANT chaque séance (aucune triche avec le futur)."""
    prev_close = daily["Close"].shift(1)
    tr = pd.concat([daily["High"] - daily["Low"],
                    (daily["High"] - prev_close).abs(),
                    (daily["Low"] - prev_close).abs()], axis=1).max(axis=1)
    atr = tr.rolling(n).mean()
    return atr.shift(1) if shift else atr


def is_market_open(day) -> bool:
    try:
        import pandas_market_calendars as mcal
        return not mcal.get_calendar("NYSE").schedule(start_date=day, end_date=day).empty
    except Exception:
        return pd.Timestamp(day).weekday() < 5
