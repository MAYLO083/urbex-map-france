#!/usr/bin/env python3
"""
Importe les bases ouvertes de l'État (Licence Ouverte Etalab) :

  - Mérimée (ministère de la Culture) : monuments historiques en vestiges,
    désaffectés, en mauvais état ou menacés          → data/spots_merimee.json
  - Cartofriches (Cerema) : friches non reconverties
    et non occupées                                   → data/spots_friches.json
  - CASIAS (BRGM) : anciens sites industriels à l'arrêt
    dont l'activité évoque un vrai bâtiment            → data/spots_casias.json

Usage :
    python scripts/fetch_opendata.py            # les trois
    python scripts/fetch_opendata.py merimee    # une seule source
"""

from __future__ import annotations

import csv
import io
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_spots import categorize  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CACHE = DATA / ".cache"
UA = "urbex-map-france/1.0 (open-source map project)"
csv.field_size_limit(10**9)

URLS = {
    "merimee": "https://ministere-culture.s3.sbg.io.cloud.ovh.net/POP/merimee.csv",
    "friches": "https://www.data.gouv.fr/api/1/datasets/61892a26c94e39bde1dbf7ac/",  # on y lit l'URL du CSV à jour
    "casias": ("https://mapsref.brgm.fr/wxs/georisques/georisques_dl?service=wfs&version=2.0.0"
               "&request=getfeature&typename=etablissement_point&outputformat=csvtext"),
}

FRANCE = (41.3, 51.2, -5.3, 9.7)  # métropole + Corse


def in_france(lat: float, lon: float) -> bool:
    return FRANCE[0] <= lat <= FRANCE[1] and FRANCE[2] <= lon <= FRANCE[3]


def download(url: str, name: str) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / name
    print(f"→ téléchargement {name}…", flush=True)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=900) as r, open(path, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    print(f"  {path.stat().st_size / 1e6:.1f} Mo", flush=True)
    return path


def write(name: str, source: str, fields: list, spots: list) -> None:
    out = DATA / f"spots_{name}.json"
    if len(spots) < 50:  # téléchargement vide ou tronqué : on garde la version précédente
        raise RuntimeError(f"seulement {len(spots)} lieux pour {name}, fichier précédent conservé")
    payload = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": source,
        "fields": fields,
        "spots": spots,
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    counts: dict[str, int] = {}
    for s in spots:
        counts[s[3]] = counts.get(s[3], 0) + 1
    print(f"{len(spots)} spots écrits dans {out.relative_to(ROOT)}")
    for c, n in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {c:12s} {n}")


FIELDS = ["lat", "lon", "name", "category", "description", "id"]


# ---------------------------------------------------------------- Mérimée
MERIMEE_STATES = ("vestige", "désaffecté", "desaffecté", "mauvais état", "menacé", "préocupant",
                  "préoccupant", "détruit partiellement", "ruine")
MERIMEE_SKIP = ("site archéologique", "menhir", "dolmen", "allée couverte", "tumulus", "croix", "calvaire",
                "oppidum", "borne", "stèle", "statue", "voie", "route", "fontaine", "lavoir", "puits",
                "polissoir", "pierre", "nécropole", "sépulture", "tombe", "monument aux morts", "mégalith",
                "rocher", "grotte ornée", "camp", "villa gallo", "théâtre antique", "thermes", "hypocauste")


def merimee() -> None:
    path = CACHE / "merimee.csv"
    if not path.exists() or "--fresh" in sys.argv:
        path = download(URLS["merimee"], "merimee.csv")
    spots = []
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f, delimiter="|"):
            state = row.get("etat_de_conservation", "").lower()
            title = row.get("Titre_editorial_de_la_notice", "")
            denom = row.get("Denomination_de_l_edifice", "").replace(";", ", ")
            low = (title + " " + denom).lower()
            if "détruit" in state and "partiellement" not in state:
                continue
            if not (any(s in state for s in MERIMEE_STATES) or "ruine" in title.lower()):
                continue
            if any(s in low for s in MERIMEE_SKIP):
                continue
            coord = row.get("coordonnees_au_format_WGS84", "")
            try:
                lat, lon = map(float, coord.split(","))
            except ValueError:
                continue
            if not in_france(lat, lon):
                continue
            commune = row.get("Commune_forme_index", "")
            name = f"{title} ({commune})" if commune and commune.lower() not in title.lower() else title
            cat = categorize({"name": low, "typefr": denom})
            if cat == "autre" and ("ruine" in low or "vestige" in state):
                cat = "ruines"
            desc = " · ".join(x for x in (denom, row.get("etat_de_conservation", "").replace(";", ", ")) if x)
            spots.append([round(lat, 5), round(lon, 5), name, cat, desc[:120], "M" + row["Reference"]])
    write("merimee", "Base Mérimée, ministère de la Culture (Licence Ouverte)", FIELDS, spots)


# ---------------------------------------------------------------- Cartofriches
FRICHE_CAT = {
    "friche industrielle": "industriel", "friche agro-industrielle": "industriel",
    "friche logistique": "industriel", "friche carrière ou mine": "industriel",
    "friche ferroviaire": "transport", "friche portuaire": "transport", "friche aéroportuaire": "transport",
    "friche d'habitat": "habitation", "friche commerciale": "loisirs",
    "friche loisir tourisme hôtellerie": "loisirs", "friche hospitalière": "hopital",
    "friche militaire": "militaire", "friche cultuelle": "religieux",
}


