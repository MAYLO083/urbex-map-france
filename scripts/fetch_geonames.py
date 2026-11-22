#!/usr/bin/env python3
"""
Lieux abandonnés du monde entier depuis GeoNames (licence CC-BY 4.0) :
villages abandonnés ou détruits, ruines, fermes, aérodromes, gares, mines,
usines, camps, barrages… Génère data/spots_geonames.json.

Le fichier mondial (allCountries.zip, ~420 Mo) est téléchargé puis lu ligne à ligne.

Usage :
    python scripts/fetch_geonames.py
"""

from __future__ import annotations

import io
import json
import sys
import time
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "spots_geonames.json"
CACHE = ROOT / "data" / ".cache"
URL = "https://download.geonames.org/export/dump/allCountries.zip"
UA = "urbex-map/1.0 (open-source map project)"

# code GeoNames → (catégorie, libellé)
CODES = {
    "PPLQ": ("habitation", "village abandonné"),
    "PPLW": ("ruines", "village détruit"),
    "RUIN": ("ruines", "ruines"),
    "FRMQ": ("habitation", "ferme abandonnée"),
    "AIRQ": ("transport", "aérodrome abandonné"),
    "RSTNQ": ("transport", "gare abandonnée"),
    "RSTPQ": ("transport", "arrêt ferroviaire abandonné"),
    "BDGQ": ("transport", "pont en ruine"),
    "MNQ": ("industriel", "mine abandonnée"),
    "MFGQ": ("industriel", "usine abandonnée"),
    "MLSGQ": ("industriel", "ancienne sucrerie"),
    "DAMQ": ("industriel", "barrage en ruine"),
    "CMPQ": ("autre", "camp abandonné"),
    "PPQ": ("militaire", "poste abandonné"),
    "MSSNQ": ("religieux", "mission abandonnée"),
    "PRNQ": ("loisirs", "prison abandonnée"),
}


def download(path: Path) -> None:
    print(f"→ téléchargement {URL}", flush=True)
    for attempt in range(5):
        try:
            req = urllib.request.Request(URL, headers={"User-Agent": UA})
            tmp = path.with_suffix(".part")
            with urllib.request.urlopen(req, timeout=600) as r, open(tmp, "wb") as f:
                total = int(r.headers.get("Content-Length", 0))
                while chunk := r.read(8 << 20):
                    f.write(chunk)
            if total and tmp.stat().st_size != total:
                raise OSError("téléchargement incomplet")
            tmp.replace(path)
            print(f"  {path.stat().st_size / 1e6:.0f} Mo", flush=True)
            return
        except Exception as e:  # noqa: BLE001
            print(f"  échec ({e}), nouvel essai…", flush=True)
            time.sleep(30 * (attempt + 1))
    raise SystemExit("Impossible de télécharger GeoNames")


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    CACHE.mkdir(parents=True, exist_ok=True)
    src = CACHE / "geonames-allCountries.zip"
    if not src.exists() or "--fresh" in sys.argv:
        download(src)

    spots = []
    with zipfile.ZipFile(src) as z, z.open("allCountries.txt") as f:
        for line in io.TextIOWrapper(f, encoding="utf-8"):
            p = line.split("\t")
            code = CODES.get(p[7])
            if not code:
                continue
            try:
                lat, lon = float(p[4]), float(p[5])
            except ValueError:
                continue
            cat, label = code
            spots.append([round(lat, 5), round(lon, 5), p[1], cat, label, "G" + p[0]])

    if len(spots) < 1000:
        sys.exit(f"Seulement {len(spots)} lieux : fichier précédent conservé")
    OUT.write_text(json.dumps({
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "GeoNames (CC-BY 4.0)",
        "fields": ["lat", "lon", "name", "category", "type", "geonames_id"],
        "spots": spots,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    counts: dict[str, int] = {}
    for s in spots:
        counts[s[4]] = counts.get(s[4], 0) + 1
    print(f"{len(spots)} spots écrits dans {OUT.relative_to(ROOT)}")
    for c, n in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {c:28s} {n}")


if __name__ == "__main__":
    main()
