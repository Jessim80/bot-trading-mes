"""Opening Range Breakout — la MÊME logique sert au backtest et au bot en direct."""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import time

import pandas as pd

NY = "America/New_York"


@dataclass
class Params:
    range_minutes: int = 15
    stop_mode: str = "opposite"
    target_r: float = 1.5
    exit_time: str = "11:30"
    max_range_atr: float | None = 0.6


@dataclass
class Market:
    tick: float = 0.25
    point_value: float = 5.0
    commission_rt: float = 1.50
    slippage_ticks: int = 1

    def cost_per_contract(self) -> float:
        return self.commission_rt + 2 * self.slippage_ticks * self.tick * self.point_value


def from_config(cfg: dict) -> tuple[Params, Market]:
    s, c = cfg["strategy"], cfg["costs"]
    return (Params(s["range_minutes"], s["stop_mode"], s["target_r"], s["exit_time"], s.get("max_range_atr")),
            Market(cfg["tick_size"], cfg["point_value"], c["commission_rt"], c["slippage_ticks"]))


def hhmm(s: str) -> time:
    h, m = map(int, s.split(":"))
    return time(h, m)


def at(day, t: time) -> pd.Timestamp:
    return pd.Timestamp.combine(pd.Timestamp(day).date(), t).tz_localize(NY)


def rt(x: float, tick: float) -> float:
    return round(round(x / tick) * tick, 2)


def opening_range(day_bars: pd.DataFrame, day, minutes: int):
    start = at(day, time(9, 30))
    end = start + pd.Timedelta(minutes=minutes)
    rng = day_bars[(day_bars.index >= start) & (day_bars.index < end)]
    if rng.empty:
        return None
    return float(rng["High"].max()), float(rng["Low"].min()), end


def levels(hi: float, lo: float, p: Params, m: Market) -> dict:
    le, se = rt(hi + m.tick, m.tick), rt(lo - m.tick, m.tick)
    if p.stop_mode == "mid":
        ls = ss = rt((hi + lo) / 2, m.tick)
    else:
        ls, ss = rt(lo - m.tick, m.tick), rt(hi + m.tick, m.tick)
    return {"long_entry": le, "long_stop": ls, "long_target": rt(le + p.target_r * (le - ls), m.tick),
            "short_entry": se, "short_stop": ss, "short_target": rt(se - p.target_r * (ss - se), m.tick)}


def position_size(risk_usd: float, entry: float, stop: float, m: Market, max_c: int, factor: float = 1.0):
    per = abs(entry - stop) * m.point_value + m.cost_per_contract()
    n = math.floor(risk_usd * factor / per) if per > 0 else 0
    return max(0, min(n, max_c)), per


def simulate_day(day_bars: pd.DataFrame, day, p: Params, m: Market, risk_usd: float,
                 max_c: int, atr: float | None = None) -> dict:
    out = {"date": pd.Timestamp(day).date(), "status": "skip"}
    orr = opening_range(day_bars, day, p.range_minutes)
    if orr is None:
        return {**out, "reason": "pas de données"}
    hi, lo, rng_end = orr
    width = hi - lo
    out["range"] = round(width, 2)
    if width <= 0:
        return {**out, "reason": "range nul"}
    if atr and p.max_range_atr and width > p.max_range_atr * atr:
        return {**out, "reason": "range trop large vs ATR"}
    lv = levels(hi, lo, p, m)
    exit_dt = at(day, hhmm(p.exit_time))
    after = day_bars[(day_bars.index >= rng_end) & (day_bars.index < exit_dt)]
    pos = None

    def close(px, ts, why):
        pts = (px - pos["entry"]) * pos["dir"]
        pnl = pts * m.point_value * pos["n"] - m.cost_per_contract() * pos["n"]
        return {**out, "status": "trade", "dir": "LONG" if pos["dir"] == 1 else "SHORT",
                "entry_time": pos["ts"], "entry": pos["entry"], "stop": pos["stop"], "target": pos["target"],
                "exit_time": ts, "exit": round(float(px), 2), "exit_reason": why, "contracts": pos["n"],
                "pnl": round(pnl, 2), "r": round(pnl / (pos["per"] * pos["n"]), 3)}

    for ts, b in after.iterrows():
        if pos is None:
            up, dn = b.High >= lv["long_entry"], b.Low <= lv["short_entry"]
            if not (up or dn):
                continue
            d = (1 if abs(b.Open - hi) <= abs(b.Open - lo) else -1) if (up and dn) else (1 if up else -1)
            if d == 1:
                entry, stop, tgt = max(lv["long_entry"], b.Open), lv["long_stop"], lv["long_target"]
            else:
                entry, stop, tgt = min(lv["short_entry"], b.Open), lv["short_stop"], lv["short_target"]
            n, per = position_size(risk_usd, entry, stop, m, max_c)
            if n == 0:
                return {**out, "reason": "stop trop large pour le risque"}
            pos = {"dir": d, "entry": float(entry), "stop": stop, "target": tgt, "n": n, "per": per, "ts": ts}
            # Prudence : si le stop est touché dans la bougie d'entrée, on compte une perte
            if (d == 1 and b.Low <= stop) or (d == -1 and b.High >= stop):
                return close(stop, ts, "stop")
            continue
        d, stop, tgt = pos["dir"], pos["stop"], pos["target"]
        if (d == 1 and b.Low <= stop) or (d == -1 and b.High >= stop):  # stop prioritaire (hypothèse prudente)
            return close(min(stop, b.Open) if d == 1 else max(stop, b.Open), ts, "stop")
        if (d == 1 and b.High >= tgt) or (d == -1 and b.Low <= tgt):
            return close(tgt, ts, "objectif")
    if pos:
        return close(after["Close"].iloc[-1], after.index[-1], "sortie horaire")
    return {**out, "reason": "pas de cassure"}