def friches() -> None:
    meta = json.load(urllib.request.urlopen(urllib.request.Request(URLS["friches"], headers={"User-Agent": UA})))
    url = next(r["url"] for r in meta["resources"] if r["url"].endswith("friches-standard.csv"))
    path = download(url, "friches.csv")
    spots = []
    na = lambda v: "" if v in ("NA", "inconnu", "-", "autre") else v  # noqa: E731
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f, delimiter=";"):
            row = {k: (v or "") for k, v in row.items() if k}
            if row["site_statut"] == "friche reconvertie":
                continue
            if row["site_occupation"] in ("occupé", "partiellement occupé") or row["bati_vacance"] == "occupé":
                continue
            if row["bati_type"] == "sans objet" or row["bati_etat"] == "sans objet":
                continue  # pas de bâtiment
            if row["site_statut"] == "friche potentielle" and row["site_type"] in ("inconnu", "NA", ""):
                continue  # friche non vérifiée et sans type : surtout d'anciennes stations-service, dépôts…
            if CASIAS_SKIP.search(row["site_nom"] + " " + row["activite_libelle"]):
                continue
            m = re.match(r"POINT \(([-\d.]+) ([-\d.]+)\)", row["geompoint"])
            if not m:
                continue
            lon, lat = float(m.group(1)), float(m.group(2))
            if not in_france(lat, lon):
                continue
            stype = na(row["site_type"])
            nom = na(row["site_nom"])
            if "friche:" in nom:
                nom = nom.split("friche:", 1)[1].strip()
            if nom == row["site_id"] or re.fullmatch(r"[\d_ ]+", nom or "") or re.match(r"(Appel à projet|Région \w+-\d)", nom):
                nom = ""
            label = nom or (stype.capitalize() if stype else "Friche")
            name = f"{label} ({row['comm_nom'].title()})" if row["comm_nom"] not in ("", "NA") else label
            cat = FRICHE_CAT.get(stype) or categorize({"name": (nom + " " + na(row["activite_libelle"])).lower()})
            desc = " · ".join(x for x in (
                stype, na(row["bati_etat"]), na(row["site_occupation"]), na(row["site_statut"]),
                ("activité jusqu'en " + row["activite_fin_annee"]) if na(row["activite_fin_annee"]) else "",
            ) if x)
            spots.append([round(lat, 5), round(lon, 5), name, cat, desc[:140], "F" + row["site_id"]])
    write("friches", "Cartofriches, Cerema (Licence Ouverte)", FIELDS, spots)


# ---------------------------------------------------------------- CASIAS
# On ne garde que les activités qui laissent en général un vrai bâtiment à explorer.
CASIAS_KEEP = re.compile(
    r"usine|fabrication|filature|tissage|tannerie|fonderie|forge|verrerie|papeterie|sucrerie|distillerie|"
    r"brasserie|minoterie|moulin|scierie|tuilerie|briqueterie|faïencerie|céramique|porcelaine|sidérurg|"
    r"métallurg|aciérie|haut[- ]fourneau|cokerie|usine à gaz|gazomètre|centrale|abattoir|laiterie|"
    r"conserverie|imprimerie|atelier|chantier naval|teinturerie|blanchisserie industrielle|mine|carrière|"
    r"chaux|cimenterie|plâtrière|raffinerie|textile|chaussure|ganterie|bonneterie|manufacture",
    re.I)
CASIAS_SKIP = re.compile(
    r"station[- ]service|carburant|garage|dépôt de liquides|stockage de produits|décharge|dépôt d'ordures|"
    r"pressing|nettoyage à sec|ferraille|casse|transformateur|cuve|citerne|dépôt de",
    re.I)


def casias() -> None:
    path = CACHE / "casias.csv"
    if not path.exists() or "--fresh" in sys.argv:
        path = download(URLS["casias"], "casias.csv")
    spots = []
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f, delimiter=";"):
            row = {k: (v or "") for k, v in row.items() if k}
            if row.get("nom_inventaire") != "BASIAS":  # les autres inventaires portent des noms de particuliers
                continue
            if row["etat_activite"] != "En arrêt":
                continue
            text = f"{row['nom_etablissement']} {row['activite_principale']}"
            if not CASIAS_KEEP.search(text) or CASIAS_SKIP.search(text):
                continue
            try:
                lat, lon = float(row["y_wgs84"]), float(row["x_wgs84"])
            except ValueError:
                continue
            if not in_france(lat, lon):
                continue
            nom = row["nom_etablissement"].strip() or row["activite_principale"].strip() or "Ancien site industriel"
            commune = row["nom_commune"].title()
            name = f"{nom} ({commune})" if commune else nom
            desc = " · ".join(x for x in (
                row["activite_principale"].strip(), "activité arrêtée",
                ("fin " + row["date_fin"][:4]) if row["date_fin"] else "",
            ) if x)
            cat = categorize({"name": text.lower()})
            if cat == "autre":
                cat = "industriel"
            spots.append([round(lat, 5), round(lon, 5), name[:100], cat, desc[:140], "C" + row["code_metier"]])
    write("casias", "CASIAS, BRGM / Géorisques (Licence Ouverte)", FIELDS, spots)


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    jobs = {"merimee": merimee, "friches": friches, "casias": casias}
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
