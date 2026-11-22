#!/usr/bin/env python3
"""
Récupère depuis Wikidata (données CC0) les lieux du monde entier marqués
désaffectés, abandonnés, hors service, en ruine, ainsi que les ruines
et villages fantômes. Génère data/spots_wikidata.json.

Les requêtes sont découpées en bandes de longitude (redécoupées en deux
automatiquement si Wikidata met trop de temps à répondre).

Usage :
    python scripts/fetch_wikidata.py
"""

from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_spots import categorize  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "spots_wikidata.json"
ENDPOINT = "https://query.wikidata.org/sparql"
UA = "urbex-map/1.0 (open-source map project)"

STATES = {
    "Q11639308": "désaffecté",
    "Q63065035": "abandonné",
    "Q56651571": "hors service",
    "Q56557159": "en ruine",
    "Q104664889": "fermé définitivement",
}
TYPES = {
    "Q109607": "ruines",
    "Q74047": "village fantôme",
}
# Types (libellé anglais de P31) sans intérêt : détruits, lignes entières, réseaux…
EXCLUDE_TYPES = (
    "destroyed", "demolished", "railway line", "tram line", "tram network", "tramway",
    "funicular", "transport network", "transit system", "bus stop", "bus line", "golf course",
    "boom barrier", "rail trail", "company", "business", "organization", "event",
    "people mover", "light rail", "railway network", "rapid transit",
)

# Une requête légère par valeur et par bande de longitude.
BANDS = [(-180, -30), (-30, 0), (0, 10), (10, 20), (20, 40), (40, 180)]
QUERY = """
SELECT ?i ?iLabel ?coord ?type ?img WHERE {
  %s
  ?i wdt:P625 ?coord.
  BIND(geof:longitude(?coord) AS ?lon)
  FILTER(?lon >= %s && ?lon < %s)
  FILTER NOT EXISTS { ?i wdt:P5817 wd:Q56556915 }
  OPTIONAL { ?i wdt:P31 ?type. }
  OPTIONAL { ?i wdt:P18 ?img. }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "fr,en,mul,de,es,it,pt,nl,pl,ru,ja,zh". }
}
"""
LABELS_QUERY = """
SELECT ?t ?en ?fr WHERE {
  VALUES ?t { %s }
  OPTIONAL { ?t rdfs:label ?en FILTER(lang(?en)="en") }
  OPTIONAL { ?t rdfs:label ?fr FILTER(lang(?fr)="fr") }
}
"""


def sparql(query: str, tries: int = 6) -> list | None:
    data = urllib.parse.urlencode({"query": query, "format": "json"}).encode()
    for attempt in range(tries):
        try:
            req = urllib.request.Request(ENDPOINT, data=data, headers={
                "User-Agent": UA, "Accept": "application/sparql-results+json",
                "Content-Type": "application/x-www-form-urlencoded"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)["results"]["bindings"]
        except Exception as e:  # noqa: BLE001
            wait = 20 * (attempt + 1)
            print(f"  échec : {e} — nouvel essai dans {wait}s", flush=True)
            time.sleep(wait)
    if tries > 2:
        raise SystemExit("Impossible d'interroger Wikidata, réessaie plus tard.")
    return None


def band(clause: str, lo: float, hi: float) -> list:
    """Une bande de longitude ; si Wikidata n'y arrive pas, on la coupe en deux."""
    res = sparql(QUERY % (clause, lo, hi), tries=2 if hi - lo > 1 else 6)
    if res is None:
        mid = (lo + hi) / 2
        print(f"    bande {lo}…{hi} trop lourde, découpée en deux", flush=True)
        return band(clause, lo, mid) + band(clause, mid, hi)
    return res


def fetch() -> list:
    rows = []
    jobs = [(q, f"?i wdt:P5817 wd:{q}.") for q in STATES] + [(q, f"?i wdt:P31 wd:{q}.") for q in TYPES]
    for q, clause in jobs:
        res = []
        for lo, hi in BANDS:
            res += band(clause, lo, hi)
            time.sleep(1)
        for b in res:
            b["state"] = {"value": q}
        print(f"  {STATES.get(q) or TYPES.get(q):22s} → {len(res)} lignes", flush=True)
        rows.extend(res)
        time.sleep(2)

    # Libellés anglais / français des types (P31), par paquets
    types = sorted({b["type"]["value"].rsplit("/", 1)[-1] for b in rows if "type" in b})
    labels: dict[str, tuple[str, str]] = {}
    for i in range(0, len(types), 300):
        chunk = " ".join("wd:" + t for t in types[i:i + 300])
        for b in sparql(LABELS_QUERY % chunk):
            t = b["t"]["value"].rsplit("/", 1)[-1]
            labels[t] = (b.get("en", {}).get("value", ""), b.get("fr", {}).get("value", ""))
    for b in rows:
        if "type" in b:
            en, fr = labels.get(b["type"]["value"].rsplit("/", 1)[-1], ("", ""))
            if en:
                b["typeEn"] = {"value": en}
            if fr:
                b["typeFr"] = {"value": fr}
    return rows


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    rows = fetch()
    print(f"{len(rows)} lignes Wikidata reçues")

    items: dict[str, dict] = {}
    for b in rows:
        qid = b["i"]["value"].rsplit("/", 1)[-1]
        coord = b["coord"]["value"]  # "Point(lon lat)"
        if not coord.startswith("Point("):
            continue
        lon, lat = map(float, coord[6:-1].split())
        it = items.setdefault(qid, {"lat": lat, "lon": lon, "name": b["iLabel"]["value"],
                                    "en": set(), "fr": set(), "img": "", "state": set()})
        if "typeEn" in b:
            it["en"].add(b["typeEn"]["value"])
        if "typeFr" in b:
            it["fr"].add(b["typeFr"]["value"])
        if "img" in b and not it["img"]:
            it["img"] = urllib.parse.unquote(b["img"]["value"].rsplit("/", 1)[-1])
        s = b["state"]["value"].rsplit("/", 1)[-1]
        it["state"].add(STATES.get(s) or TYPES.get(s, ""))

    spots = []
    for qid, it in items.items():
        en = " ".join(it["en"]).lower()
        if any(x in en for x in EXCLUDE_TYPES):
            continue
        name = it["name"] if it["name"] != qid else ""
        tags = {"name": name, "type": " ".join(sorted(it["en"])), "typefr": " ".join(sorted(it["fr"]))}
        if "ruines" in it["state"]:
            tags["historic"] = "ruins"
        label = ", ".join(sorted(it["fr"]))[:80] or ", ".join(sorted(it["state"]))
        spots.append([
            round(it["lat"], 5), round(it["lon"], 5), name,
            categorize(tags), label, qid, it["img"],
        ])

    payload = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "Wikidata (CC0)",
        "fields": ["lat", "lon", "name", "category", "type", "wikidata_id", "image"],
        "spots": spots,
    }
    if len(spots) < 50:
        sys.exit(f"Seulement {len(spots)} lieux : fichier précédent conservé")
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
