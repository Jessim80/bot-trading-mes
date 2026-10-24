"""Backtest de l'Opening Range Breakout + test de robustesse + verdict."""
from __future__ import annotations

import argparse
import itertools
import json
from dataclasses import replace

import pandas as pd

from .config import RESULTS, load_config
from .data import daily_atr, fetch_daily, fetch_intraday, load_csv, rth
from .strategy import Market, Params, from_config, simulate_day
from .telegram import esc, send_message, send_photo


def daily_trend(daily: pd.DataFrame | None, n: int = 20) -> pd.Series | None:
    """+1 si la clôture de la VEILLE est au-dessus de sa moyenne 20 jours, -1 sinon (sans regarder le futur)."""
    if daily is None or daily.empty:
        return None
    c = daily["Close"]
    t = (c > c.rolling(n).mean()).astype(int) * 2 - 1
    t[c.rolling(n).mean().isna()] = 0
    t = t.shift(1)
    t.index = pd.to_datetime(t.index).tz_localize(None).normalize()
    return t


def run(intraday: pd.DataFrame, atr: pd.Series | None, p: Params, m: Market, risk: float, max_c: int,
        trend: pd.Series | None = None):
    bars = rth(intraday)
    rows = []
    for day, g in bars.groupby(bars.index.date):
        a = None
        if atr is not None:
            v = atr.get(pd.Timestamp(day))
            a = float(v) if v is not None and pd.notna(v) else None
        tr = None
        if trend is not None:
            v = trend.get(pd.Timestamp(day))
            tr = int(v) if v is not None and pd.notna(v) else None
        rows.append(simulate_day(g, day, p, m, risk, max_c, a, tr))
    return pd.DataFrame(rows)


def stats(res: pd.DataFrame) -> dict:
    t = res[res["status"] == "trade"] if not res.empty else res
    n = len(t)
    s = {"days": len(res), "trades": n}
    if n == 0:
        return {**s, "win_rate": 0, "profit_factor": 0, "expectancy_r": 0, "total_pnl": 0,
                "max_drawdown": 0, "max_loss_streak": 0, "avg_win": 0, "avg_loss": 0}
    wins, losses = t[t["pnl"] > 0], t[t["pnl"] <= 0]
    eq = t["pnl"].cumsum()
    streak = best = 0
    for v in t["pnl"]:
        streak = streak + 1 if v <= 0 else 0
        best = max(best, streak)
    gl = -losses["pnl"].sum()
    return {**s,
            "win_rate": round(len(wins) / n * 100, 1),
            "avg_win": round(wins["pnl"].mean(), 2) if len(wins) else 0,
            "avg_loss": round(losses["pnl"].mean(), 2) if len(losses) else 0,
            "profit_factor": round(wins["pnl"].sum() / gl, 2) if gl > 0 else 99.0,
            "expectancy_r": round(t["r"].mean(), 3),
            "total_pnl": round(t["pnl"].sum(), 2),
            "max_drawdown": round((eq.cummax().clip(lower=0) - eq).max(), 2),
            "max_loss_streak": best}


def grid(intraday, atr, base: Params, m, risk, max_c, trend=None) -> pd.DataFrame:
    rows = []
    for rm, sm, tr in itertools.product([5, 15, 30], ["opposite", "mid"], [1.0, 1.5, 2.0]):
        p = replace(base, range_minutes=rm, stop_mode=sm, target_r=tr)
        s = stats(run(intraday, atr, p, m, risk, max_c, trend))
        rows.append({"range_min": rm, "stop": sm, "target_r": tr, **{k: s[k] for k in
                     ("trades", "win_rate", "profit_factor", "expectancy_r", "total_pnl", "max_drawdown")}})
    return pd.DataFrame(rows).sort_values("expectancy_r", ascending=False)


def verdict(s: dict, g: pd.DataFrame) -> dict:
    share_pos = float((g["expectancy_r"] > 0).mean()) if len(g) else 0.0
    checks = {
        "Au moins 30 trades (échantillon)": s["trades"] >= 30,
        "Profit factor ≥ 1,2": s["profit_factor"] >= 1.2,
        "Espérance ≥ +0,10 R par trade": s["expectancy_r"] >= 0.10,
        "≥ 60 % des variantes gagnantes (robustesse)": share_pos >= 0.6,
    }
    return {"validated": all(checks.values()), "checks": checks, "share_positive": round(share_pos * 100)}


