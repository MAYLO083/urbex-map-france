/* Urbex Map France — carte des lieux abandonnés d'après OpenStreetMap */
(() => {
  "use strict";

  const CATEGORIES = {
    industriel: { label: "Industriel", color: "#e0a030" },
    militaire:  { label: "Militaire / bunkers", color: "#7d9b4a" },
    hopital:    { label: "Hôpitaux / sanatoriums", color: "#e05a5a" },
    chateau:    { label: "Châteaux / manoirs", color: "#b07ad8" },
    religieux:  { label: "Religieux", color: "#5aa7e0" },
    transport:  { label: "Transport / gares / tunnels", color: "#3fc1b0" },
    loisirs:    { label: "Hôtels / écoles / loisirs", color: "#e07ab8" },
    habitation: { label: "Maisons / fermes", color: "#c9a27a" },
    ruines:     { label: "Ruines", color: "#8c8c8c" },
    autre:      { label: "Autre", color: "#cfcfcf" },
  };
  const MINE_COLOR = "#ff3d00";
  const STORE_KEY = "urbex.mine.v1";
  const FILTER_KEY = "urbex.filters.v1";
  const SEEN_KEY = "urbex.disclaimer.v1";

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  // ---------- Carte ----------
  const map = L.map("map", { preferCanvas: true, zoomControl: true, minZoom: 4 });
  const renderer = L.canvas({ padding: 0.5 });

  const geopf = (layer, fmt = "image/jpeg") =>
    `https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=${layer}&STYLE=normal&TILEMATRIXSET=PM&FORMAT=${fmt}&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}`;

  const baseLayers = {
    "Plan (OpenStreetMap)": L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }),
    "Satellite (Esri)": L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
      maxZoom: 19, attribution: "Imagerie &copy; Esri, Maxar, Earthstar Geographics",
    }),
    "Photo aérienne IGN": L.tileLayer(geopf("ORTHOIMAGERY.ORTHOPHOTOS"), {
      maxZoom: 19, attribution: '&copy; <a href="https://geoservices.ign.fr/">IGN</a>',
    }),
    "Photo aérienne 1950-1965 (IGN)": L.tileLayer(geopf("ORTHOIMAGERY.ORTHOPHOTOS.1950-1965", "image/png"), {
      maxZoom: 18, attribution: '&copy; <a href="https://geoservices.ign.fr/">IGN</a>',
    }),
  };
  baseLayers["Plan (OpenStreetMap)"].addTo(map);
  L.control.layers(baseLayers, null, { position: "topright" }).addTo(map);
  L.control.scale({ imperial: false }).addTo(map);

  // Position depuis l'URL (#zoom/lat/lon) ou France entière
  const fromHash = () => {
    const m = location.hash.match(/^#(\d+(?:\.\d+)?)\/(-?\d+\.\d+)\/(-?\d+\.\d+)/);
    if (m) { map.setView([+m[2], +m[3]], +m[1]); return true; }
    return false;
  };
  if (!fromHash()) map.fitBounds([[41.3, -5.2], [51.1, 9.6]]);
  map.on("moveend", () => {
    const c = map.getCenter();
    history.replaceState(null, "", `#${map.getZoom()}/${c.lat.toFixed(5)}/${c.lng.toFixed(5)}`);
  });

  // Géolocalisation
  const LocateControl = L.Control.extend({
    options: { position: "topleft" },
    onAdd() {
      const b = L.DomUtil.create("a", "leaflet-bar leaflet-control");
      Object.assign(b.style, { width: "34px", height: "34px", lineHeight: "30px", textAlign: "center", background: "#fff", cursor: "pointer", fontSize: "18px" });
      b.title = "Me localiser";
      b.textContent = "◎";
      L.DomEvent.on(b, "click", (e) => { L.DomEvent.stop(e); map.locate({ setView: true, maxZoom: 13 }); });
      return b;
    },
  });
  new LocateControl().addTo(map);
  let meMarker;
  map.on("locationfound", (e) => {
    if (meMarker) meMarker.remove();
    meMarker = L.circleMarker(e.latlng, { radius: 8, color: "#fff", weight: 3, fillColor: "#2b7cff", fillOpacity: 1 }).addTo(map);
  });

  // ---------- Marqueurs OSM ----------
  const cluster = L.markerClusterGroup({
    chunkedLoading: true,
    maxClusterRadius: (z) => (z < 9 ? 60 : z < 13 ? 45 : 30),
    disableClusteringAtZoom: 16,
    spiderfyOnMaxZoom: true,
    showCoverageOnHover: false,
  });
  map.addLayer(cluster);

  let spots = [];          // [lat, lon, name, cat, osmType, osmId]
  let markers = [];        // marqueur par spot (créé une fois)
  const savedFilters = JSON.parse(localStorage.getItem(FILTER_KEY) || "null");
  const active = new Set(savedFilters || Object.keys(CATEGORIES));
  let namedOnly = false;

  const osmUrl = (id) => {
    const t = { n: "node", w: "way", r: "relation" }[id[0]];
    return `https://www.openstreetmap.org/${t}/${id.slice(1)}`;
  };

  const linksHtml = (lat, lon) => `
    <div class="links">
      <a target="_blank" rel="noopener" href="https://www.google.com/maps/@?api=1&map_action=map&center=${lat},${lon}&zoom=18&basemap=satellite">Google Satellite</a>
      <a target="_blank" rel="noopener" href="https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${lat},${lon}">Street View</a>
      <a target="_blank" rel="noopener" href="https://remonterletemps.ign.fr/comparer?lon=${lon}&lat=${lat}&z=17">Remonter le temps</a>
      <a target="_blank" rel="noopener" href="https://www.google.com/maps/dir/?api=1&destination=${lat},${lon}">Itinéraire</a>
    </div>`;

  const spotPopup = (s) => {
    const cat = CATEGORIES[s[3]] || CATEGORIES.autre;
    const isWd = s[5][0] === "Q";
    const source = isWd
      ? `<a target="_blank" rel="noopener" href="https://www.wikidata.org/wiki/${s[5]}">Fiche Wikidata</a>`
      : `<a target="_blank" rel="noopener" href="${osmUrl(s[5])}">Voir / corriger sur OpenStreetMap</a>`;
    const img = s[6]
      ? `<a target="_blank" rel="noopener" href="https://commons.wikimedia.org/wiki/File:${encodeURIComponent(s[6])}">
           <img src="https://commons.wikimedia.org/wiki/Special:FilePath/${encodeURIComponent(s[6])}?width=320" alt="" loading="lazy" class="thumb"></a>`
      : "";
    return `<div class="popup">
      ${img}
      <h3>${esc(s[2] || "Lieu sans nom")}</h3>
      <span class="tag" style="background:${cat.color}">${cat.label}</span>
      <span class="src">${isWd ? "Wikidata" : "OpenStreetMap"}</span>
      ${s[4] ? `<div class="osm">${esc(s[4])}</div>` : ""}
      <div class="osm">${s[0].toFixed(5)}, ${s[1].toFixed(5)}</div>
      ${linksHtml(s[0], s[1])}
      <div class="links">${source}</div>
    </div>`;
  };

  const makeMarker = (s) => {
    const cat = CATEGORIES[s[3]] || CATEGORIES.autre;
    const m = L.circleMarker([s[0], s[1]], {
      renderer, radius: 6, weight: 2, color: "#fff", fillColor: cat.color, fillOpacity: 0.95,
    });
    m.bindPopup(() => spotPopup(s));
    return m;
  };

  const visible = (s) => active.has(s[3]) && (!namedOnly || s[2]);

  const refresh = () => {
    cluster.clearLayers();
    const list = [];
    for (let i = 0; i < spots.length; i++) if (visible(spots[i])) list.push(markers[i]);
    cluster.addLayers(list);
    document.getElementById("stats").textContent =
      `${list.length.toLocaleString("fr-FR")} lieux affichés sur ${spots.length.toLocaleString("fr-FR")}` +
      (window.__generated ? ` · données du ${new Date(window.__generated).toLocaleDateString("fr-FR")}` : "");
    localStorage.setItem(FILTER_KEY, JSON.stringify([...active]));
  };

  // ---------- Filtres ----------
  const buildFilters = () => {
    const counts = {};
    for (const s of spots) counts[s[3]] = (counts[s[3]] || 0) + 1;
    const box = document.getElementById("filters");
    box.innerHTML = "";
    for (const [key, c] of Object.entries(CATEGORIES)) {
      const lab = document.createElement("label");
      lab.className = "check";
      lab.innerHTML = `<input type="checkbox" ${active.has(key) ? "checked" : ""}>
        <span class="dot" style="background:${c.color}"></span>${c.label}
        <span class="count">${(counts[key] || 0).toLocaleString("fr-FR")}</span>`;
      lab.querySelector("input").addEventListener("change", (e) => {
        e.target.checked ? active.add(key) : active.delete(key);
        refresh();
      });
      box.appendChild(lab);
    }
    const all = document.createElement("div");
    all.className = "row";
    all.style.marginTop = "6px";
    all.innerHTML = `<button data-a="all">Tout</button><button data-a="none">Rien</button>`;
    all.addEventListener("click", (e) => {
      const a = e.target.dataset.a;
      if (!a) return;
      active.clear();
      if (a === "all") Object.keys(CATEGORIES).forEach((k) => active.add(k));
      box.querySelectorAll("input").forEach((i) => (i.checked = a === "all"));
      refresh();
    });
    box.appendChild(all);
  };
  document.getElementById("named-only").addEventListener("change", (e) => { namedOnly = e.target.checked; refresh(); });

  // ---------- Recherche ----------
  const norm = (s) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  let normNames = [];
  const results = document.getElementById("results");
  let searchTimer;
  document.getElementById("search").addEventListener("input", (e) => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      const q = norm(e.target.value.trim());
      results.innerHTML = "";
      if (q.length < 2) return;
      const words = q.split(/\s+/);
      const found = [];
      for (let i = 0; i < spots.length && found.length < 60; i++) {
        if (normNames[i] && words.every((w) => normNames[i].includes(w))) found.push(i);
      }
      for (const m of mine) {
        if (words.every((w) => norm(m.name || "").includes(w))) found.push(m);
      }
      if (!found.length) { results.innerHTML = `<li class="hint">Aucun résultat</li>`; return; }
      for (const f of found) {
        const li = document.createElement("li");
        if (typeof f === "number") {
          const s = spots[f];
          const c = CATEGORIES[s[3]] || CATEGORIES.autre;
          li.innerHTML = `<span class="dot" style="background:${c.color}"></span>${esc(s[2])}<small>${c.label.split(" ")[0]}</small>`;
          li.onclick = () => focusSpot(f);
        } else {
          li.innerHTML = `<span class="dot" style="background:${MINE_COLOR}"></span>${esc(f.name)}<small>Mon spot</small>`;
          li.onclick = () => { map.setView([f.lat, f.lon], 17); f._marker.openPopup(); };
        }
        results.appendChild(li);
      }
    }, 150);
  });

  const focusSpot = (i) => {
    const s = spots[i];
    if (!visible(s)) { active.add(s[3]); namedOnly = false; document.getElementById("named-only").checked = false; buildFilters(); refresh(); }
    cluster.zoomToShowLayer(markers[i], () => markers[i].openPopup());
  };

  // ---------- Mes spots (localStorage) ----------
  const mineLayer = L.layerGroup().addTo(map);
  let mine = JSON.parse(localStorage.getItem(STORE_KEY) || "[]");
  const saveMine = () => localStorage.setItem(STORE_KEY, JSON.stringify(mine.map(({ _marker, ...m }) => m)));

  const mineIcon = L.divIcon({ className: "", html: `<div class="pin mine" style="background:${MINE_COLOR}"></div>`, iconSize: [18, 18], iconAnchor: [9, 9] });

  const minePopup = (m) => {
    const div = document.createElement("div");
    div.className = "popup";
    div.innerHTML = `
      <input class="n" value="${esc(m.name)}" placeholder="Nom du spot">
      <textarea class="t" placeholder="Notes (accès, état, date de visite…)">${esc(m.note)}</textarea>
      <div class="osm">${m.lat.toFixed(5)}, ${m.lon.toFixed(5)}</div>
      ${linksHtml(m.lat, m.lon)}
      <div class="row"><button class="s">Enregistrer</button><button class="d">Supprimer</button></div>`;
    div.querySelector(".s").onclick = () => {
      m.name = div.querySelector(".n").value.trim() || "Mon spot";
      m.note = div.querySelector(".t").value;
      saveMine();
      m._marker.closePopup();
    };
    div.querySelector(".d").onclick = () => {
      if (!confirm(`Supprimer « ${m.name} » ?`)) return;
      mine = mine.filter((x) => x !== m);
      m._marker.remove();
      saveMine();
    };
    return div;
  };

  const addMineMarker = (m) => {
    m._marker = L.marker([m.lat, m.lon], { icon: mineIcon, draggable: true, zIndexOffset: 1000 })
      .bindPopup(() => minePopup(m))
      .on("dragend", (e) => { const p = e.target.getLatLng(); m.lat = p.lat; m.lon = p.lng; saveMine(); })
      .addTo(mineLayer);
  };
  mine.forEach(addMineMarker);

  map.on("contextmenu", (e) => {
    const m = { id: Date.now().toString(36), lat: e.latlng.lat, lon: e.latlng.lng, name: "Mon spot", note: "", created: new Date().toISOString() };
    mine.push(m);
    saveMine();
    addMineMarker(m);
    m._marker.openPopup();
  });

  document.getElementById("export").onclick = () => {
    const gj = {
      type: "FeatureCollection",
      features: mine.map((m) => ({
        type: "Feature",
        geometry: { type: "Point", coordinates: [m.lon, m.lat] },
        properties: { name: m.name, note: m.note, created: m.created },
      })),
    };
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([JSON.stringify(gj, null, 2)], { type: "application/geo+json" }));
    a.download = `mes-spots-urbex-${new Date().toISOString().slice(0, 10)}.geojson`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  document.getElementById("import").onchange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    try {
      const gj = JSON.parse(await file.text());
      let n = 0;
      for (const f of gj.features || []) {
        if (f.geometry?.type !== "Point") continue;
        const [lon, lat] = f.geometry.coordinates;
        const m = { id: Date.now().toString(36) + n, lat, lon, name: String(f.properties?.name || "Spot importé"), note: String(f.properties?.note || ""), created: f.properties?.created || new Date().toISOString() };
        mine.push(m); addMineMarker(m); n++;
      }
      saveMine();
      alert(`${n} spot(s) importé(s).`);
    } catch (err) {
      alert("Fichier invalide : " + err.message);
    }
    e.target.value = "";
  };

  // ---------- Panneau & avertissement ----------
  document.getElementById("toggle-panel").onclick = () => {
    document.body.classList.toggle("collapsed");
    setTimeout(() => map.invalidateSize(), 250);
  };
  const dlg = document.getElementById("disclaimer");
  document.getElementById("show-disclaimer").onclick = (e) => { e.preventDefault(); dlg.showModal(); };
  if (!localStorage.getItem(SEEN_KEY)) { dlg.showModal(); localStorage.setItem(SEEN_KEY, "1"); }

  // ---------- Chargement des données ----------
  document.getElementById("stats").textContent = "Chargement des lieux…";
  const load = (url) => fetch(url).then((r) => (r.ok ? r.json() : null)).catch(() => null);
  Promise.all([load("data/spots.json"), load("data/spots_wikidata.json")])
    .then(([osm, wd]) => {
      if (!osm && !wd) throw new Error("aucune donnée");
      window.__generated = (osm || wd).generated;
      spots = [...(osm?.spots || []), ...(wd?.spots || [])];
      markers = spots.map(makeMarker);
      normNames = spots.map((s) => (s[2] ? norm(s[2]) : ""));
      buildFilters();
      refresh();
    })
    .catch((err) => {
      document.getElementById("stats").textContent =
        "Impossible de charger data/spots.json (" + err.message + "). Lance « python scripts/fetch_spots.py » ou ouvre le site via un serveur web.";
    });
})();
