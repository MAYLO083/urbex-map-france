#!/usr/bin/env python3
"""
Extrait les lieux abandonnés / désaffectés / en ruine de l'extrait officiel
OpenStreetMap de la France (Geofabrik) et génère data/spots.json.

Contrairement à fetch_spots.py (API Overpass, souvent saturée), cette méthode
ne dépend d'aucun serveur partagé : on télécharge le fichier .osm.pbf complet
(~5 Go) puis on le filtre localement.

Dépendances :
    pip install osmium               # pyosmium (lecture du fichier)
    apt install osmium-tool          # facultatif mais conseillé pour la France entière :
                                     # pré-filtre rapide qui évite de charger 4,7 Go en mémoire

Usage :
    python scripts/fetch_osm_extract.py                  # télécharge la France puis filtre
    python scripts/fetch_osm_extract.py chemin/vers.pbf  # utilise un fichier déjà présent
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import osmium

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_spots import categorize, describe, keep  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "spots.json"
CACHE = ROOT / "data" / ".cache"
URL = "https://download.geofabrik.de/europe/france/france-latest.osm.pbf"
UA = "urbex-map-france/1.0 (open-source map project)"

FRANCE = (41.3, 51.2, -5.3, 9.7)  # métropole + Corse

# Mêmes critères que la requête Overpass de fetch_spots.py
EXACT = {
    "abandoned": {"yes"}, "disused": {"yes"}, "ruins": {"yes"}, "historic": {"ruins"},
    "building": {"ruins", "abandoned", "disused", "bunker"}, "military": {"bunker"},
}
ANY_VALUE = ("abandoned:building", "abandoned:amenity", "abandoned:man_made", "abandoned:industrial",
             "disused:amenity", "disused:building", "disused:man_made")

# Expressions pour « osmium tags-filter »
OSMIUM_FILTERS = [f"nwr/{k}={','.join(sorted(v))}" for k, v in EXACT.items()] + [f"nwr/{k}" for k in ANY_VALUE]


def matches(tags: dict) -> bool:
    for k, vals in EXACT.items():
        if tags.get(k) in vals:
            return True
    return any(k in tags for k in ANY_VALUE)


def download(path: Path) -> None:
    print(f"→ téléchargement {URL}", flush=True)
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    done = 0
    with urllib.request.urlopen(req, timeout=600) as r, open(path, "wb") as f:
        total = int(r.headers.get("Content-Length", 0))
        while chunk := r.read(8 << 20):
            f.write(chunk)
            done += len(chunk)
            if total and done % (512 << 20) < (8 << 20):
                print(f"  {done / 1e9:.1f} / {total / 1e9:.1f} Go", flush=True)
    print(f"  terminé : {path.stat().st_size / 1e9:.2f} Go", flush=True)


def prefilter(src: Path) -> Path:
    """Garde seulement les objets intéressants (+ les nœuds de leurs contours)."""
    exe = shutil.which("osmium")
    if not exe:
        print("  (osmium-tool absent : lecture directe du fichier complet)", flush=True)
        return src
    dst = src.with_name(src.stem.replace(".osm", "") + "-urbex.osm.pbf")
    print("→ pré-filtrage avec osmium tags-filter…", flush=True)
    subprocess.run([exe, "tags-filter", str(src), *OSMIUM_FILTERS, "-o", str(dst), "--overwrite"], check=True)
    print(f"  {dst.stat().st_size / 1e6:.1f} Mo après filtrage", flush=True)
    return dst


class Collector(osmium.SimpleHandler):
    def __init__(self) -> None:
        super().__init__()
        self.way_centers: dict[int, tuple[float, float]] = {}
        self.found: list[tuple[str, int, float, float, dict]] = []

    def node(self, n) -> None:
        if not n.tags or not n.location.valid():
            return
        tags = dict(n.tags)
        if matches(tags):
            self.found.append(("n", n.id, n.location.lat, n.location.lon, tags))

    def way(self, w) -> None:
        lats, lons = [], []
        for nd in w.nodes:
            if nd.location.valid():
                lats.append(nd.location.lat)
                lons.append(nd.location.lon)
        if not lats:
            return
        c = (sum(lats) / len(lats), sum(lons) / len(lons))
        self.way_centers[w.id] = c
        if w.tags:
            tags = dict(w.tags)
            if matches(tags):
                self.found.append(("w", w.id, c[0], c[1], tags))

    def relation(self, r) -> None:
        if not r.tags:
            return
        tags = dict(r.tags)
        if not matches(tags):
            return
        pts = [self.way_centers[m.ref] for m in r.members if m.type == "w" and m.ref in self.way_centers]
        if pts:
            self.found.append(("r", r.id, sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts), tags))


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    if len(sys.argv) > 1:
        src = Path(sys.argv[1])
    else:
        CACHE.mkdir(parents=True, exist_ok=True)
        src = CACHE / "france-latest.osm.pbf"
        if not src.exists():
            download(src)
    work = prefilter(src)

    print("→ lecture des objets…", flush=True)
    h = Collector()
    h.apply_file(str(work), locations=True, idx="flex_mem")
    print(f"  {len(h.found)} objets correspondants", flush=True)

    spots, seen = [], set()
    for t, oid, lat, lon, tags in h.found:
        if not keep(tags):
            continue
        if not (FRANCE[0] <= lat <= FRANCE[1] and FRANCE[2] <= lon <= FRANCE[3]):
            continue
        key = (round(lat, 4), round(lon, 4))
        if key in seen:
            continue
        seen.add(key)
        spots.append([round(lat, 5), round(lon, 5), tags.get("name", ""), categorize(tags), describe(tags), f"{t}{oid}"])

    payload = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "© contributeurs OpenStreetMap (ODbL), extrait Geofabrik",
        "fields": ["lat", "lon", "name", "category", "osm_type", "osm_id"],
        "spots": spots,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    counts: dict[str, int] = {}
    for s in spots:
        counts[s[3]] = counts.get(s[3], 0) + 1
    print(f"{len(spots)} spots écrits dans {OUT.relative_to(ROOT)}")
    for c, n in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {c:12s} {n}")


if __name__ == "__main__":
    main()
