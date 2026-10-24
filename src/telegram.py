"""Envoi Telegram. Sans identifiants (ou DRY_RUN=1), affiche le message dans la console."""
from __future__ import annotations

import html
import os

import requests

API = "https://api.telegram.org/bot{token}/{method}"


def esc(x) -> str:
    return html.escape(str(x), quote=False)


def _creds():
    # On retire espaces et retours à la ligne collés par erreur depuis un téléphone.
    tok = "".join((os.getenv("TELEGRAM_BOT_TOKEN") or "").split())
    chat = "".join((os.getenv("TELEGRAM_CHAT_ID") or "").split())
    return (None, None) if os.getenv("DRY_RUN") == "1" or not tok or not chat else (tok, chat)


def send_message(text: str) -> None:
    tok, chat = _creds()
    chunks = [text[i:i + 3900] for i in range(0, len(text), 3900)] or [""]
    for c in chunks:
        if not tok:
            print("----- TELEGRAM (simulation) -----\n" + c)
            continue
        r = requests.post(API.format(token=tok, method="sendMessage"), timeout=30,
                          data={"chat_id": chat, "text": c, "parse_mode": "HTML",
                                "disable_web_page_preview": True})
        if not r.ok:  # repli sans mise en forme si le HTML est refusé
            requests.post(API.format(token=tok, method="sendMessage"), timeout=30,
                          data={"chat_id": chat, "text": c}).raise_for_status()


def send_photo(path: str, caption: str = "") -> None:
    tok, chat = _creds()
    if not tok:
        print(f"----- TELEGRAM photo (simulation) : {path} -----")
        return
    with open(path, "rb") as f:
        requests.post(API.format(token=tok, method="sendPhoto"), timeout=60,
                      data={"chat_id": chat, "caption": caption[:1000], "parse_mode": "HTML"},
                      files={"photo": f}).raise_for_status()
