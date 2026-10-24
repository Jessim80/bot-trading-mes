"""Titres d'actualité gratuits (Yahoo Finance + flux RSS CNBC), sans clé ni abonnement."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import pandas as pd
import requests

RSS = ["https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114",  # Top News
       "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258"]   # Économie


def _yahoo(tickers=("^GSPC", "ES=F", "SPY")) -> list[dict]:
    out = []
    try:
        import yfinance as yf
        for t in tickers:
            for n in (yf.Ticker(t).news or []):
                c = n.get("content", n)  # format variable selon la version de yfinance
                title = c.get("title")
                ts = c.get("pubDate") or c.get("providerPublishTime")
                src = (c.get("provider") or {}).get("displayName") if isinstance(c.get("provider"), dict) else c.get("publisher")
                if title and ts:
                    when = pd.Timestamp(ts, unit="s", tz="UTC") if isinstance(ts, (int, float)) else pd.Timestamp(ts)
                    out.append({"title": title.strip(), "source": src or "Yahoo Finance", "time": when})
    except Exception:
        pass
    return out


def _rss() -> list[dict]:
    out = []
    for url in RSS:
        try:
            root = ET.fromstring(requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"}).content)
            for it in root.iter("item"):
                title, date = it.findtext("title"), it.findtext("pubDate")
                if title and date:
                    out.append({"title": title.strip(), "source": "CNBC",
                                "time": pd.Timestamp(parsedate_to_datetime(date))})
        except Exception:
            continue
    return out


def headlines(now: pd.Timestamp, hours: int = 24, limit: int = 15, sources=None) -> list[dict]:
    items = sources if sources is not None else _yahoo() + _rss()
    cutoff = now.tz_convert("UTC") - pd.Timedelta(hours=hours)
    seen, out = set(), []
    for n in sorted(items, key=lambda x: x["time"], reverse=True):
        key = n["title"].lower()[:60]
        t = n["time"].tz_convert("UTC") if n["time"].tzinfo else n["time"].tz_localize("UTC")
        if key in seen or t < cutoff:
            continue
        seen.add(key)
        out.append(n)
    return out[:limit]
