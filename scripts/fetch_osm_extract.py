#!/usr/bin/env python3
"""
Extrait les lieux abandonnés / désaffectés / en ruine des extraits officiels
OpenStreetMap (Geofabrik) et génère un fichier de lieux.

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
    python scripts/fetch_osm_extract.py --out lot.json URL1 URL2 …
        # monde entier : chaque machine GitHub traite un lot d'extraits
        # (voir plan_regions.py), téléchargés et supprimés un par un
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import osmium

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ipv4  # noqa: E402,F401  (évite « Network is unreachable » sur GitHub)
from fetch_spots import categorize, describe, keep  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUTDIR = ROOT / "data" / "osm"   # un fichier par région Geofabrik
CACHE = ROOT / "data" / ".cache"
URL = "https://download.geofabrik.de/europe/france/france-latest.osm.pbf"
UA = "urbex-map/1.0 (open-source map project)"

# Étiquettes retenues : valeur précise…
EXACT = {
    "abandoned": {"yes"}, "disused": {"yes"}, "ruins": {"yes"},
    "historic": {"ruins", "bunker", "mine"},
    "building": {"ruins", "abandoned", "disused", "bunker"}, "military": {"bunker"},
    "landuse": {"brownfield"},                                   # friches
    "abandoned:railway": {"station", "halt"}, "disused:railway": {"station", "halt"},  # gares (pas les voies)
    "abandoned:power": {"plant", "substation"}, "disused:power": {"plant", "substation"},
    "abandoned:aeroway": {"aerodrome", "hangar", "terminal", "control_tower", "airstrip", "heliport"},
    "disused:aeroway": {"aerodrome", "hangar", "terminal", "control_tower", "airstrip", "heliport"},
}
# … ou n'importe quelle valeur
ANY_VALUE = ("abandoned:building", "abandoned:amenity", "abandoned:man_made", "abandoned:industrial",
             "disused:amenity", "disused:building", "disused:man_made",
             "abandoned:place",                                  # villages abandonnés
             "abandoned:military", "disused:military", "abandoned:tourism", "disused:tourism",
             "abandoned:leisure", "disused:leisure", "abandoned:landuse", "disused:landuse")

# Expressions pour « osmium tags-filter »
OSMIUM_FILTERS = [f"nwr/{k}={','.join(sorted(v))}" for k, v in EXACT.items()] + [f"nwr/{k}" for k in ANY_VALUE]


def matches(tags: dict) -> bool:
    for k, vals in EXACT.items():
        if tags.get(k) in vals:
            return True
    return any(k in tags for k in ANY_VALUE)


def download(url: str, path: Path) -> None:
    print(f"→ téléchargement {url}", flush=True)
    for attempt in range(6):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            done = 0
            with urllib.request.urlopen(req, timeout=600) as r, open(path, "wb") as f:
                total = int(r.headers.get("Content-Length", 0))
                while chunk := r.read(8 << 20):
                    f.write(chunk)
                    done += len(chunk)
                    if total and done % (1 << 30) < (8 << 20):
                        print(f"  {done / 1e9:.1f} / {total / 1e9:.1f} Go", flush=True)
            if total and path.stat().st_size != total:
                raise OSError("téléchargement incomplet")
            print(f"  terminé : {path.stat().st_size / 1e9:.2f} Go", flush=True)
            return
        except Exception as e:  # noqa: BLE001
            print(f"  échec ({e}), nouvel essai…", flush=True)
            time.sleep(30 * (attempt + 1))
    raise OSError(f"impossible de télécharger {url}")


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


def extract(src: Path) -> list:
    work = prefilter(src)
    print("→ lecture des objets…", flush=True)
    h = Collector()
    h.apply_file(str(work), locations=True, idx="flex_mem")
    print(f"  {len(h.found)} objets correspondants", flush=True)
    if work != src:
        work.unlink()
    spots = []
    for t, oid, lat, lon, tags in h.found:
        if keep(tags):
            spots.append([round(lat, 5), round(lon, 5), tags.get("name", ""), categorize(tags), describe(tags), f"{t}{oid}"])
    return spots


def region_id(url: str) -> str:
    """https://download.geofabrik.de/europe/france-latest.osm.pbf → europe_france"""
    path = url.split("download.geofabrik.de/", 1)[-1].replace("-latest.osm.pbf", "")
    return path.replace("/", "_")


def save(path: Path, spots: list, source: str) -> None:
    # Un même objet OSM n'est gardé qu'une fois (relations découpées, nœuds en double…)
    uniq, seen = [], set()
    for s in spots:
        if s[5] not in seen:
            seen.add(s[5])
            uniq.append(s)
    payload = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": source,
        "fields": ["lat", "lon", "name", "category", "osm_type", "osm_id"],
        "spots": uniq,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    counts: dict[str, int] = {}
    for s in uniq:
        counts[s[3]] = counts.get(s[3], 0) + 1
    print(f"{len(uniq)} spots écrits dans {path.name}  " + ", ".join(f"{c} {n}" for c, n in sorted(counts.items(), key=lambda x: -x[1])), flush=True)


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    args = sys.argv[1:]
    outdir = OUTDIR
    if "--outdir" in args:
        i = args.index("--outdir")
        outdir = Path(args[i + 1])
        del args[i:i + 2]

    if args and not args[0].startswith("http"):  # fichier local
        src = Path(args[0])
        save(outdir / (src.name.split(".")[0].replace("-latest", "") + ".json"), extract(src), "© contributeurs OpenStreetMap (ODbL)")
        return

    CACHE.mkdir(parents=True, exist_ok=True)
    failed = []
    for url in args or [URL]:
        src = CACHE / url.rsplit("/", 1)[-1]
        try:
            if not (src.exists() and url == URL):
                download(url, src)
            spots = extract(src)
            save(outdir / f"{region_id(url)}.json", spots, f"© contributeurs OpenStreetMap (ODbL), extrait Geofabrik {region_id(url)}")
        except Exception as e:  # noqa: BLE001
            # La région garde ses données de la fois précédente
            print(f"!! {url} a échoué : {e}", flush=True)
            failed.append(url)
        finally:
            if url != URL:
                src.unlink(missing_ok=True)  # libère le disque pour l'extrait suivant
    if failed:
        print(f"{len(failed)} extrait(s) en échec : " + " ".join(region_id(u) for u in failed))


if __name__ == "__main__":
    main()
