"""Contexte de marché commun au brief et au plan : niveaux, volatilité, VIX, annonces."""
from __future__ import annotations

import json
import os
from datetime import time

import pandas as pd

from .calendar_eco import day_verdict, fetch_events
from .config import RESULTS
from .data import daily_atr, fetch_daily, fetch_intraday, rth
from .strategy import at

NY, PARIS = "America/New_York", "Europe/Paris"


def now_ny() -> pd.Timestamp:
    fake = os.getenv("NOW")  # pour les tests, ex : NOW=2026-10-26T09:00
    return pd.Timestamp(fake).tz_localize(NY) if fake else pd.Timestamp.now(tz=NY)


def paris(ts: pd.Timestamp) -> str:
    return ts.tz_convert(PARIS).strftime("%Hh%M")


def vix_level() -> float | None:
    try:
        import yfinance as yf
        h = yf.Ticker("^VIX").history(period="5d", interval="1d")
        return round(float(h["Close"].iloc[-1]), 2)
    except Exception:
        return None


def backtest_status() -> dict | None:
    f = RESULTS / "backtest_summary.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def market_context(cfg: dict, today, intraday: pd.DataFrame | None = None,
                   daily: pd.DataFrame | None = None, vix=..., events=...) -> dict:
    today = pd.Timestamp(today).date()
    intraday = fetch_intraday(cfg["symbol"], "5d", "5m") if intraday is None else intraday
    daily = fetch_daily(cfg["symbol"], "6mo") if daily is None else daily
    vix = vix_level() if vix is ... else vix
    events = fetch_events(today) if events is ... else events

    sess = rth(intraday)
    prev_days = sorted(d for d in set(sess.index.date) if d < today)
    ctx = {"today": today, "vix": vix, "events": events,
           "verdict": day_verdict(events, vix, cfg["filters"])}
    if prev_days:
        pd_ = prev_days[-1]
        g = sess[sess.index.date == pd_]
        ctx.update(prev_date=pd_, prev_high=float(g.High.max()), prev_low=float(g.Low.min()),
                   prev_close=float(g.Close.iloc[-1]))
        on = intraday[(intraday.index >= at(pd_, time(16, 0))) & (intraday.index < at(today, time(9, 30)))]
        if not on.empty:
            ctx.update(on_high=float(on.High.max()), on_low=float(on.Low.min()), last=float(on.Close.iloc[-1]))
            ctx["gap_pct"] = round((ctx["last"] / ctx["prev_close"] - 1) * 100, 2)
    d = daily[daily.index.date < today] if not daily.empty else daily
    if len(d) > 15:
        atr = daily_atr(d, shift=False).iloc[-1]
        ctx["atr"] = round(float(atr), 2) if pd.notna(atr) else None
        ctx["sma20"] = round(float(d.Close.tail(20).mean()), 2)
        ctx["trend"] = "haussière" if d.Close.iloc[-1] > ctx["sma20"] else "baissière"
    return ctx
