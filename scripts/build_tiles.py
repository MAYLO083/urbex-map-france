#!/usr/bin/env python3
"""
Prépare les données pour un chargement rapide de la carte (« tuiles »).

Lit toutes les sources (data/spots*.json), fusionne les doublons entre
sources, puis écrit dans data/tiles/ :

  meta.json      version, date, totaux (pour les compteurs des filtres)
  overview.json  une bulle par case de 1° avec les comptes par catégorie/source
                 (vue dézoomée : quelques Ko au lieu de tous les lieux)
  c/<y>_<x>.json les lieux d'une case de 0,5° × 0,5° (chargés seulement
                 quand on regarde cette zone)
  search.json    index des lieux nommés (chargé seulement si on cherche)

Le site ne télécharge donc que ce qui est visible : ça marche aussi bien pour
la France que pour le monde entier.

Usage :
    python scripts/build_tiles.py
"""

from __future__ import annotations

import json
import math
import re
import shutil
import sys
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = DATA / "tiles"

TILE = 0.5       # taille d'une case de données (degrés)
OVERVIEW = 1.0   # taille d'une case de la vue dézoomée (degrés)

# Fichier de chaque source, par ordre de fiabilité (la première gagne en cas de doublon)
SOURCES = {
    "communaute": "spots_communaute.json",
    "wikidata": "spots_wikidata.json",
    "merimee": "spots_merimee.json",
    "osm": "spots.json",
    "friches": "spots_friches.json",
    "casias": "spots_casias.json",
}

STOP = set("de du des la le les et au aux en sur sous ancien ancienne anciens anciennes site friche usine lieu".split())


def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def tokens(name: str) -> frozenset:
    n = norm(re.sub(r"\(.*?\)", " ", name or ""))
    return frozenset(w for w in re.split(r"[^a-z0-9]+", n) if len(w) > 2 and w not in STOP)


def similar(a: frozenset, b: frozenset) -> bool:
    if not a or not b:
        return False
    return len(a & b) / min(len(a), len(b)) >= 0.6


def load() -> tuple[list, str]:
    spots, generated = [], ""
    for src, fname in SOURCES.items():
        p = DATA / fname
        if not p.exists():
            print(f"  (source absente : {fname})")
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        generated = max(generated, data.get("generated", ""))
        for s in data["spots"]:
            # [lat, lon, nom, catégorie, description, id, image]
            spots.append({"lat": s[0], "lon": s[1], "name": s[2] or "", "cat": s[3], "desc": s[4] or "",
                          "id": s[5], "img": s[6] if len(s) > 6 else "", "src": src, "also": []})
        print(f"  {src:11s} {len(data['spots']):7d}")
    return spots, generated


def dedupe(spots: list) -> tuple[list, int]:
    """Deux fiches de sources différentes = même lieu à < 30 m, ou à < 100 m avec un nom proche.
    Dans une même source : seulement les fiches en double (même nom, < 30 m)."""
    cell = 0.0015
    grid: dict[tuple, list] = defaultdict(list)
    kept, merged = [], 0
    for s in spots:  # déjà triées par fiabilité (ordre des sources)
        cx, cy = int(math.floor(s["lat"] / cell)), int(math.floor(s["lon"] / cell))
        cos = math.cos(math.radians(s["lat"]))
        twin, best = None, float("inf")
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for k in grid.get((cx + dx, cy + dy), ()):
                    same = k["src"] == s["src"]
                    if same and (not s["name"] or k["name"] != s["name"]):
                        continue
                    d = math.hypot((k["lat"] - s["lat"]) * 111320, (k["lon"] - s["lon"]) * 111320 * cos)
                    if d >= best:
                        continue
                    if d < 30 or (not same and d < 100 and similar(
                            k.setdefault("tok", tokens(k["name"])), s.setdefault("tok", tokens(s["name"])))):
                        twin, best = k, d
        if twin:
            twin["also"].append([s["src"], s["id"]])
            for f in ("name", "img", "desc"):
                if not twin[f] and s[f]:
                    twin[f] = s[f]
            if twin["cat"] == "autre" and s["cat"] != "autre":
                twin["cat"] = s["cat"]
            merged += 1
            continue
        grid[(cx, cy)].append(s)
        kept.append(s)
    return kept, merged


def key(lat: float, lon: float, size: float) -> str:
    return f"{math.floor(lat / size)}_{math.floor(lon / size)}"


def count_key(s: dict) -> str:
    return f"{s['cat']}|{s['src']}|{1 if s['name'] else 0}"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    print("→ lecture des sources")
    spots, generated = load()
    if not spots:
        sys.exit("Aucune donnée")
    kept, merged = dedupe(spots)
    print(f"→ {merged} doublons fusionnés, {len(kept)} lieux uniques")

    tiles: dict[str, list] = defaultdict(list)
    overview: dict[str, dict] = {}
    totals: dict[str, int] = defaultdict(int)
    search = []
    for s in kept:
        row = [round(s["lat"], 5), round(s["lon"], 5), s["name"], s["cat"], s["desc"], s["id"], s["img"], s["src"]]
        if s["also"]:
            row.append(s["also"])
        t = key(s["lat"], s["lon"], TILE)
        tiles[t].append(row)

        o = overview.setdefault(key(s["lat"], s["lon"], OVERVIEW), {"lat": 0.0, "lon": 0.0, "n": defaultdict(int), "t": set(), "count": 0})
        o["lat"] += s["lat"]
        o["lon"] += s["lon"]
        o["count"] += 1
        o["n"][count_key(s)] += 1
        o["t"].add(t)
        totals[count_key(s)] += 1
        if s["name"]:
            search.append([row[0], row[1], s["name"], s["cat"], s["src"], s["id"]])

    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "c").mkdir(parents=True)
    dump = lambda p, obj: p.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")  # noqa: E731

    for t, rows in tiles.items():
        dump(OUT / "c" / f"{t}.json", rows)
    dump(OUT / "overview.json", [
        {"c": [round(o["lat"] / o["count"], 4), round(o["lon"] / o["count"], 4)], "t": sorted(o["t"]), "n": dict(o["n"])}
        for o in overview.values()
    ])
    dump(OUT / "search.json", search)
    version = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    dump(OUT / "meta.json", {
        "v": version, "generated": generated, "tile": TILE, "overview": OVERVIEW,
        "count": len(kept), "merged": merged, "totals": dict(totals),
    })

    size = sum(p.stat().st_size for p in OUT.rglob("*.json"))
    biggest = max(tiles.values(), key=len)
    print(f"→ {len(tiles)} cases, {len(overview)} bulles, {len(search)} noms indexés, "
          f"{size / 1e6:.1f} Mo au total (plus grosse case : {len(biggest)} lieux)")


if __name__ == "__main__":
    main()
