"""Brief du matin, envoyé ~45 min avant l'ouverture de New York."""
from __future__ import annotations

import logging
import os
from datetime import time

import pandas as pd

from .ai import ask
from .config import load_config
from .context import backtest_status, market_context, now_ny, paris
from .data import is_market_open
from .news import headlines
from .strategy import at, from_config, position_size
from .telegram import esc, send_message

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

SYSTEM = (
    "Tu es l'analyste marchés d'un trader débutant qui trade le micro S&P 500 (MES) à l'ouverture de New York. "
    "On te donne les données de marché calculées et les titres d'actualité des dernières 24 heures. "
    "Réponds en français, en texte brut sans markdown, 130 à 180 mots, en trois parties titrées : "
    "'Cette nuit :', 'Aujourd'hui :', 'Attention à :'. Base-toi UNIQUEMENT sur les infos fournies. "
    "Interdit : donner un signal d'achat ou de vente, prédire la direction avec certitude, inventer des faits ou des chiffres."
)


def fmt(x, d=2):
    return "—" if x is None else f"{x:,.{d}f}".replace(",", " ")


def build_message(ctx: dict, cfg: dict, ai_text: str | None, bt: dict | None, news: list | None = None) -> str:
    today = ctx["today"]
    open_ny = at(today, time(9, 30))
    v = ctx["verdict"]
    icon = {"GO": "🟢", "PRUDENCE": "🟠", "PAS DE TRADE": "🔴"}[v["status"]]
    L = [f"<b>☀️ BRIEF DU {today:%d/%m/%Y}</b>",
         f"Ouverture New York : <b>{paris(open_ny)}</b> (heure de Paris)", "",
         f"<b>{icon} VERDICT DU JOUR : {v['status']}</b>"]
    L += [f"• {esc(r)}" for r in v["reasons"]]
    if v["factor"] and v["factor"] < 1:
        L.append(f"• Risque max aujourd'hui : {cfg['account']['risk_per_trade_usd'] * v['factor']:.0f} $")
    L += ["", "<b>📍 Niveaux clés MES</b>",
          f"Veille : haut {fmt(ctx.get('prev_high'))} · bas {fmt(ctx.get('prev_low'))} · clôture {fmt(ctx.get('prev_close'))}",
          f"Nuit : haut {fmt(ctx.get('on_high'))} · bas {fmt(ctx.get('on_low'))}",
          f"Prix actuel : {fmt(ctx.get('last'))}"
          + (f" ({ctx['gap_pct']:+.2f} % vs veille)" if ctx.get("gap_pct") is not None else ""),
          f"Volatilité journalière (ATR 14) : {fmt(ctx.get('atr'))} points"
          + (f" ≈ {ctx['atr'] * cfg['point_value']:.0f} $ par contrat" if ctx.get("atr") else ""),
          f"Tendance de fond (moyenne 20 jours) : {ctx.get('trend', '—')}",
          f"VIX (peur du marché) : {fmt(ctx.get('vix'))}"]
    ev = ctx.get("events")
    L += ["", "<b>🗓 Annonces US du jour</b>"]
    if ev is None:
        L.append("Calendrier indisponible — vérifie forexfactory.com")
    elif not ev:
        L.append("Aucune annonce importante")
    else:
        for e in ev:
            dot = "🔴" if e["impact"] == "High" else "🟠"
            L.append(f"{dot} {paris(e['time'])} — {esc(e['title'])}"
                     + (f" (prévu {esc(e['forecast'])}, avant {esc(e['previous'])})" if e.get("forecast") else ""))
    if ai_text:
        L += ["", "<b>🧠 Contexte (résumé IA)</b>", esc(ai_text)]
    if news:
        L += ["", "<b>📰 Titres des dernières 24 h</b>"]
        L += [f"• {paris(n['time'])} — {esc(n['title'])} <i>({esc(n['source'])})</i>" for n in news[:5 if ai_text else 10]]
    rm = cfg["strategy"]["range_minutes"]
    end = open_ny + pd.Timedelta(minutes=rm)
    L += ["", "<b>🎯 Plan (à appliquer toi-même à " + paris(end) + ", sans attendre le bot)</b>",
          f"1. De {paris(open_ny)} à {paris(end)}, note le plus haut et le plus bas sur ton graphique.",
          "2. Ordre Buy Stop 1 tick au-dessus du haut, ordre Sell Stop 1 tick sous le bas, en OCO.",
          "3. Stop-loss : " + ("au milieu du range" if cfg["strategy"]["stop_mode"] == "mid"
                               else "1 tick de l'autre côté du range") + ". Objectif : "
          f"{cfg['strategy']['target_r']} fois la taille du stop.",
          "4. Nombre de contrats selon la taille du range :"]
    if v["factor"]:
        p, m = from_config(cfg)
        max_w = (p.max_range_atr * ctx["atr"]) if ctx.get("atr") and p.max_range_atr else None
        for w in (4, 6, 8, 10, 14, 18, 24):
            if max_w and w > max_w:
                break
            dist = w / 2 + m.tick if p.stop_mode == "mid" else w + 2 * m.tick
            n, _ = position_size(cfg["account"]["risk_per_trade_usd"], 0, dist, m,
                                 cfg["account"]["max_contracts"], v["factor"])
            L.append(f"   range {w} pts → {n} contrat(s)" if n else f"   range {w} pts → 0, pas de trade")
        if max_w:
            L.append(f"   range > {max_w:.1f} pts → <b>pas de trade</b> (trop large)")
    L += ["Le bot t'envoie ensuite le plan calculé pour vérifier (ses données ont ~10 min de retard).",
          "Si le verdict est 🔴, tu ne trades pas, même si ça bouge. C'est ça qui protège ton compte."]
    if bt:
        L.append("")
        L.append("📊 Stratégie : " + ("✅ validée par le backtest" if bt.get("validated")
                                       else "❌ non validée — DÉMO UNIQUEMENT"))
    else:
        L += ["", "📊 Backtest pas encore lancé — DÉMO UNIQUEMENT"]
    return "\n".join(L)


def main():
    cfg = load_config()
    now = now_ny()
    force = os.getenv("FORCE") == "1"
    if not force and not (time(8, 30) <= now.time() <= time(9, 25)):
        print(f"Hors fenêtre du brief ({now:%H:%M} NY) : rien à faire.")
        return
    if now.weekday() >= 5 or not is_market_open(now.date()):
        send_message(f"😴 Marché américain fermé aujourd'hui ({now:%d/%m}). Pas de trading, repose-toi.")
        return
    ctx = market_context(cfg, now.date())
    news = headlines(now)
    data_txt = {k: ctx.get(k) for k in ("prev_high", "prev_low", "prev_close", "on_high", "on_low",
                                         "last", "gap_pct", "atr", "trend", "vix")}
    prompt = (f"Date : {now:%A %d %B %Y}.\nDonnées MES : {data_txt}\n"
              f"Annonces US du jour : {[(e['title'], e['time'].strftime('%H:%M') + ' NY') for e in (ctx['events'] or [])]}\n"
              "Titres d'actualité :\n" + "\n".join(f"- {n['title']} ({n['source']})" for n in news))
    ai_text = ask(SYSTEM, prompt, cfg.get("ai", {})) if news else None
    send_message(build_message(ctx, cfg, ai_text, backtest_status(), news))

if __name__ == "__main__":
    main()
