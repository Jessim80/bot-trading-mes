"""Résumé IA robuste et GRATUIT par défaut (Google Gemini, offre gratuite sans carte bancaire).

- délai max sur chaque appel, réessais avec attente progressive sur les erreurs temporaires
- si un modèle n'existe plus ou refuse, on passe au suivant de la liste
- si aucune clé ou si tout échoue : None, et le bot envoie quand même le brief (jamais bloquant)
"""
from __future__ import annotations

import logging
import os
import random
import time

import requests

log = logging.getLogger("ai")
RETRYABLE = {429, 500, 502, 503, 504, 529}
KEYS = {"gemini": "GEMINI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}


class APIError(Exception):
    def __init__(self, status_code: int, msg: str = "", retry_after: float | None = None):
        super().__init__(f"HTTP {status_code} {msg[:200]}")
        self.status_code, self.retry_after = status_code, retry_after


def is_retryable(e: Exception) -> bool:
    status = getattr(e, "status_code", None)
    if status is not None:
        return status in RETRYABLE
    name = type(e).__name__
    return isinstance(e, (TimeoutError, ConnectionError)) or "Timeout" in name or "Connection" in name


def _gemini(model, system, prompt, timeout):
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"], "Content-Type": "application/json"},
        json={"system_instruction": {"parts": [{"text": system}]},
              "contents": [{"role": "user", "parts": [{"text": prompt}]}],
              "generationConfig": {"temperature": 0.3, "maxOutputTokens": 1200}},
        timeout=timeout)
    if not r.ok:
        ra = r.headers.get("retry-after")
        raise APIError(r.status_code, r.text, float(ra) if ra and ra.isdigit() else None)
    parts = (r.json().get("candidates") or [{}])[0].get("content", {}).get("parts", [])
    return "".join(p.get("text", "") for p in parts).strip()


def _anthropic(model, system, prompt, timeout):  # option payante, désactivée par défaut
    import anthropic
    resp = anthropic.Anthropic(timeout=timeout, max_retries=0).messages.create(
        model=model, max_tokens=1200, system=system, messages=[{"role": "user", "content": prompt}])
    return "\n".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()


CALLERS = {"gemini": _gemini, "anthropic": _anthropic}


def ask(system: str, prompt: str, cfg: dict, call=None, sleep=time.sleep, env=os.environ) -> str | None:
    if not cfg.get("enabled", True):
        return None
    retries = cfg.get("max_retries", 3)
    for entry in cfg.get("models", []):
        prov, model = entry["provider"], entry["model"]
        if call is None and not env.get(KEYS[prov]):
            continue  # pas de clé pour ce fournisseur : on l'ignore
        fn = call or CALLERS[prov]
        for attempt in range(retries + 1):
            try:
                out = fn(model, system, prompt, cfg.get("timeout_s", 90))
                if out:
                    log.info("résumé IA fourni par %s/%s", prov, model)
                    return out
                break
            except Exception as e:  # noqa: BLE001
                if not is_retryable(e) or attempt == retries:
                    log.warning("%s/%s indisponible (%s), modèle suivant", prov, model, type(e).__name__)
                    break
                wait = getattr(e, "retry_after", None) or min(30, 2 ** attempt) + random.uniform(0, 1)
                log.info("%s/%s : erreur temporaire, nouvel essai dans %.1fs", prov, model, wait)
                sleep(wait)
    return None
