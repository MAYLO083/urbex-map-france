#!/usr/bin/env python3
"""
Ajoute à data/spots_communaute.json le lieu décrit dans une issue GitHub
(formulaire .github/ISSUE_TEMPLATE/nouveau-spot.yml).

Appelé par le workflow add-community-spot.yml quand le propriétaire du dépôt
pose (ACTION=add) ou retire (ACTION=remove) le label « validé » sur l'issue.
Variables d'environnement : ACTION, ISSUE_NUMBER, ISSUE_BODY.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "spots_communaute.json"

CATEGORIES = {
    "industriel": "industriel", "militaire / bunkers": "militaire", "hôpitaux / sanatoriums": "hopital",
    "châteaux / manoirs": "chateau", "religieux": "religieux", "transport / gares / tunnels": "transport",
    "hôtels / écoles / loisirs": "loisirs", "maisons / fermes": "habitation", "ruines": "ruines", "autre": "autre",
}


def parse(body: str) -> dict:
    """Les formulaires d'issue produisent « ### Titre\\n\\nvaleur »."""
    out = {}
    for block in re.split(r"^### ", body, flags=re.M)[1:]:
        title, _, value = block.partition("\n")
        value = value.strip()
        out[title.strip().lower()] = "" if value == "_No response_" else value
    return out


def load() -> dict:
    if OUT.exists():
        return json.loads(OUT.read_text(encoding="utf-8"))
    return {"fields": ["lat", "lon", "name", "category", "description", "id"], "spots": []}


def save(data: dict) -> None:
    data["generated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    data["source"] = "Propositions de la communauté (issues GitHub validées)"
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def output(summary: str) -> None:
    """Écrit le résumé au format GITHUB_OUTPUT (sortie standard redirigée par le workflow)."""
    delim = "EOF_" + secrets.token_hex(8)
    print(f"summary<<{delim}\n{summary}\n{delim}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    number = int(os.environ["ISSUE_NUMBER"])
    sid = f"U{number}"

    if os.environ.get("ACTION") == "remove":
        data = load()
        data["spots"] = [s for s in data["spots"] if s[5] != sid]
        save(data)
        output(f"Lieu #{number} retiré.")
        return

    f = parse(os.environ["ISSUE_BODY"])

    m = re.search(r"(-?\d{1,2}[.,]\d+)\s*[,; ]\s*(-?\d{1,3}[.,]\d+)", f.get("coordonnées gps", ""))
    if not m:
        sys.exit("Coordonnées introuvables : format attendu « 45.12345, 4.56789 »")
    lat, lon = float(m.group(1).replace(",", ".")), float(m.group(2).replace(",", "."))
    if not (-85 <= lat <= 85 and -180 <= lon <= 180) or (lat == 0 and lon == 0):
        sys.exit(f"Coordonnées invalides : {lat}, {lon}")

    name = re.sub(r"\s+", " ", f.get("nom du lieu", "")).strip()[:120] or "Lieu proposé"
    cat = CATEGORIES.get(f.get("catégorie", "").strip().lower(), "autre")
    desc = re.sub(r"\s+", " ", f.get("description", "")).strip()[:300]

    data = load()
    data["spots"] = [s for s in data["spots"] if s[5] != sid]  # mise à jour si re-validé
    data["spots"].append([round(lat, 5), round(lon, 5), name, cat, desc, sid])
    save(data)
    # Récapitulatif de ce qui a réellement été publié (au cas où l'issue aurait été modifiée)
    output(f"- **Nom** : {name}\n- **Position** : {lat:.5f}, {lon:.5f} "
           f"([voir](https://www.openstreetmap.org/?mlat={lat:.5f}&mlon={lon:.5f}#map=17/{lat:.5f}/{lon:.5f}))\n"
           f"- **Catégorie** : {cat}" + (f"\n- **Description** : {desc}" if desc else ""))


if __name__ == "__main__":
    main()
