#!/usr/bin/env python3
"""
Ajoute à data/spots_communaute.json le lieu décrit dans une issue GitHub
(formulaire .github/ISSUE_TEMPLATE/nouveau-spot.yml).

Appelé par le workflow add-community-spot.yml quand le propriétaire du dépôt
pose le label « validé » sur l'issue. Variables d'environnement :
ISSUE_NUMBER, ISSUE_BODY.
"""

from __future__ import annotations

import json
import os
import re
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


def main() -> None:
    number = int(os.environ["ISSUE_NUMBER"])
    f = parse(os.environ["ISSUE_BODY"])

    m = re.search(r"(-?\d{1,2}[.,]\d+)\s*[,; ]\s*(-?\d{1,3}[.,]\d+)", f.get("coordonnées gps", ""))
    if not m:
        sys.exit("Coordonnées introuvables : format attendu « 45.12345, 4.56789 »")
    lat, lon = float(m.group(1).replace(",", ".")), float(m.group(2).replace(",", "."))
    if not (41 <= lat <= 51.5 and -5.5 <= lon <= 10):
        sys.exit(f"Coordonnées hors de France : {lat}, {lon}")

    name = f.get("nom du lieu", "").strip()[:120] or "Lieu proposé"
    cat = CATEGORIES.get(f.get("catégorie", "").strip().lower(), "autre")
    desc = re.sub(r"\s+", " ", f.get("description", "")).strip()[:300]

    data = {"fields": ["lat", "lon", "name", "category", "description", "id"], "spots": []}
    if OUT.exists():
        data = json.loads(OUT.read_text(encoding="utf-8"))
    sid = f"U{number}"
    data["spots"] = [s for s in data["spots"] if s[5] != sid]  # mise à jour si re-validé
    data["spots"].append([round(lat, 5), round(lon, 5), name, cat, desc, sid])
    data["generated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    data["source"] = "Propositions de la communauté (issues GitHub validées)"
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Ajouté : {name} ({lat}, {lon}) [{cat}]")


if __name__ == "__main__":
    main()
