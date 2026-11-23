# 🏚️ Urbex Map

Carte interactive du **monde entier** recensant les **lieux abandonnés, désaffectés et en ruine** : usines, bunkers, sanatoriums, châteaux, gares, églises, maisons…

Les données viennent de bases libres et ouvertes, mises à jour automatiquement chaque semaine :

| Source | Contenu | Licence |
|---|---|---|
| [OpenStreetMap](https://www.openstreetmap.org) | 🌍 monde entier : objets tagués abandonné, désaffecté, en ruine, bunker | ODbL |
| [Wikidata](https://www.wikidata.org) | 🌍 monde entier : lieux désaffectés, abandonnés, hors service, ruines, villages fantômes | CC0 |
| 🇫🇷 [Mérimée](https://pop.culture.gouv.fr) (ministère de la Culture) | monuments historiques en vestiges, désaffectés, menacés, en mauvais état | Licence Ouverte |
| 🇫🇷 [Cartofriches](https://cartofriches.cerema.fr) (Cerema) | friches non reconverties et inoccupées | Licence Ouverte |
| 🇫🇷 [CASIAS](https://www.georisques.gouv.fr) (BRGM) | anciens sites industriels à l'arrêt (usines, fonderies, filatures…) — beaucoup ont été démolis | Licence Ouverte |
| [GeoNames](https://www.geonames.org) | 🌍 villages abandonnés ou détruits, ruines, fermes, aérodromes, gares, mines abandonnés | CC-BY 4.0 |
| 🇬🇧 [Heritage at Risk](https://historicengland.org.uk/advice/heritage-at-risk/) (Historic England) | bâtiments, structures et lieux de culte classés en danger | Open Government Licence |
| 🇬🇧 [Brownfield land](https://www.planning.data.gov.uk/dataset/brownfield-land) | friches anglaises : seulement les anciens bâtiments (usines, moulins, hôpitaux…) | Open Government Licence |
| 🇨🇦 [AMIS](https://data.ontario.ca/dataset/abandoned-mines-information) (Ontario) | mines abandonnées | Open Government Licence – Ontario |
| [GeoNames cities15000](https://www.geonames.org) | 🌍 villes de plus de 15 000 habitants, pour la recherche par ville (`scripts/build_cities.py`) | CC-BY 4.0 |
| **Communauté** | lieux proposés par les visiteurs et validés | — |

Chaque source peut être affichée ou masquée dans le panneau « Sources ».

## Communauté Discord

💬 **Rejoindre le serveur : <https://discord.gg/F5gXjfSCA6>** (explos, photos, entraide, idées pour l'appli).

Le salon **#mises-à-jour-carte** reçoit automatiquement un message à chaque mise à jour de la carte et à chaque lieu de la communauté validé (`scripts/discord_notify.py`, webhook enregistré dans le secret `DISCORD_WEBHOOK` du dépôt).

## Proposer un lieu

Bouton **« Proposer un lieu à la communauté »** sur la carte (ou dans la fiche d'un de tes spots perso) → formulaire GitHub.
**Seul le propriétaire du dépôt modère** :
- il relit la proposition puis pose le label **`validé`** → le lieu est ajouté à la carte, l'issue est fermée et un commentaire récapitule exactement ce qui a été publié ;
- s'il retire le label **`validé`** → le lieu est retiré de la carte.

Un label posé par quelqu'un d'autre que le propriétaire est ignoré. Les spots perso et l'import restent, eux, uniquement dans le navigateur de chaque visiteur.

🌐 **Voir la carte : <https://maylo083.github.io/urbex-map-france/>**

## Fonctionnalités

- 🗺️ Carte du monde entier avec regroupement des points (clusters)
- 🏭 Filtres par catégorie : industriel, militaire, hôpitaux, châteaux, religieux, transport, loisirs, habitations, ruines
- 🔍 Recherche par nom (sans accents ni majuscules, tous alphabets)
- 🛰️ Fonds de carte : plan, satellite, photo aérienne IGN actuelle **et des années 1950-1965**
- 🔗 Pour chaque lieu : liens Google Satellite, Street View, *Remonter le temps* (IGN, en France), itinéraire, fiche OSM
- 📍 **Mes spots** : clic droit sur la carte pour ajouter tes propres lieux avec notes (stockés dans ton navigateur), export / import en GeoJSON
- 📱 Fonctionne sur mobile, géolocalisation

## Utilisation en local

Le site est 100 % statique (HTML/CSS/JS), mais il doit être servi par un petit serveur web. Il faut d'abord préparer les tuiles (`python scripts/build_tiles.py`, voir plus bas) :

```bash
python -m http.server 8000
```

Puis ouvre <http://localhost:8000>.

## Comment la carte reste rapide

Le site ne télécharge pas tous les lieux d'un coup. `scripts/build_tiles.py` prépare les données dans `data/tiles/` :

- `meta.json` + `overview.json` : chargés à l'ouverture, ils affichent les bulles du monde (cases de 4°) ;
- `o/<carré>.json` : bulles par case de 1°, par carrés de 10°, chargées quand on zoome sur une région ;
- `c/<case>.json` : les lieux d'une case de 0,5° × 0,5°, chargés seulement quand on regarde cette zone ;
- `s/<début>.json` : l'index de recherche, découpé selon le début des mots (on ne télécharge que le morceau du mot tapé).

La fusion des doublons entre sources est faite à ce moment-là, une fois pour toutes.

## Où sont les données ?

Pour que le dépôt ne grossisse pas à chaque mise à jour, rien de tout ça n'est enregistré dans le code :

- les **sources brutes** (OpenStreetMap par région, Wikidata, Mérimée, Cartofriches, CASIAS) sont rangées dans la [Release « donnees »](https://github.com/MAYLO083/urbex-map-france/releases/tag/donnees) ;
- les **tuiles** sont construites par GitHub Actions et publiées directement sur GitHub Pages (`.github/workflows/build-site.yml`) ;
- seuls les **lieux de la communauté** (`data/spots_communaute.json`) sont dans le dépôt.

## Mise à jour automatique

`.github/workflows/update-data.yml`, chaque lundi (ou via **Actions → Mise à jour des spots → Run workflow**) :

1. **OpenStreetMap, monde entier** (le premier lundi du mois, ou à la demande) : `plan_regions.py` découpe la planète en ~275 extraits Geofabrik (~84 Go), répartis en lots ; une dizaine de machines GitHub les traitent en parallèle avec `fetch_osm_extract.py` (téléchargement, filtre `osmium`, extraction, suppression) ;
2. **Wikidata** (monde entier) et les sources françaises ;
3. les nouvelles versions remplacent les anciennes dans la Release — une région ou une source qui échoue garde sa version précédente ;
4. le site est reconstruit et republié.

En local :

```bash
gh release download donnees --dir data/.dl     # sources de la dernière mise à jour
tar -xzf data/.dl/osm.tar.gz -C data
for f in data/.dl/spots_*.json.gz; do gunzip -c "$f" > "data/$(basename "$f" .gz)"; done
python scripts/build_tiles.py                  # fusion des doublons + découpage en tuiles
python -m http.server 8000
```

**CASIAS depuis GitHub :** le pare-feu du BRGM refuse les machines de GitHub Actions (« Request Rejected »). La version rangée dans la Release est donc gardée telle quelle. C'est un inventaire historique qui bouge très peu. Pour la rafraîchir depuis ton ordinateur :

```bash
python scripts/fetch_opendata.py casias --fresh
gzip -c data/spots_casias.json > spots_casias.json.gz
gh release upload donnees spots_casias.json.gz --clobber
```

Ou pour refaire une source : `fetch_wikidata.py`, `fetch_opendata.py` (Mérimée + Cartofriches + CASIAS), `fetch_osm_extract.py` (sans argument : la France ; sinon une liste d'URL d'extraits Geofabrik).

## Quels lieux sont inclus ?

Tous les objets OSM du monde portant l'un de ces tags : `abandoned=yes`, `disused=yes`, `ruins=yes`, `historic=ruins|bunker|mine`, `building=ruins|abandoned|disused|bunker`, `military=bunker`, `landuse=brownfield` (friches), `abandoned:place` (villages abandonnés), les gares `abandoned:railway` / `disused:railway`, les centrales `abandoned:power` / `disused:power`, les aérodromes `abandoned:aeroway` / `disused:aeroway`, et `abandoned:` / `disused:` suivis de `building`, `amenity`, `man_made`, `industrial`, `military`, `tourism`, `leisure` ou `landuse`.
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
- Données : © contributeurs OpenStreetMap, sous licence [ODbL](https://opendatacommons.org/licenses/odbl/) ; Wikidata ([CC0](https://creativecommons.org/publicdomain/zero/1.0/)) ; Mérimée, Cartofriches, CASIAS ([Licence Ouverte 2.0](https://www.etalab.gouv.fr/licence-ouverte-open-licence/)) ; GeoNames ([CC-BY 4.0](https://creativecommons.org/licenses/by/4.0/)) ; Historic England et planning.data.gov.uk ([Open Government Licence](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/), contient des données Historic England et du gouvernement britannique) ; Ontario AMIS ([Open Government Licence – Ontario](https://www.ontario.ca/page/open-government-licence-ontario)) ; photos Wikimedia Commons (licence propre à chaque photo)
- Fonds de carte : OpenStreetMap, Esri, IGN (Géoplateforme)
- Bibliothèques : [Leaflet](https://leafletjs.com), [Leaflet.markercluster](https://github.com/Leaflet/Leaflet.markercluster)
