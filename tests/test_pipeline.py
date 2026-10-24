import pandas as pd

from src import backtest, brief, plan
from src.calendar_eco import day_verdict
from src.config import load_config
from src.context import market_context
from src.strategy import from_config
from tests.synth import daily_from, synthetic


def test_backtest_end_to_end(tmp_path):
    cfg = load_config()
    p, m = from_config(cfg)
    df = synthetic(60, "5min")
    atr = backtest.daily_atr(daily_from(df))
    res = backtest.run(df, atr, p, m, 200, 5)
    s = backtest.stats(res)
    g = backtest.grid(df, atr, p, m, 200, 5)
    v = backtest.verdict(s, g)
    assert s["trades"] > 10 and len(g) == 18 and isinstance(v["validated"], bool)
    txt = backtest.report(s, v, g, p, "test")
    assert "BACKTEST" in txt and "Contrôles" in txt
    assert backtest.chart(res, tmp_path / "eq.png")


def test_brief_and_plan_messages():
    cfg = load_config()
    df1 = synthetic(10, "1min", seed=3, first="2026-10-14")
    day = sorted(set(df1.index.date))[-1]
    events = [{"time": pd.Timestamp(f"{day} 08:30", tz="America/New_York"), "title": "Unemployment Claims",
               "impact": "High", "forecast": "230K", "previous": "228K"}]
    ctx = market_context(cfg, day, intraday=df1, daily=daily_from(synthetic(120, "5min", first="2026-06-01")), vix=18.0, events=events)
    assert ctx["verdict"]["status"] == "PRUDENCE" and "prev_high" in ctx and ctx.get("atr")
    msg = brief.build_message(ctx, cfg, "Cette nuit : test. Aujourd'hui : test. Attention à : test.", None)
    assert "VERDICT DU JOUR" in msg and ("15h30" in msg or "14h30" in msg)
    txt = plan.build_plan(cfg, day, df1, ctx["verdict"], ctx["atr"] * 10, None)
    assert "PLAN DE TRADE" in txt and ("Buy Stop" in txt or "PAS DE TRADE" in txt)
    no = plan.build_plan(cfg, day, df1, day_verdict([], 35, cfg["filters"]), None, None)
    assert "PAS DE TRADE" in no


def test_wait_for_range_retries():
    calls = []
    full = synthetic(3, "1min")
    day = sorted(set(full.index.date))[-1]
    cut = full[full.index < pd.Timestamp(f"{day} 09:40", tz="America/New_York")]

    def fetch(sym, period, interval):
        calls.append(1)
        return cut if len(calls) < 3 else full

    out = plan.wait_for_range(load_config(), day, 15, False, sleep=lambda s: None, fetch=fetch)
    assert len(calls) == 3 and out is full


def test_news_dedup_and_brief_section():
    from src.news import headlines
    now = pd.Timestamp("2026-10-26 09:00", tz="America/New_York")
    src = [{"title": "Stocks rise on earnings", "source": "CNBC", "time": now - pd.Timedelta(hours=2)},
           {"title": "Stocks rise on earnings", "source": "Yahoo", "time": now - pd.Timedelta(hours=3)},
           {"title": "Old news", "source": "CNBC", "time": now - pd.Timedelta(hours=40)}]
    news = headlines(now, sources=src)
    assert [n["title"] for n in news] == ["Stocks rise on earnings"]
    cfg = load_config()
    ctx = {"today": now.date(), "verdict": day_verdict([], 15, cfg["filters"]), "events": []}
    msg = brief.build_message(ctx, cfg, None, None, news)
    assert "Titres des dernières 24 h" in msg and "Stocks rise" in msg
