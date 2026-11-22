#!/usr/bin/env python3
"""
Publie un message dans le salon #mises-à-jour-carte du Discord (webhook dans le secret DISCORD_WEBHOOK).

Usage (dans les GitHub Actions) :
    python scripts/discord_notify.py carte     # la carte vient d'être mise à jour (AVANT = ancien total)
    python scripts/discord_notify.py spot      # un lieu de la communauté vient d'être ajouté (SUMMARY, ISSUE_URL)

Sans webhook configuré, ne fait rien.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request

SITE = "https://maylo083.github.io/urbex-map-france/"
UA = "urbex-map/1.0 (open-source map project)"
ORANGE = 0xE67E22
LABELS = {
    "osm": "OpenStreetMap", "wikidata": "Wikidata", "geonames": "GeoNames", "friches": "Friches 🇫🇷",
    "casias": "Anciens sites industriels 🇫🇷", "mines_on": "Mines abandonnées 🇨🇦",
    "heritage": "Patrimoine en danger 🇬🇧", "friches_uk": "Friches 🇬🇧", "merimee": "Monuments historiques 🇫🇷",
    "communaute": "Communauté",
}


def n(x: int) -> str:
    return f"{x:,}".replace(",", " ")


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def send(hook: str, embed: dict) -> None:
    body = json.dumps({"username": "Urbex Map", "embeds": [embed]}).encode()
    req = urllib.request.Request(hook + "?wait=true", data=body, method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        print("message envoyé", r.status)


def carte() -> dict:
    meta = json.loads(get(f"{SITE}data/tiles/meta.json?t={int(time.time())}"))
    per: dict[str, int] = {}
    for key, count in meta["totals"].items():
        src = key.split("|")[1]
        per[src] = per.get(src, 0) + count
    lines = [f"• {LABELS.get(s, s)} : {n(c)}" for s, c in sorted(per.items(), key=lambda x: -x[1])]
    total = meta["count"]
    head = f"La carte compte maintenant **{n(total)} lieux**"
    avant = os.environ.get("AVANT", "")
    if avant.isdigit() and int(avant) != total:
        diff = total - int(avant)
        head += f" ({'+' if diff > 0 else '−'}{n(abs(diff))} depuis la dernière mise à jour)"
    return {"title": "🗺️ Carte mise à jour", "url": SITE, "color": ORANGE,
            "description": head + ".\n\n" + "\n".join(lines),
            "footer": {"text": "Mise à jour automatique · sources ouvertes"}}


def spot() -> dict:
    summary = os.environ.get("SUMMARY", "").strip()
    url = os.environ.get("ISSUE_URL", "")
    return {"title": "📍 Nouveau lieu de la communauté", "url": url or SITE, "color": 0xF1C40F,
            "description": f"{summary}\n\n[Voir sur la carte]({SITE}) · [Proposition]({url})" if url else summary,
            "footer": {"text": "Merci au contributeur ! Propose le tien : salon #➕ajouter-un-lieu"}}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    hook = os.environ.get("DISCORD_WEBHOOK", "").strip()
    if not hook:
        print("Pas de webhook Discord configuré : rien à faire")
        return
    mode = sys.argv[1] if len(sys.argv) > 1 else "carte"
    send(hook, carte() if mode == "carte" else spot())


if __name__ == "__main__":
    main()