def chart(res: pd.DataFrame, path) -> bool:
    t = res[res["status"] == "trade"]
    if t.empty:
        return False
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    eq = t["pnl"].cumsum().reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(8, 4.2), dpi=130)
    ax.plot(eq.index + 1, eq.values, lw=2, color="#2563eb")
    ax.fill_between(eq.index + 1, eq.values, 0, alpha=.12, color="#2563eb")
    ax.axhline(0, color="#888", lw=.8)
    ax.set_title("Courbe de gains du backtest (en $, après frais)")
    ax.set_xlabel("Trade n°")
    ax.grid(alpha=.3)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return True


def report(s, v, g, p: Params, period: str) -> str:
    L = [f"📊 BACKTEST — Opening Range Breakout sur MES" + (" · filtre tendance" if p.trend_filter else ""),
         f"Période : {esc(period)}",
         f"Réglages : range {p.range_minutes} min · stop {p.stop_mode} · objectif {p.target_r}R · sortie {p.exit_time} NY",
         "",
         f"Trades : {s['trades']} sur {s['days']} jours",
         f"Taux de réussite : {s['win_rate']} %",
         f"Gain moyen : {s['avg_win']} $ · Perte moyenne : {s['avg_loss']} $",
         f"Profit factor : {s['profit_factor']}",
         f"Espérance : {s['expectancy_r']:+} R par trade",
         f"Résultat total : {s['total_pnl']:+} $",
         f"Pire baisse (drawdown) : {s['max_drawdown']} $ · Pire série de pertes : {s['max_loss_streak']}",
         "", "Contrôles :"]
    L += [f"{'✅' if ok else '❌'} {esc(k)}" for k, ok in v["checks"].items()]
    L += ["", "Top 5 des variantes testées :"]
    for _, r in g.head(5).iterrows():
        L.append(f"• {r.range_min} min / {r.stop} / {r.target_r}R → {r.expectancy_r:+} R, PF {r.profit_factor}, {r.trades} trades")
    L += ["", ("✅ STRATÉGIE VALIDÉE — passe en démo pendant 30 trades avant tout argent réel."
               if v["validated"] else
               "❌ STRATÉGIE NON VALIDÉE — démo uniquement. Ne mets pas d'argent réel dessus."),
          "Ne choisis pas la meilleure variante juste parce qu'elle a gagné : c'est le piège du sur-ajustement. "
          "Une stratégie solide gagne avec des réglages proches, pas avec un seul réglage magique."]
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", help="historique 1 ou 5 min plus long (optionnel)")
    a = ap.parse_args(argv)
    cfg = load_config()
    p, m = from_config(cfg)
    risk, max_c = cfg["account"]["risk_per_trade_usd"], cfg["account"]["max_contracts"]
    intraday = load_csv(a.csv) if a.csv else fetch_intraday(cfg["symbol"], "60d", "5m")
    if intraday.empty:
        send_message("⚠️ Backtest : impossible de récupérer les données de marché.")
        return
    try:
        daily = fetch_daily(cfg["symbol"], "2y")
        atr, trend = daily_atr(daily), daily_trend(daily)
    except Exception:
        atr = trend = None
    res = run(intraday, atr, p, m, risk, max_c, trend)
    s, g = stats(res), grid(intraday, atr, p, m, risk, max_c, trend)
    v = verdict(s, g)
    period = f"{intraday.index[0]:%d/%m/%Y} → {intraday.index[-1]:%d/%m/%Y}"
    RESULTS.mkdir(exist_ok=True)
    res.to_csv(RESULTS / "trades.csv", index=False)
    g.to_csv(RESULTS / "variantes.csv", index=False)
    (RESULTS / "backtest_summary.json").write_text(json.dumps(
        {"period": period, "stats": s, "validated": v["validated"], "checks": v["checks"],
         "params": vars(p), "generated": pd.Timestamp.now(tz="UTC").isoformat()},
        ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    send_message(report(s, v, g, p, period))
    png = RESULTS / "equity.png"
    if chart(res, png):
        send_photo(str(png), "Courbe de gains du backtest")


if __name__ == "__main__":
    main()
