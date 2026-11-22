# 🏚️ Urbex Map France

Carte interactive de la France recensant les **lieux abandonnés, désaffectés et en ruine** : usines, bunkers, sanatoriums, châteaux, gares, églises, maisons…

Les données viennent de bases libres et ouvertes, mises à jour automatiquement chaque semaine :

| Source | Contenu | Licence |
|---|---|---|
| [OpenStreetMap](https://www.openstreetmap.org) | objets tagués abandonné, désaffecté, en ruine, bunker | ODbL |
| [Wikidata](https://www.wikidata.org) | lieux désaffectés, abandonnés, hors service, ruines, villages fantômes | CC0 |
| [Mérimée](https://pop.culture.gouv.fr) (ministère de la Culture) | monuments historiques en vestiges, désaffectés, menacés, en mauvais état | Licence Ouverte |
| [Cartofriches](https://cartofriches.cerema.fr) (Cerema) | friches non reconverties et inoccupées | Licence Ouverte |
| [CASIAS](https://www.georisques.gouv.fr) (BRGM) | anciens sites industriels à l'arrêt (usines, fonderies, filatures…) — beaucoup ont été démolis | Licence Ouverte |
| **Communauté** | lieux proposés par les visiteurs et validés | — |

Chaque source peut être affichée ou masquée dans le panneau « Sources ».

## Proposer un lieu

Bouton **« Proposer un lieu à la communauté »** sur la carte (ou dans la fiche d'un de tes spots perso) → formulaire GitHub.
**Seul le propriétaire du dépôt modère** :
- il relit la proposition puis pose le label **`validé`** → le lieu est ajouté à la carte, l'issue est fermée et un commentaire récapitule exactement ce qui a été publié ;
- s'il retire le label **`validé`** → le lieu est retiré de la carte.

Un label posé par quelqu'un d'autre que le propriétaire est ignoré. Les spots perso et l'import restent, eux, uniquement dans le navigateur de chaque visiteur.

🌐 **Voir la carte : <https://maylo083.github.io/urbex-map-france/>**

## Fonctionnalités

- 🗺️ Carte de toute la France avec regroupement des points (clusters)
- 🏭 Filtres par catégorie : industriel, militaire, hôpitaux, châteaux, religieux, transport, loisirs, habitations, ruines
- 🔍 Recherche par nom (sans accents ni majuscules)
- 🛰️ Fonds de carte : plan, satellite, photo aérienne IGN actuelle **et des années 1950-1965**
- 🔗 Pour chaque lieu : liens Google Satellite, Street View, *Remonter le temps* (IGN), itinéraire, fiche OSM
- 📍 **Mes spots** : clic droit sur la carte pour ajouter tes propres lieux avec notes (stockés dans ton navigateur), export / import en GeoJSON
- 📱 Fonctionne sur mobile, géolocalisation

## Utilisation en local

Le site est 100 % statique (HTML/CSS/JS), mais il doit être servi par un petit serveur web pour pouvoir charger `data/spots.json` :

```bash
python -m http.server 8000
```

Puis ouvre <http://localhost:8000>.

## Comment la carte reste rapide

Le site ne télécharge pas tous les lieux d'un coup. `scripts/build_tiles.py` prépare les données dans `data/tiles/` :

- `meta.json` + `overview.json` (~10 Ko) : chargés à l'ouverture, ils affichent les bulles par région ;
- `c/<case>.json` : les lieux d'une case de 0,5° × 0,5°, chargés seulement quand on regarde cette zone ;
- `search.json` : l'index des noms, chargé seulement quand on utilise la recherche.

La fusion des doublons entre sources est faite à ce moment-là, une fois pour toutes. Ce découpage permet d'ajouter d'autres pays sans ralentir l'ouverture.

## Mettre à jour les données

```bash
python scripts/fetch_wikidata.py   # rapide (~1 min)
python scripts/fetch_opendata.py   # Mérimée + Cartofriches + CASIAS (~200 Mo à télécharger)
pip install osmium                 # puis, sous Linux : apt install osmium-tool
python scripts/fetch_osm_extract.py   # OpenStreetMap : télécharge l'extrait officiel France (~5 Go, Geofabrik) et le filtre
python scripts/build_tiles.py      # à lancer après : fusion des doublons + découpage en tuiles
```

`fetch_wikidata.py` récupère les lieux marqués *désaffecté*, *abandonné*, *hors service*, *en ruine*, *fermé définitivement*, les ruines et villages fantômes (données CC0, avec photo quand elle existe).

`fetch_osm_extract.py` lit l'extrait officiel OpenStreetMap de la France (aucun serveur partagé, donc fiable) et réécrit `data/spots.json`. L'ancien `fetch_spots.py` (API Overpass) reste disponible mais ces serveurs sont souvent saturés.
Sur GitHub, le workflow `.github/workflows/update-data.yml` le fait tout seul chaque lundi (ou à la demande via l'onglet **Actions → Run workflow**).

## Publier sur GitHub Pages

1. Crée un dépôt sur GitHub et pousse ce dossier.
2. Dans **Settings → Pages**, choisis *Deploy from a branch*, branche `main`, dossier `/ (root)`.
3. Dans **Settings → Actions → General**, autorise *Read and write permissions* pour que la mise à jour automatique puisse committer.
4. Ton site est en ligne sur `https://<ton-pseudo>.github.io/<nom-du-depot>/`.

## Quels lieux sont inclus ?

Tous les objets OSM en France portant l'un de ces tags : `abandoned=yes`, `disused=yes`, `ruins=yes`, `historic=ruins`, `building=ruins|abandoned|disused`, `abandoned:*`, `disused:*`, `military=bunker`, `building=bunker`.
Les objets linéaires (routes, voies ferrées, lignes électriques…) sont exclus. La catégorie est déduite automatiquement des tags et du nom ; elle peut donc parfois être approximative.

**Un lieu manque ou est faux ?** Corrige-le directement sur OpenStreetMap (lien dans chaque fiche) : il apparaîtra ici à la prochaine mise à jour.

## ⚠️ Avertissement

- La plupart de ces lieux sont des **propriétés privées**. Y pénétrer sans autorisation peut constituer une infraction.
- Les lieux abandonnés sont **dangereux** (effondrements, amiante, puits…). Ne pars jamais seul.
- Respecte les lieux : ne casse rien, ne vole rien, ne tague rien.
- Les données peuvent être inexactes ou périmées (lieu démoli, rénové, gardienné).

Ce projet est un outil cartographique ; tu restes seul responsable de l'usage que tu en fais.

## Licences

- Code : [MIT](LICENSE)
- Données : © contributeurs OpenStreetMap, sous licence [ODbL](https://opendatacommons.org/licenses/odbl/) ; Wikidata ([CC0](https://creativecommons.org/publicdomain/zero/1.0/)) ; Mérimée, Cartofriches, CASIAS ([Licence Ouverte 2.0](https://www.etalab.gouv.fr/licence-ouverte-open-licence/)) ; photos Wikimedia Commons (licence propre à chaque photo)
- Fonds de carte : OpenStreetMap, Esri, IGN (Géoplateforme)
- Bibliothèques : [Leaflet](https://leafletjs.com), [Leaflet.markercluster](https://github.com/Leaflet/Leaflet.markercluster)
