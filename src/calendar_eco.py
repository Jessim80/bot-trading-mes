"""Calendrier économique US (ForexFactory) + règles « trade / pas trade » du jour."""
from __future__ import annotations

from datetime import time

import pandas as pd
import requests

FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
NY = "America/New_York"
NO_TRADE_KEYWORDS = ("FOMC", "Federal Funds Rate", "Fed Chair", "Powell")


def fetch_events(day) -> list[dict] | None:
    """Annonces US à impact moyen/fort du jour (heure NY). None si indisponible."""
    try:
        raw = requests.get(FF_URL, timeout=20, headers={"User-Agent": "Mozilla/5.0"}).json()
    except Exception:
        return None
    out = []
    for e in raw:
        if e.get("country") != "USD" or e.get("impact") not in ("High", "Medium"):
            continue
        try:
            ts = pd.Timestamp(e["date"]).tz_convert(NY)
        except Exception:
            continue
        if ts.date() == pd.Timestamp(day).date():
            out.append({"time": ts, "title": e.get("title", ""), "impact": e["impact"],
                        "forecast": e.get("forecast", ""), "previous": e.get("previous", "")})
    return sorted(out, key=lambda x: x["time"])


def day_verdict(events: list[dict] | None, vix: float | None, filters: dict) -> dict:
    """GO / PRUDENCE / PAS DE TRADE, facteur de taille et raisons. Règles fixes, pas d'IA."""
    status, factor, reasons = "GO", 1.0, []
    for e in [x for x in (events or []) if x["impact"] == "High"]:
        t = e["time"].time()
        if any(k.lower() in e["title"].lower() for k in NO_TRADE_KEYWORDS):
            return {"status": "PAS DE TRADE", "factor": 0.0,
                    "reasons": [f"Journée Fed ({e['title']}) : mouvements imprévisibles"]}
        if time(9, 30) <= t <= time(11, 30):
            return {"status": "PAS DE TRADE", "factor": 0.0,
                    "reasons": [f"{e['title']} à {t:%H:%M} NY tombe pendant la fenêtre de trading"]}
        if t < time(9, 30):
            status, factor = "PRUDENCE", min(factor, 0.5)
            reasons.append(f"{e['title']} à {t:%H:%M} NY avant l'ouverture : taille divisée par 2")
    if events is None:
        status, factor = "PRUDENCE", min(factor, 0.5)
        reasons.append("Calendrier économique indisponible : vérifie forexfactory.com, taille divisée par 2")
    if vix is not None:
        if vix >= filters["vix_no_trade"]:
            return {"status": "PAS DE TRADE", "factor": 0.0, "reasons": [f"VIX à {vix:.1f} : marché en panique"]}
        if vix >= filters["vix_half_size"]:
            status, factor = "PRUDENCE", min(factor, 0.5)
            reasons.append(f"VIX élevé ({vix:.1f}) : taille divisée par 2")
    if not reasons:
        reasons.append("Aucune annonce majeure dans la fenêtre, volatilité normale")
    return {"status": status, "factor": factor, "reasons": reasons}
