"""Plan de trade : envoyé dès que le range d'ouverture est formé, avec les ordres exacts."""
from __future__ import annotations

import logging
import os
import time as _t
from datetime import time

import pandas as pd

from .calendar_eco import day_verdict, fetch_events
from .config import load_config
from .context import backtest_status, market_context, now_ny, paris
from .data import fetch_intraday, is_market_open, rth
from .strategy import at, from_config, hhmm, levels, opening_range, position_size
from .telegram import send_message

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def wait_for_range(cfg, day, minutes, force, sleep=_t.sleep, fetch=fetch_intraday, max_tries=20):
    """Les données Yahoo des futures ont ~10 min de retard : on attend que le range soit complet."""
    end = at(day, time(9, 30)) + pd.Timedelta(minutes=minutes)
    df = pd.DataFrame()
    for i in range(max_tries):
        df = fetch(cfg["symbol"], "5d" if force else "1d", "1m")
        if not df.empty and df.index.max() >= end - pd.Timedelta(minutes=1):
            return df
        if force:
            break
        sleep(60)
    return df


def build_plan(cfg, day, bars: pd.DataFrame, verdict: dict, atr: float | None, bt: dict | None,
               test_label: str = "") -> str:
    p, m = from_config(cfg)
    risk, max_c = cfg["account"]["risk_per_trade_usd"], cfg["account"]["max_contracts"]
    day_bars = rth(bars)
    day_bars = day_bars[day_bars.index.date == day]
    orr = opening_range(day_bars, day, p.range_minutes)
    head = f"<b>🎯 PLAN DE TRADE — {day:%d/%m/%Y}</b>{test_label}"
    if orr is None:
        return head + "\n⚠️ Données du range indisponibles. Pas de trade aujourd'hui."
    hi, lo, end = orr
    width = hi - lo
    L = [head, f"Range {p.range_minutes} min : haut <b>{hi:.2f}</b> · bas <b>{lo:.2f}</b> ({width:.2f} pts)"]
    if verdict["status"] == "PAS DE TRADE":
        return "\n".join(L + ["", "🔴 <b>PAS DE TRADE AUJOURD'HUI</b>"] + [f"• {r}" for r in verdict["reasons"]])
    if atr and p.max_range_atr and width > p.max_range_atr * atr:
        return "\n".join(L + ["", f"🔴 <b>PAS DE TRADE</b> : range trop large ({width:.2f} pts > "
                                  f"{p.max_range_atr:.0%} de l'ATR {atr:.2f}). Risque trop gros pour l'objectif."])
    lv = levels(hi, lo, p, m)
    after = day_bars[day_bars.index >= end]
    broke = after[(after.High >= lv["long_entry"]) | (after.Low <= lv["short_entry"])]
    if not broke.empty:
        ts = broke.index[0]
        side = "à la hausse" if broke.iloc[0].High >= lv["long_entry"] else "à la baisse"
        L += ["", f"⏱ Le marché a déjà cassé {side} à {paris(ts)} (données en retard).",
              "Si ton ordre n'était pas déjà placé : <b>on ne court pas après le prix, pas de trade.</b>"]
    exit_paris = paris(at(day, hhmm(p.exit_time)))
    for side, e, s, t, word in (("🟢 ACHAT", lv["long_entry"], lv["long_stop"], lv["long_target"], "Buy Stop"),
                                ("🔴 VENTE", lv["short_entry"], lv["short_stop"], lv["short_target"], "Sell Stop")):
        n, per = position_size(risk, e, s, m, max_c, verdict["factor"])
        L += ["", f"<b>{side}</b> — ordre <b>{word}</b> à <b>{e:.2f}</b>",
              f"Stop-loss : {s:.2f} · Objectif : {t:.2f}",
              (f"Taille : <b>{n} contrat(s) MES</b> → risque {per * n:.0f} $, gain visé ≈ "
               f"{abs(t - e) * m.point_value * n - m.cost_per_contract() * n:.0f} $")
              if n else "Taille : 0 → stop trop large pour ton risque, <b>ne place pas cet ordre</b>."]
    L += ["", "<b>Mode d'emploi</b>",
          "1. Place les 2 ordres en OCO (dès que l'un est exécuté, l'autre s'annule).",
          "2. Chaque ordre part avec son stop-loss et son objectif attachés (ordre « bracket »).",
          f"3. Pas touché à {exit_paris} ? Tu fermes la position, quoi qu'il arrive.",
          "4. Un seul trade par jour. Gagné ou perdu, tu t'arrêtes.",
          "5. Tu ne déplaces JAMAIS ton stop-loss."]
    if verdict["status"] == "PRUDENCE":
        L += ["", "🟠 Taille réduite aujourd'hui : " + " ; ".join(verdict["reasons"])]
    if not (bt and bt.get("validated")):
        L += ["", "⚠️ Stratégie pas encore validée : <b>compte DÉMO uniquement</b>."]
    return "\n".join(L)


def main():
    cfg = load_config()
    now = now_ny()
    force = os.getenv("FORCE") == "1"
    if not force and not (time(9, 44) <= now.time() <= time(10, 30)):
        print(f"Hors fenêtre du plan ({now:%H:%M} NY) : rien à faire.")
        return
    if not force and (now.weekday() >= 5 or not is_market_open(now.date())):
        print("Marché fermé.")
        return
    p, _ = from_config(cfg)
    bars = wait_for_range(cfg, now.date(), p.range_minutes, force)
    if bars.empty:
        send_message("⚠️ Plan : données indisponibles aujourd'hui. Pas de trade.")
        return
    sess_days = sorted(set(rth(bars).index.date))
    day, label = now.date(), ""
    if force and (not sess_days or sess_days[-1] != now.date()):
        day, label = sess_days[-1], " <i>(test sur la dernière séance)</i>"
    ctx = market_context(cfg, day, events=fetch_events(day))
    send_message(build_plan(cfg, day, bars, ctx["verdict"], ctx.get("atr"), backtest_status(), label))


if __name__ == "__main__":
    main()
