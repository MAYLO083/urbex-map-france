#!/usr/bin/env python3
"""
Récupère les lieux abandonnés / désaffectés / en ruine de France
depuis OpenStreetMap (API Overpass) et génère data/spots.json.

Aucune dépendance externe : Python 3.9+ suffit.

Usage :
    python scripts/fetch_spots.py
"""

from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "spots.json"

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]

# France métropolitaine + Corse (relation admin_level=2 couvre aussi l'outre-mer,
# on garde tout ce qui est dans l'aire "FR").
QUERY = r"""
[out:json][timeout:240][bbox:{bbox}];
area["ISO3166-1"="FR"][admin_level=2]->.fr;
(
  nwr["abandoned"="yes"](area.fr);
  nwr["disused"="yes"](area.fr);
  nwr["ruins"="yes"](area.fr);
  nwr["historic"="ruins"](area.fr);
  nwr["building"~"^(ruins|abandoned|disused)$"](area.fr);
  nwr["abandoned:building"](area.fr);
  nwr["abandoned:amenity"](area.fr);
  nwr["abandoned:man_made"](area.fr);
  nwr["abandoned:industrial"](area.fr);
  nwr["disused:amenity"](area.fr);
  nwr["disused:building"](area.fr);
  nwr["disused:man_made"](area.fr);
  nwr["military"="bunker"](area.fr);
  nwr["building"="bunker"](area.fr);
);
out center tags qt;
"""

# Objets linéaires / sans intérêt pour l'exploration : on les ignore.
EXCLUDE_KEYS = {
    "highway", "railway", "waterway", "power", "barrier", "route",
    "pipeline", "aerialway", "boundary", "natural",
}
EXCLUDE_VALUES = {
    ("man_made", "pipeline"), ("man_made", "embankment"), ("man_made", "cutline"),
    ("amenity", "parking"), ("amenity", "bench"), ("amenity", "waste_basket"),
    ("amenity", "telephone"), ("amenity", "vending_machine"), ("amenity", "post_box"),
    ("amenity", "fuel"), ("amenity", "recycling"), ("amenity", "drinking_water"),
    ("man_made", "survey_point"), ("man_made", "manhole"), ("man_made", "street_cabinet"),
}
# Ces clés de lignes sont acceptées si l'objet est un bâtiment (gare, dépôt…)
LINE_OK_IF = {"building", "abandoned:building", "disused:building"}


def tag_any(tags: dict, *keys: str) -> str:
    for k in keys:
        for prefix in ("", "abandoned:", "disused:", "was:", "ruins:"):
            v = tags.get(prefix + k)
            if v:
                return v
    return ""


def categorize(tags: dict) -> str:
    """Classe le lieu dans une grande catégorie lisible."""
    t = {k: v.lower() for k, v in tags.items()}
    joined = " ".join(f"{k}={v}" for k, v in t.items())
    name = t.get("name", "")

    if t.get("military") == "bunker" or t.get("building") == "bunker" or "bunker" in joined \
            or "blockhaus" in name or tag_any(t, "military") or "fort " in name or name.startswith("fort"):
        return "militaire"
    if any(w in joined for w in ("hospital", "clinic", "sanatorium", "asylum")) \
            or any(w in name for w in ("sanatorium", "hôpital", "hopital", "préventorium", "asile", "clinique")):
        return "hopital"
    if any(w in joined for w in ("place_of_worship", "church", "chapel", "monastery", "abbey", "convent", "cathedral")) \
            or any(w in name for w in ("église", "chapelle", "abbaye", "prieuré", "couvent", "monastère")):
        return "religieux"
    if any(w in joined for w in ("castle", "manor", "palace", "chateau", "château", "fortification", "citywalls")) \
            or any(w in name for w in ("château", "manoir", "castel", "tour ", "donjon")):
        return "chateau"
    if any(w in joined for w in ("industrial", "factory", "works", "mine", "quarry", "mill", "kiln",
                                  "chimney", "silo", "gasometer", "power_plant", "warehouse", "watermill",
                                  "windmill", "adit", "mineshaft", "crane", "storage_tank")) \
            or any(w in name for w in ("usine", "moulin", "mine", "carrière", "forge", "filature", "sucrerie",
                                       "tannerie", "verrerie", "papeterie", "distillerie", "fonderie")):
        return "industriel"
    if any(w in joined for w in ("station", "railway", "train", "tunnel", "aerodrome", "airport", "hangar",
                                  "lighthouse", "bridge")) \
            or any(w in name for w in ("gare", "tunnel", "phare", "aérodrome")):
        return "transport"
    if any(w in joined for w in ("school", "hotel", "restaurant", "cinema", "theatre", "swimming_pool",
                                  "sports_centre", "stadium", "camp_site", "colonie", "theme_park",
                                  "nightclub", "casino", "shop", "pub", "bar", "cafe", "retail", "commercial")) \
            or any(w in name for w in ("école", "hôtel", "colonie", "piscine", "cinéma", "discothèque")):
        return "loisirs"
    if any(w in joined for w in ("house", "residential", "farm", "barn", "detached", "apartments",
                                  "villa", "cabin", "hut", "shed")) \
            or any(w in name for w in ("maison", "ferme", "villa", "mas ", "grange", "bastide")):
        return "habitation"
    if t.get("historic") == "ruins" or t.get("ruins") == "yes" or t.get("building") == "ruins":
        return "ruines"
    return "autre"


