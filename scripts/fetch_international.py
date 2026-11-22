#!/usr/bin/env python3
"""
Bases nationales ouvertes hors de France (équivalents de Mérimée / Cartofriches) :

  heritage   Angleterre — Heritage at Risk Register (Historic England, Open Government Licence)
             bâtiments, structures et lieux de culte classés « en danger »
  friches_uk Angleterre — Brownfield land registers (planning.data.gov.uk, OGL)
             seulement les anciens bâtiments (« former… works, mill, hospital… »)
  mines_on   Canada / Ontario — Abandoned Mines Information System (Open Government Licence – Ontario)

Génère data/spots_<nom>.json pour chacun (le fichier précédent est gardé en cas d'échec).

Usage :
    python scripts/fetch_international.py              # tout
    python scripts/fetch_international.py heritage     # une seule base
"""

from __future__ import annotations

import csv
import html
import io
import json
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_opendata import fetch, write  # noqa: E402
from fetch_spots import categorize  # noqa: E402

FIELDS = ["lat", "lon", "name", "category", "description", "id"]
csv.field_size_limit(10**9)

# ---------------------------------------------------------------- Heritage at Risk
HE_HUB = ("https://opendata-historicengland.hub.arcgis.com/api/search/v1/collections/all/items"
          "?q=heritage%20at%20risk%20register&limit=50")
HE_KEEP = {"Building or structure": "bâtiment ou structure en danger", "Place of worship": "lieu de culte en danger"}


def heritage() -> None:
    # Le registre est republié chaque année : on prend la version la plus récente
    items = json.loads(fetch(HE_HUB))["features"]
    regs = []
    for f in items:
        p = f["properties"]
        m = re.search(r"Heritage at Risk Register (\d{4})", p.get("title") or "")
        if m and p.get("type") == "Feature Service" and p.get("url"):
            regs.append((int(m.group(1)), p["url"].rstrip("/")))
    year, url = max(regs)
    print(f"→ Heritage at Risk {year}", flush=True)
    spots, offset = [], 0
    while True:
        q = (f"{url}/0/query?where=1%3D1&outFields=EntryName,Risk_Metho,HeritageCa,URL,List_Entry"
             f"&returnGeometry=false&returnCentroid=true&outSR=4326&resultOffset={offset}"
             f"&resultRecordCount=1000&f=json")
        page = json.loads(fetch(q))
        feats = page.get("features", [])
        for f in feats:
            a, c = f["attributes"], f.get("centroid")
            label = HE_KEEP.get(a.get("Risk_Metho") or "")
            if not label or not c:
                continue
            name = (a.get("EntryName") or "").strip()
            m = re.search(r"list-entry/(\d+)", a.get("URL") or "")
            if not name or not m:
                continue
            cat = "religieux" if a["Risk_Metho"] == "Place of worship" else categorize({"name": name.lower()})
            if cat == "autre":
                cat = "ruines" if re.search(r"\bruins?\b|remains", name, re.I) else "autre"
            spots.append([round(c["y"], 5), round(c["x"], 5), name[:120], cat, label, "H" + m.group(1)])
        offset += len(feats)
        if not feats or not page.get("exceededTransferLimit"):
            break
    write("heritage", f"Historic England, Heritage at Risk Register {year} (Open Government Licence)", FIELDS, spots)


# ---------------------------------------------------------------- Friches anglaises
BROWNFIELD = "https://files.planning.data.gov.uk/dataset/brownfield-land.csv"
BF_KEEP = re.compile(r"\b(former|disused|vacant|derelict|redundant|mill|works|factory|foundry|brewery|gasworks|"
                     r"hospital|barracks|cinema|airfield|colliery|asylum|maltings|tannery|dyeworks)\b", re.I)
BF_SKIP = re.compile(r"complet|under construction|commenced|started|built out|occupied|in use|demolish|cleared|"
                     r"car park|\badj|adjacent|garage block|garages|land (at|to|adj|north|south|east|west|rear|off)|"
                     r"garden|field|allotment|playing|mill (road|lane|street|hill)", re.I)


def friches_uk() -> None:
    data = fetch(BROWNFIELD).decode("utf-8")
    spots = []
    for row in csv.DictReader(io.StringIO(data)):
        addr = (row.get("site-address") or "").strip()
        if row.get("end-date") or not addr or not BF_KEEP.search(addr) or BF_SKIP.search(addr + " " + (row.get("notes") or "")):
            continue
        m = re.match(r"POINT\(([-\d.]+) ([-\d.]+)\)", row.get("point") or "")
        if not m:
            continue
        lon, lat = float(m.group(1)), float(m.group(2))
        cat = categorize({"name": addr.lower()})
        if cat == "autre":
            cat = "industriel"
        desc = "friche (brownfield land register)"
        if row.get("hectares"):
            desc += f" · {row['hectares']} ha"
        spots.append([round(lat, 5), round(lon, 5), addr[:120], cat, desc, "B" + row["entity"]])
    write("friches_uk", "Brownfield land registers, planning.data.gov.uk (Open Government Licence)", FIELDS, spots)


# ---------------------------------------------------------------- Mines de l'Ontario
AMIS = "http://www.geologyontario.mndm.gov.on.ca/mines/data/google/AMIS/KML/Sites/Sites{year}.kmz"
AMIS_INDEX = "https://www.geologyontario.mndm.gov.on.ca/mines/data/google/amis/AMIS.kml"


def field(block: str, label: str) -> str:
    m = re.search(rf"<em>\s*{label}\s*:\s*</em></b>([^<]*)", block)
    return html.unescape(m.group(1)).strip() if m else ""


def mines_on() -> None:
    index = fetch(AMIS_INDEX).decode("utf-8", "replace")
    m = re.search(r"<href>([^<]*Sites/Sites\d{4}\.kmz)</href>", index)
    url = m.group(1) if m else AMIS.format(year=2026)
    print(f"→ {url}", flush=True)
    with zipfile.ZipFile(io.BytesIO(fetch(url))) as z:
        kml = z.read(next(n for n in z.namelist() if n.endswith(".kml"))).decode("utf-8", "replace")
    spots = []
    for block in kml.split("<Placemark")[1:]:
        if field(block, "Status") != "ABANDONED":
            continue
        ident = re.search(r"abandoned-mine=(\d+)", block)
        lon = re.search(r"Longitude \(dd\) : </em></b>([-\d.]+)", block)
        lat = re.search(r"Latitude \(dd\) : </em></b>([-\d.]+)", block)
        if not (ident and lon and lat):
            continue
        name = field(block, "Official Name").title() or "Mine abandonnée"
        commodity = field(block, "Primary Commodity").lower()
        desc = "mine abandonnée" + (f" · {commodity}" if commodity else "")
        spots.append([round(float(lat.group(1)), 5), round(float(lon.group(1)), 5), name[:120], "industriel",
                      desc, "A" + ident.group(1)])
    write("mines_on", "Ontario Abandoned Mines Information System (Open Government Licence – Ontario)", FIELDS, spots)


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    jobs = {"heritage": heritage, "friches_uk": friches_uk, "mines_on": mines_on}
    wanted = [a for a in sys.argv[1:] if not a.startswith("--")] or list(jobs)
    failed = []
    for name in wanted:
        try:
            jobs[name]()
        except Exception as e:  # noqa: BLE001
            print(f"!! {name} a échoué : {e}", flush=True)
            failed.append(name)
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
