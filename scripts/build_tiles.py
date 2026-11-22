#!/usr/bin/env python3
"""
Prépare les données pour un chargement rapide de la carte (« tuiles »).

Lit toutes les sources (data/osm/*.json pour OpenStreetMap, data/spots_*.json
pour les autres), fusionne les doublons entre sources, puis écrit dans data/tiles/ :

  meta.json      version, date, totaux (pour les compteurs des filtres)
  overview.json  vue du monde : une bulle par case de 4° avec les comptes
                 par catégorie/source
  o/<Y>_<X>.json vue régionale : une bulle par case de 1°, groupées par
                 carrés de 10° (chargés seulement pour la zone regardée)
  c/<y>_<x>.json les lieux d'une case de 0,5° × 0,5° (chargés seulement
                 quand on zoome sur cette zone)
  s/<début>.json index de recherche découpé selon le début des mots
                 (on ne télécharge que le morceau du mot tapé)

Le site ne télécharge donc que ce qui est visible.

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

TILE = 0.5        # taille d'une case de données (degrés)
REGION = 1.0      # bulles de la vue régionale (degrés)
CHUNK = 10        # fichiers de la vue régionale (degrés)
WORLD = 4.0       # bulles de la vue du monde (degrés)
SHARD_MAX = 3000  # lieux max par morceau de l'index de recherche

# Fichier de chaque source, par ordre de fiabilité (la première gagne en cas de doublon)
SOURCES = {
    "communaute": "spots_communaute.json",
    "wikidata": "spots_wikidata.json",
    "merimee": "spots_merimee.json",
    "osm": "osm",  # dossier : un fichier par région du monde
    "friches": "spots_friches.json",
    "casias": "spots_casias.json",
}

STOP = set("de du des la le les et au aux en sur sous ancien ancienne anciens anciennes site friche usine lieu "
           "the of and old former der die das und alte ehemalige del di da do dos el".split())


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
        files = sorted(p.glob("*.json")) if p.is_dir() else [p] if p.exists() else []
        if not files:
            print(f"  (source absente : {fname})")
            continue
        n, ids = 0, set()
        for f in files:
            data = json.loads(f.read_text(encoding="utf-8"))
            generated = max(generated, data.get("generated", ""))
            for s in data["spots"]:
                if s[5] in ids:  # même objet dans deux extraits voisins
                    continue
                ids.add(s[5])
                # [lat, lon, nom, catégorie, description, id, image]
                spots.append({"lat": s[0], "lon": s[1], "name": s[2] or "", "cat": s[3], "desc": s[4] or "",
                              "id": s[5], "img": s[6] if len(s) > 6 else "", "src": src, "also": []})
                n += 1
        print(f"  {src:11s} {n:8d}" + (f"  ({len(files)} fichiers)" if len(files) > 1 else ""), flush=True)
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


WORD = re.compile(r"[\W_]+")
SAFE = set("abcdefghijklmnopqrstuvwxyz0123456789_")


# Mots trop courants pour servir d'entrée dans l'index (ils restent cherchables
# en complément d'un autre mot : « saint martin » passe par « martin »)
COMMON = STOP | set("saint sainte rue chemin route avenue lieu dit les des aux pour avec sans "
                    "station service garage atelier societe ets etablissements entreprise".split())


def words(name: str) -> set:
    """Les 3 mots les plus longs (et les plus distinctifs) du nom."""
    ws = {w for w in WORD.split(norm(name)) if len(w) >= 3 and not w.isdigit() and w not in COMMON}
    return set(sorted(ws, key=len, reverse=True)[:3])


def safe(prefix: str) -> str:
    """Nom de fichier sans caractère spécial (même règle que dans app.js)."""
    return "".join(c if c in SAFE else f"~{ord(c):x}." for c in prefix)


def shard_search(entries: list) -> tuple[dict, list]:
    """Index de recherche découpé selon le début des mots : 3 lettres, ou plus si le
    morceau est trop gros (« sta » → « stat », « stad »…). Un mot plus court que le
    préfixe va dans le morceau « …_ ». Un lieu apparaît dans le morceau de chacun de ses mots."""
    pairs = [(w, i) for i, (_, name) in enumerate(entries) for w in words(name)]
    shards: dict[str, set] = {}
    split: list = []

    def place(group: list, n: int) -> None:
        by: dict[str, list] = defaultdict(list)
        for w, i in group:
            by[w[:n] if len(w) >= n else w + "_"].append((w, i))
        for p, g in by.items():
            ids = {i for _, i in g}
            if len(ids) > SHARD_MAX and n < 8 and not p.endswith("_"):
                split.append(p)
                place(g, n + 1)
            else:
                shards[p] = set(sorted(ids)[:SHARD_MAX])

    place(pairs, 3)
    return {p: [entries[i][0] for i in sorted(ids)] for p, ids in shards.items()}, sorted(split)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    print("→ lecture des sources", flush=True)
    spots, generated = load()
    if not spots:
        sys.exit("Aucune donnée")
    kept, merged = dedupe(spots)
    print(f"→ {merged} doublons fusionnés, {len(kept)} lieux uniques", flush=True)

    tiles: dict[str, list] = defaultdict(list)
    levels = {"world": (WORLD, {}), "region": (REGION, {})}
    totals: dict[str, int] = defaultdict(int)
    search = []
    for s in kept:
        row = [round(s["lat"], 5), round(s["lon"], 5), s["name"], s["cat"], s["desc"], s["id"], s["img"], s["src"]]
        if s["also"]:
            row.append(s["also"])
        t = key(s["lat"], s["lon"], TILE)
        tiles[t].append(row)
        ck = count_key(s)
        for size, cells in levels.values():
            o = cells.setdefault(key(s["lat"], s["lon"], size),
                                 {"lat": 0.0, "lon": 0.0, "n": defaultdict(int), "t": set(), "count": 0})
            o["lat"] += s["lat"]
            o["lon"] += s["lon"]
            o["count"] += 1
            o["n"][ck] += 1
            o["t"].add(t)
        totals[ck] += 1
        if s["name"]:
            search.append(([round(s["lat"], 4), round(s["lon"], 4), s["name"], s["cat"], s["src"], s["id"]], s["name"]))

    if OUT.exists():
        shutil.rmtree(OUT)
    for d in ("c", "o", "s"):
        (OUT / d).mkdir(parents=True)

    def dump(p: Path, obj) -> None:
        p.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    def cell(o: dict, with_tiles: bool) -> dict:
        c = {"c": [round(o["lat"] / o["count"], 4), round(o["lon"] / o["count"], 4)], "n": dict(o["n"])}
        if with_tiles:
            c["t"] = sorted(o["t"])
        return c

    for t, rows in tiles.items():
        dump(OUT / "c" / f"{t}.json", rows)
    dump(OUT / "overview.json", [cell(o, False) for o in levels["world"][1].values()])

    chunks: dict[str, list] = defaultdict(list)  # carrés de 10° → bulles de 1°
    for k, o in levels["region"][1].items():
        y, x = map(int, k.split("_"))
        chunks[f"{math.floor(y * REGION / CHUNK)}_{math.floor(x * REGION / CHUNK)}"].append(cell(o, True))
    for k, cells in chunks.items():
        dump(OUT / "o" / f"{k}.json", cells)

    shards, split = shard_search(search)
    for p, rows in shards.items():
        dump(OUT / "s" / f"{safe(p)}.json", rows)

    version = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    dump(OUT / "meta.json", {
        "v": version, "generated": generated, "tile": TILE, "region": REGION, "chunk": CHUNK,
        "count": len(kept), "merged": merged, "totals": dict(totals),
        "chunks": sorted(chunks), "split": split,
    })

    size = sum(p.stat().st_size for p in OUT.rglob("*.json"))
    files = sum(1 for _ in OUT.rglob("*.json"))
    biggest = max(tiles.values(), key=len)
    big_shard = max(shards.values(), key=len)
    print(f"→ {len(tiles)} cases, {len(levels['region'][1])} bulles régionales, {len(levels['world'][1])} bulles monde, "
          f"{len(search)} noms en {len(shards)} morceaux (plus gros : {len(big_shard)}), "
          f"{files} fichiers, {size / 1e6:.1f} Mo au total (plus grosse case : {len(biggest)} lieux)")


if __name__ == "__main__":
    main()