def describe(tags: dict) -> str:
    """Petit libellé du type d'objet OSM (ex. 'building=industrial')."""
    for k in ("abandoned:building", "abandoned:amenity", "abandoned:man_made", "abandoned:industrial",
              "disused:building", "disused:amenity", "disused:man_made", "ruins:building",
              "historic", "military", "amenity", "man_made", "industrial", "building", "landuse", "tourism"):
        v = tags.get(k)
        if v and v not in ("yes",):
            return f"{k}={v}"
    if tags.get("building"):
        return "building"
    return ""


def keep(tags: dict) -> bool:
    if not tags:
        return False
    has_building = any(tags.get(k) for k in LINE_OK_IF)
    if not has_building:
        if any(k in tags for k in EXCLUDE_KEYS):
            return False
    for k, v in EXCLUDE_VALUES:
        if tags.get(k) == v or tags.get("abandoned:" + k) == v or tags.get("disused:" + k) == v:
            return False
    # Un point sans nom ni type d'objet n'apporte rien
    if not tags.get("name") and not describe(tags):
        return False
    return True


# France métropolitaine + Corse, découpée en tuiles pour ne pas surcharger Overpass
LAT_MIN, LAT_MAX, LAT_STEP = 41.3, 51.2, 1.0
LON_MIN, LON_MAX, LON_STEP = -5.3, 9.7, 1.5
CACHE = ROOT / "data" / ".cache"


def tiles():
    lat = LAT_MIN
    while lat < LAT_MAX:
        lon = LON_MIN
        while lon < LON_MAX:
            yield (lat, lon, min(lat + LAT_STEP, LAT_MAX), min(lon + LON_STEP, LON_MAX))
            lon += LON_STEP
        lat += LAT_STEP


def fetch_tile(bbox: tuple) -> list:
    q = QUERY.replace("{bbox}", ",".join(f"{v:.2f}" for v in bbox))
    data = urllib.parse.urlencode({"data": q}).encode()
    last_err = None
    for attempt in range(14):
        url = ENDPOINTS[attempt % len(ENDPOINTS)]
        try:
            req = urllib.request.Request(
                url, data=data,
                headers={"User-Agent": "urbex-map-france/1.0 (open-source map project)"},
            )
            with urllib.request.urlopen(req, timeout=300) as r:
                res = json.load(r)
            if "remark" in res and "runtime error" in res["remark"]:
                raise RuntimeError(res["remark"][:120])
            return res.get("elements", [])
        except Exception as e:  # noqa: BLE001
            last_err = e
            wait = min(15 * 2 ** (attempt // len(ENDPOINTS)), 300)
            print(f"    échec ({url.split('/')[2]}) : {e} — nouvel essai dans {wait}s", flush=True)
            time.sleep(wait)
    raise SystemExit(f"Impossible de récupérer la tuile {bbox} : {last_err}\n"
                     "Relance le script plus tard : les tuiles déjà téléchargées sont conservées.")


def fetch() -> list:
    """Télécharge chaque tuile, avec un cache pour reprendre là où on s'est arrêté.
    Le cache est vidé à la fin d'un téléchargement complet."""
    CACHE.mkdir(parents=True, exist_ok=True)
    all_tiles = list(tiles())
    elements = []
    for i, bbox in enumerate(all_tiles, 1):
        f = CACHE / ("tile_" + "_".join(f"{v:.2f}" for v in bbox) + ".json")
        if f.exists():
            els = json.loads(f.read_text(encoding="utf-8"))
            src = "cache"
        else:
            els = fetch_tile(bbox)
            f.write_text(json.dumps(els), encoding="utf-8")
            src = "téléchargée"
            time.sleep(3)
        elements.extend(els)
        print(f"  tuile {i:3d}/{len(all_tiles)} {src} → {len(els)} objets", flush=True)
    return elements


def clear_cache() -> None:
    for f in CACHE.glob("tile_*.json"):
        f.unlink()


def main() -> None:  # noqa: C901
    # Console Windows : forcer l'UTF-8 pour les accents et flèches
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    elements = fetch()
    print(f"{len(elements)} objets bruts reçus")

    spots = []
    seen = set()
    for el in elements:
        tags = el.get("tags", {})
        if not keep(tags):
            continue
        if "center" in el:
            lat, lon = el["center"]["lat"], el["center"]["lon"]
        elif "lat" in el:
            lat, lon = el["lat"], el["lon"]
        else:
            continue
        key = (round(lat, 4), round(lon, 4))
        if key in seen:
            continue
        seen.add(key)
        spots.append([
            round(lat, 5),
            round(lon, 5),
            tags.get("name", ""),
            categorize(tags),
            describe(tags),
            f"{el['type'][0]}{el['id']}",  # n123 / w456 / r789
        ])

    payload = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "© contributeurs OpenStreetMap (ODbL)",
        "fields": ["lat", "lon", "name", "category", "osm_type", "osm_id"],
        "spots": spots,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    clear_cache()

    counts: dict[str, int] = {}
    for s in spots:
        counts[s[3]] = counts.get(s[3], 0) + 1
    print(f"{len(spots)} spots écrits dans {OUT.relative_to(ROOT)}")
    for c, n in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {c:12s} {n}")


if __name__ == "__main__":
    sys.exit(main())
