#!/usr/bin/env python3
"""
Retire de la carte un lieu signalé (formulaire .github/ISSUE_TEMPLATE/signaler-lieu.yml).

Appelé par le workflow report-spot.yml quand le propriétaire du dépôt pose (ACTION=add)
ou retire (ACTION=remove) le label « validé » sur un signalement.
Le lieu est ajouté à data/lieux_retires.json (ou en est enlevé), que build_tiles.py
applique à chaque construction de la carte : le retrait survit donc aux mises à jour.
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from add_community_spot import parse  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "lieux_retires.json"
REF = re.compile(r"\b([a-z_]+):([A-Za-z0-9_.-]+)")


def load() -> dict:
    if OUT.exists():
        return json.loads(OUT.read_text(encoding="utf-8"))
    return {"description": "Lieux retirés de la carte après un signalement validé (source:identifiant)", "lieux": []}


def output(summary: str) -> None:
    delim = "EOF_" + secrets.token_hex(8)
    print(f"summary<<{delim}\n{summary}\n{delim}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    number = int(os.environ["ISSUE_NUMBER"])
    data = load()
    data["lieux"] = [x for x in data["lieux"] if x["issue"] != number]   # re-validation ou annulation

    if os.environ.get("ACTION") == "remove":
        OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        output(f"Signalement #{number} annulé : le lieu réapparaîtra sur la carte.")
        return

    f = parse(os.environ["ISSUE_BODY"])
    refs = REF.findall(f.get("identifiant du lieu (ne pas modifier)", ""))
    if not refs:
        sys.exit("Identifiant du lieu introuvable : le signalement doit être ouvert depuis le bouton « Signaler » de la carte")
    name = re.sub(r"\s+", " ", f.get("nom du lieu", "")).strip()[:120]
    reason = f.get("quel est le problème ?", "").strip()[:120]
    data["lieux"].append({"issue": number, "refs": [f"{s}:{i}" for s, i in refs], "nom": name, "raison": reason,
                          "date": datetime.now(timezone.utc).date().isoformat()})
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    output(f"- **Lieu** : {name or 'sans nom'}\n- **Raison** : {reason}\n- **Fiches retirées** : "
           + ", ".join(f"`{s}:{i}`" for s, i in refs))


if __name__ == "__main__":
    main()
