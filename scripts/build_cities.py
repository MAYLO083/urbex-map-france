#!/usr/bin/env python3
"""
Liste des villes du monde pour la recherche de l'appli : toutes les villes de plus de
15 000 habitants selon GeoNames (cities15000, licence CC-BY 4.0).

Génère data/cities.json : [[nom, lat, lon, code pays, population], …] trié par population.

Usage :
    python scripts/build_cities.py
"""

from __future__ import annotations

import io
import json
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "cities.json"
URL = "https://download.geonames.org/export/dump/cities15000.zip"
UA = "urbex-map/1.0 (open-source map project)"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    rows = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for line in z.read("cities15000.txt").decode("utf-8").splitlines():
            p = line.split("\t")
            if p[6] != "P" or re.search(r"\s\d{1,2}$", p[1]):   # sans les arrondissements (« Lyon 03 »)
                continue
            rows.append([p[1], round(float(p[4]), 4), round(float(p[5]), 4), p[8], int(p[14] or 0)])
    rows.sort(key=lambda r: -r[4])
    if len(rows) < 10000:
        sys.exit(f"Seulement {len(rows)} villes : fichier précédent conservé")
    OUT.write_text(json.dumps(rows, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(rows)} villes écrites dans {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1e6:.1f} Mo)")


if __name__ == "__main__":
    main()
