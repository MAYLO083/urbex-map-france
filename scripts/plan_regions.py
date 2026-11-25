#!/usr/bin/env python3
"""
Découpe le monde en extraits OpenStreetMap Geofabrik de taille raisonnable
(chaque extrait doit tenir sur le disque d'une machine GitHub Actions).

Part des continents ; tout extrait plus gros que LIMIT est remplacé par ses
sous-régions (pays, puis régions/États), récursivement.

Les extraits sont ensuite répartis en lots de taille équivalente (une machine
GitHub Actions traite un lot, plusieurs lots tournent en parallèle).

Sortie : la liste des lots en JSON sur la sortie standard
(ou au format GitHub Actions avec --github).

Usage :
    python scripts/plan_regions.py
    python scripts/plan_regions.py --github >> "$GITHUB_OUTPUT"
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ipv4  # noqa: E402,F401
from concurrent.futures import ThreadPoolExecutor

INDEX = "https://download.geofabrik.de/index-v1-nogeom.json"
UA = "urbex-map/1.0 (open-source map project)"
LIMIT = 3.5e9  # octets : au-delà on découpe en sous-régions
BATCH = 3e9    # octets traités par machine (en gros 10 à 20 min)


def size(url: str) -> int:
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": UA})
    for _ in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return int(r.headers.get("Content-Length", 0))
        except Exception:  # noqa: BLE001
            pass
    return 0


def main() -> None:
    with urllib.request.urlopen(urllib.request.Request(INDEX, headers={"User-Agent": UA}), timeout=120) as r:
        feats = [f["properties"] for f in json.load(r)["features"]]
    by_id = {f["id"]: f for f in feats}
    children: dict[str, list] = {}
    for f in feats:
        if f.get("parent"):
            children.setdefault(f["parent"], []).append(f["id"])

    def sizes(ids: list[str]) -> dict[str, int]:
        with ThreadPoolExecutor(8) as ex:
            return dict(zip(ids, ex.map(lambda i: size(by_id[i]["urls"]["pbf"]), ids)))

    todo = [f["id"] for f in feats if not f.get("parent")]
    out = []
    while todo:
        sz = sizes(todo)
        nxt = []
        for i in todo:
            if sz[i] > LIMIT and children.get(i):
                # « special_regions » = regroupements qui chevauchent les pays (dach, alps…) : on les saute
                skip = set(by_id[i].get("special_regions") or ())
                nxt.extend(c for c in children[i] if c not in skip)
            else:
                out.append({"id": i, "url": by_id[i]["urls"]["pbf"], "size": sz[i]})
        todo = nxt

    out.sort(key=lambda r: -r["size"])  # les plus longs d'abord
    print(f"{len(out)} extraits, {sum(r['size'] for r in out) / 1e9:.1f} Go au total, "
          f"le plus gros : {out[0]['id']} ({out[0]['size'] / 1e9:.1f} Go)", file=sys.stderr)
    # Répartition gloutonne : chaque extrait va dans le lot le moins chargé
    n = max(1, round(sum(r["size"] for r in out) / BATCH))
    lots = [{"lot": f"{k + 1:02d}", "size": 0, "regions": []} for k in range(n)]
    for r in out:
        b = min(lots, key=lambda x: x["size"])
        b["size"] += r["size"]
        b["regions"].append(r["url"])
    print(f"{n} lots (max {max(b['size'] for b in lots) / 1e9:.1f} Go)", file=sys.stderr)
    matrix = [{"lot": b["lot"], "urls": " ".join(b["regions"])} for b in lots]
    if "--github" in sys.argv:
        print("lots=" + json.dumps(matrix))
    else:
        print(json.dumps(matrix, indent=1))


if __name__ == "__main__":
    main()
