/* Urbex Map — carte des lieux abandonnés du monde entier */
(() => {
  "use strict";

  // ================================================================ Constantes
  const CATEGORIES = {
    industriel: { label: "Industriel", icon: "🏭", color: "#ffb020" },
    militaire:  { label: "Militaire", icon: "🪖", color: "#9ccc5a" },
    hopital:    { label: "Hôpitaux", icon: "🏥", color: "#ff6161" },
    chateau:    { label: "Châteaux", icon: "🏰", color: "#b98cff" },
    religieux:  { label: "Religieux", icon: "⛪", color: "#5ab0ff" },
    transport:  { label: "Transport", icon: "🚂", color: "#2ed3b7" },
    loisirs:    { label: "Hôtels & loisirs", icon: "🎡", color: "#ff7ac6" },
    habitation: { label: "Maisons & fermes", icon: "🏚️", color: "#e0b07a" },
    ruines:     { label: "Ruines", icon: "🧱", color: "#b3b3b3" },
    autre:      { label: "Autre", icon: "📍", color: "#e8e8e8" },
  };
  const STORE_KEY = "urbex.mine.v1";
  const FILTER_KEY = "urbex.filters.v1";
  const SEEN_KEY = "urbex.disclaimer.v1";
  const SOURCE_KEY = "urbex.sources.v2";
  const BASE_KEY = "urbex.base.v1";
  const REPO = "https://github.com/MAYLO083/urbex-map-france";
  const isMobile = () => matchMedia("(max-width: 760px)").matches;
  const $ = (id) => document.getElementById(id);
  const fmt = (n) => n.toLocaleString("fr-FR");
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  // Relais Cloudflare (worker/) : signaler et proposer sans compte GitHub. Vide = liens GitHub classiques.
  const RELAY = "https://urbex-map-relais.world-urbex.workers.dev";
  const TURNSTILE_SITEKEY = "0x4AAAAAAGSwpcxkprI2Tng5";
  const proposeUrl = (lat, lon, name = "") =>
    `${REPO}/issues/new?template=nouveau-spot.yml&title=${encodeURIComponent("[Spot] " + name)}` +
    `&coordonnees=${encodeURIComponent(lat.toFixed(5) + ", " + lon.toFixed(5))}&nom=${encodeURIComponent(name)}`;

  const ICONS = {
    sat: '<svg viewBox="0 0 24 24"><path d="M4 10l6-6 4 4-6 6z"/><path d="M14 14l6-6"/><path d="M10 14l4 4"/><path d="M14 18c2 0 4-2 4-4"/><path d="M14 22c4 0 8-4 8-8"/></svg>',
    eye: '<svg viewBox="0 0 24 24"><circle cx="12" cy="5" r="2.5"/><path d="M12 8v6M9 22l3-8 3 8M8 11h8"/></svg>',
    time: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>',
    go: '<svg viewBox="0 0 24 24"><path d="M3 11l18-8-8 18-2-8z"/></svg>',
    ext: '<svg viewBox="0 0 24 24" style="width:13px;height:13px"><path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/></svg>',
  };

  // ================================================================ Signaler / proposer sans compte (via le relais)
  let tsLoaded = null;
  const loadTurnstile = () => tsLoaded || (tsLoaded = new Promise((ok, ko) => {
    const sc = document.createElement("script");
    sc.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
    sc.onload = ok; sc.onerror = ko;
    document.head.appendChild(sc);
  }));
  const setupForm = (dlgId, path, okText, extra) => {
    const dlg = $(dlgId), form = dlg.querySelector("form"), msg = dlg.querySelector(".form-msg"), ts = dlg.querySelector(".ts");
    let token = "", widget = null;
    dlg.querySelector("[data-close]").onclick = () => dlg.close();
    const open = async (fill) => {
      form.reset();
      msg.textContent = ""; msg.className = "form-msg";
      form.querySelector("[type=submit]").disabled = false;
      fill(form);
      dlg.showModal();
      if (TURNSTILE_SITEKEY) {
        try {
          await loadTurnstile();
          if (widget === null) widget = window.turnstile.render(ts, { sitekey: TURNSTILE_SITEKEY, theme: "dark", callback: (t) => { token = t; } });
          else { window.turnstile.reset(widget); token = ""; }
        } catch { msg.textContent = "Vérification anti-robots indisponible, réessaie plus tard."; msg.className = "form-msg err"; }
      }
    };
    form.onsubmit = async (e) => {
      e.preventDefault();
      const btn = form.querySelector("[type=submit]");
      const data = Object.fromEntries(new FormData(form));
      if (form.regles) data.regles = form.regles.checked;
      Object.assign(data, extra ? extra() : {}, { turnstile: token });
      btn.disabled = true; msg.textContent = "Envoi…"; msg.className = "form-msg";
      try {
        const r = await fetch(RELAY + path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
        const res = await r.json().catch(() => ({}));
        if (!r.ok || !res.ok) throw new Error(res.error || "Envoi impossible, réessaie plus tard.");
        msg.textContent = okText; msg.className = "form-msg ok";
        setTimeout(() => dlg.close(), 2500);
      } catch (err) {
        msg.textContent = err.message; msg.className = "form-msg err";
        btn.disabled = false;
        if (widget !== null) { window.turnstile.reset(widget); token = ""; }
      }
    };
    return open;
  };
  let reportTarget = null;
  const openReport = setupForm("report-dlg", "/signaler", "✅ Merci ! Ton signalement est envoyé, il sera vérifié rapidement.", () => reportTarget);
  const openProposeForm = setupForm("propose-dlg", "/proposer", "✅ Merci ! Ta proposition est envoyée, elle sera vérifiée avant publication.");
  const openPropose = (p) => openProposeForm((f) => {
    f.nom.value = p.nom || "";
    f.coordonnees.value = p.lat != null ? `${p.lat.toFixed(5)}, ${p.lon.toFixed(5)}` : "";
    f.description.value = p.description || "";
  });
  document.addEventListener("click", (e) => {
    if (!RELAY) return;
    const a = e.target.closest(".report-link");
    if (!a) return;
    e.preventDefault();
    reportTarget = { lieu: a.dataset.refs, nom: a.dataset.nom, position: a.dataset.pos };
    openReport(() => { $("report-name").textContent = a.dataset.nom || "Lieu sans nom"; });
  });
  const centerText = () => { const c = map.getCenter(); return `${c.lat.toFixed(5)}, ${c.lng.toFixed(5)}`; };
  $("propose-dlg").querySelector("[data-center]").onclick = () => { $("propose-form").coordonnees.value = centerText(); };
  $("propose-cta").addEventListener("click", (e) => {
    if (!RELAY) return;
    e.preventDefault();
    const c = map.getCenter();
    openPropose({ lat: c.lat, lon: c.lng });
  });

  // ================================================================ Toast
  let toastTimer;
  const toast = (msg) => {
    const t = $("toast");
    t.textContent = msg;
    t.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.remove("show"), 2400);
  };

  // ================================================================ Carte
  const map = L.map("map", { preferCanvas: true, zoomControl: false, minZoom: 2, attributionControl: true,
    maxBounds: [[-85, -200], [85, 200]], maxBoundsViscosity: 0.8 });
  const renderer = L.canvas({ padding: 0.5 });
  map.attributionControl.setPrefix(false);

  const geopf = (layer, f = "image/jpeg") =>
    `https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=${layer}&STYLE=normal&TILEMATRIXSET=PM&FORMAT=${f}&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}`;
  const OSM_ATTR = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';
  const BASES = {
    dark: { label: "Nuit", preview: "https://tile.openstreetmap.org/6/32/22.png", dark: true,
      layer: () => L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, className: "tiles-dark", attribution: OSM_ATTR }) },
    osm: { label: "Plan", preview: "https://tile.openstreetmap.org/6/32/22.png",
      layer: () => L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: OSM_ATTR }) },
    planign: { label: "Plan IGN", preview: geopf("GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2", "image/png").replace("{z}", 6).replace("{y}", 22).replace("{x}", 32),
      layer: () => L.tileLayer(geopf("GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2", "image/png"), { maxZoom: 19, attribution: '&copy; <a href="https://geoservices.ign.fr/">IGN</a>' }) },
    sat: { label: "Satellite", preview: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/6/22/32",
      layer: () => L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", { maxZoom: 19, attribution: "Imagerie &copy; Esri, Maxar" }) },
    ign: { label: "Photo aérienne IGN", preview: geopf("ORTHOIMAGERY.ORTHOPHOTOS").replace("{z}", 6).replace("{y}", 22).replace("{x}", 32),
      layer: () => L.tileLayer(geopf("ORTHOIMAGERY.ORTHOPHOTOS"), { maxZoom: 19, attribution: '&copy; <a href="https://geoservices.ign.fr/">IGN</a>' }) },
    ign1950: { label: "Photo IGN 1950-1965", preview: geopf("ORTHOIMAGERY.ORTHOPHOTOS.1950-1965", "image/png").replace("{z}", 6).replace("{y}", 22).replace("{x}", 32),
      layer: () => L.tileLayer(geopf("ORTHOIMAGERY.ORTHOPHOTOS.1950-1965", "image/png"), { maxZoom: 18, attribution: '&copy; <a href="https://geoservices.ign.fr/">IGN</a>' }) },
  };
  let baseKey = BASES[localStorage.getItem(BASE_KEY)] ? localStorage.getItem(BASE_KEY) : "dark";
  let baseLayer = BASES[baseKey].layer().addTo(map);
  const setBase = (key) => {
    map.removeLayer(baseLayer);
    baseKey = key;
    baseLayer = BASES[key].layer().addTo(map);
    baseLayer.bringToBack();
    localStorage.setItem(BASE_KEY, key);
    buildLayersMenu();
  };
  L.control.scale({ imperial: false, position: "bottomleft" }).addTo(map);

  // Position (#zoom/lat/lon) ou France entière par défaut
  const m0 = location.hash.match(/^#(\d+(?:\.\d+)?)\/(-?\d+\.\d+)\/(-?\d+\.\d+)/);
  if (m0) map.setView([+m0[2], +m0[3]], +m0[1]);
  else map.fitBounds([[41.3, -5.2], [51.1, 9.6]], { paddingTopLeft: isMobile() ? [0, 0] : [390, 0] });
  map.on("moveend", () => {
    const c = map.getCenter();
    history.replaceState(null, "", `#${map.getZoom()}/${c.lat.toFixed(5)}/${c.lng.toFixed(5)}`);
  });

  // ================================================================ Commandes
  $("zoom-in").onclick = () => map.zoomIn();
  $("zoom-out").onclick = () => map.zoomOut();
  let meMarker;
  $("locate").onclick = () => { $("locate").classList.add("active"); map.locate({ setView: true, maxZoom: 13 }); };
  map.on("locationfound", (e) => {
    if (meMarker) meMarker.remove();
    meMarker = L.marker(e.latlng, { icon: L.divIcon({ className: "", html: '<div class="me-dot"></div>', iconSize: [18, 18] }), interactive: false }).addTo(map);
  });
  map.on("locationerror", () => { $("locate").classList.remove("active"); toast("Position introuvable"); });

  const buildLayersMenu = () => {
    $("layers-menu").innerHTML = Object.entries(BASES).map(([k, b]) =>
      `<button data-k="${k}" class="${k === baseKey ? "on" : ""}"><span class="sw${b.dark ? " sw-dark" : ""}" style="background-image:url('${b.preview}')"></span>${b.label}</button>`).join("");
  };
  buildLayersMenu();
  $("layers-btn").onclick = (e) => { e.stopPropagation(); $("layers-menu").hidden = !$("layers-menu").hidden; };
  $("layers-menu").onclick = (e) => { const b = e.target.closest("button"); if (b) { setBase(b.dataset.k); $("layers-menu").hidden = true; } };
  document.addEventListener("click", (e) => { if (!e.target.closest("#controls")) $("layers-menu").hidden = true; });

  // ================================================================ Sources
  const osmUrl = (id) => `https://www.openstreetmap.org/${{ n: "node", w: "way", r: "relation" }[id[0]]}/${id.slice(1)}`;
  const SOURCES = {
    communaute: { label: "Communauté", hint: "Lieux proposés et validés",
      link: (id) => [`${REPO}/issues/${id.slice(1)}`, "Voir la proposition"] },
    osm: { label: "OpenStreetMap", hint: "Abandonnés, en ruine, friches, bunkers",
      link: (id) => [osmUrl(id), "Voir sur OpenStreetMap"] },
    wikidata: { label: "Wikidata", hint: "Désaffectés, abandonnés, avec photos",
      link: (id) => [`https://www.wikidata.org/wiki/${id}`, "Fiche Wikidata"] },
    merimee: { label: "Monuments historiques 🇫🇷", hint: "Vestiges, désaffectés, menacés",
      link: (id) => [`https://pop.culture.gouv.fr/notice/merimee/${id.slice(1)}`, "Fiche Mérimée"] },
    friches: { label: "Friches 🇫🇷", hint: "Cartofriches · non reconverties",
      link: (id) => [`https://cartofriches.cerema.fr/cartofriches/?site=${encodeURIComponent(id.slice(1))}`, "Fiche Cartofriches"] },
    geonames: { label: "GeoNames", hint: "Villages abandonnés, ruines, gares, mines · monde",
      link: (id) => [`https://www.geonames.org/${id.slice(1)}`, "Fiche GeoNames"] },
    heritage: { label: "Patrimoine en danger 🇬🇧", hint: "Heritage at Risk · Angleterre",
      link: (id) => [`https://historicengland.org.uk/advice/heritage-at-risk/search-register/list-entry/${id.slice(1)}`, "Fiche Historic England"] },
    friches_uk: { label: "Friches 🇬🇧", hint: "Anciens bâtiments · Angleterre",
      link: (id) => [`https://www.planning.data.gov.uk/entity/${id.slice(1)}`, "Fiche du registre"] },
    mines_on: { label: "Mines abandonnées 🇨🇦", hint: "AMIS · Ontario",
      link: (id) => [`https://www.geologyontario.mines.gov.on.ca/persistent-linking?abandoned-mine=${id.slice(1)}`, "Fiche AMIS"] },
    casias: { label: "Anciens sites industriels 🇫🇷", hint: "CASIAS · souvent démolis · masqué par défaut",
      link: (id) => [`https://fiches-risques.brgm.fr/georisques/casias/${id.slice(1)}`, "Fiche Géorisques"] },
  };

  // ================================================================ État
  // Les lieux sont découpés en cases de 0,5° (data/tiles/c/*.json) : on ne charge que celles qu'on regarde.
  let meta = null;            // data/tiles/meta.json : version, totaux
  let worldCells = [];        // data/tiles/overview.json : une bulle par case de 4° (vue du monde)
  const chunks = new Map();   // data/tiles/o/*.json : bulles de 1° par carrés de 10° (vue régionale)
  let ovMode = null;          // "world" | "region" : bulles affichées
  const tileExists = new Set();
  const tiles = new Map();    // case → { items: [[lieu, marqueur]], ready, used }
  const shown = new Set();    // cases dont les marqueurs sont sur la carte
  const byId = new Map();     // id → [lieu, marqueur]
  const active = new Set(JSON.parse(localStorage.getItem(FILTER_KEY) || "null") || Object.keys(CATEGORIES));
  // CASIAS (anciens sites industriels, souvent démolis ou reconstruits) est masqué par défaut.
  // Les choix enregistrés avec l'ancienne version sont repris, sans CASIAS.
  const HIDDEN_BY_DEFAULT = ["casias"];
  const savedSources = JSON.parse(localStorage.getItem(SOURCE_KEY) || "null")
    || (JSON.parse(localStorage.getItem("urbex.sources.v1") || "null") || Object.keys(SOURCES)).filter((s) => !HIDDEN_BY_DEFAULT.includes(s));
  const activeSources = new Set(savedSources);
  let namedOnly = false;
  let pendingFocus = null;

  // ================================================================ Clusters & marqueurs
  function bubble(n) {
    const size = n < 10 ? 34 : n < 100 ? 42 : n < 1000 ? 50 : 58;
    const cls = n < 10 ? "s" : n < 100 ? "m" : n < 1000 ? "l" : "xl";
    const label = n >= 10000 ? Math.round(n / 1000) + "k" : n >= 1000 ? (n / 1000).toFixed(1).replace(".0", "") + "k" : n;
    return L.divIcon({ html: `<div>${label}</div>`, className: `ucluster ucluster-${cls}`, iconSize: [size, size] });
  }
  const cluster = L.markerClusterGroup({
    chunkedLoading: true,
    maxClusterRadius: (z) => (z < 9 ? 64 : z < 13 ? 48 : 32),
    disableClusteringAtZoom: 16,
    spiderfyOnMaxZoom: true,
    showCoverageOnHover: false,
    iconCreateFunction: (c) => bubble(c.getChildCount()),
  });
  map.addLayer(cluster);

  // Vue dézoomée : une bulle par case de 1°, avec le nombre de lieux (sans charger les lieux)
  const overviewLayer = L.markerClusterGroup({
    maxClusterRadius: 80,
    showCoverageOnHover: false,
    spiderfyOnMaxZoom: false,
    iconCreateFunction: (c) => bubble(c.getAllChildMarkers().reduce((t, m) => t + m.options.count, 0)),
  });

  const inFrance = (lat, lon) => lat > 41 && lat < 51.5 && lon > -5.5 && lon < 10;
  const coordsBtn = (lat, lon) =>
    `<button class="coords" data-copy="${lat.toFixed(5)}, ${lon.toFixed(5)}"><span>${lat.toFixed(5)}, ${lon.toFixed(5)}</span><em>Copier</em></button>`;
  const actionsHtml = (lat, lon) => `
    <div class="actions">
      <a class="act" target="_blank" rel="noopener" href="https://www.google.com/maps/@?api=1&map_action=map&center=${lat},${lon}&zoom=18&basemap=satellite">${ICONS.sat}Satellite</a>
      <a class="act" target="_blank" rel="noopener" href="https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${lat},${lon}">${ICONS.eye}Street View</a>
      ${inFrance(lat, lon) ? `<a class="act" target="_blank" rel="noopener" href="https://remonterletemps.ign.fr/comparer?lon=${lon}&lat=${lat}&z=17">${ICONS.time}Avant / après</a>` : ""}
      <a class="act" target="_blank" rel="noopener" href="https://www.google.com/maps/dir/?api=1&destination=${lat},${lon}">${ICONS.go}Y aller</a>
    </div>`;

  // Formulaire GitHub « Signaler un lieu », pré-rempli avec les fiches du lieu (toutes sources fusionnées)
  const reportUrl = (s, refs) => `${REPO}/issues/new?` + new URLSearchParams({
    template: "signaler-lieu.yml",
    title: `[Signalement] ${s[2] || "Lieu sans nom"}`,
    lieu: refs.map(([k, id]) => `${k}:${id}`).join(" "),
    nom: s[2] || "",
    position: `${s[0].toFixed(5)}, ${s[1].toFixed(5)}`,
  });

  const spotPopup = (s) => {
    const cat = CATEGORIES[s[3]] || CATEGORIES.autre;
    const src = SOURCES[s._src];
    const refs = [[s._src, s[5]], ...(s._also || [])];
    const srcTags = [...new Set(refs.map(([k]) => SOURCES[k].label))].map((l) => `<span class="tag src">${l}</span>`).join("");
    const links = refs.map(([k, id]) => { const [href, text] = SOURCES[k].link(id); return `<a class="src-link" target="_blank" rel="noopener" href="${href}">${text} ${ICONS.ext}</a>`; }).join("");
    const img = s[6]
      ? `<a target="_blank" rel="noopener" href="https://commons.wikimedia.org/wiki/File:${encodeURIComponent(s[6])}"><img class="pop-img" src="https://commons.wikimedia.org/wiki/Special:FilePath/${encodeURIComponent(s[6])}?width=600" alt="" loading="lazy"></a>`
      : `<div class="pop-band"></div>`;
    return `<div style="--c:${cat.color}">
      ${img}
      <div class="pop-body">
        <div class="pop-tags"><span class="tag cat">${cat.icon} ${cat.label}</span>${srcTags}</div>
        <h3>${esc(s[2] || "Lieu sans nom")}</h3>
        ${s[4] ? `<p class="pop-desc">${esc(s[4])}</p>` : ""}
        ${coordsBtn(s[0], s[1])}
        ${actionsHtml(s[0], s[1])}
        <div class="src-links">${links}</div>
        <a class="report-link" target="_blank" rel="noopener" href="${reportUrl(s, refs)}"
          data-refs="${esc(refs.map(([k, id]) => `${k}:${id}`).join(" "))}" data-nom="${esc(s[2] || "")}"
          data-pos="${s[0].toFixed(5)}, ${s[1].toFixed(5)}">🚩 Signaler un problème (démoli, rénové, habité…)</a>
      </div>
    </div>`;
  };

  const R = 8;
  const makeMarker = (s) => {
    const cat = CATEGORIES[s[3]] || CATEGORIES.autre;
    const m = L.circleMarker([s[0], s[1]], { renderer, radius: R, weight: 2.5, color: "#0d0f13", fillColor: cat.color, fillOpacity: 1 });
    m.on("mouseover", () => m.setStyle({ radius: R + 4, color: "#fff" }));
    m.on("mouseout", () => m.setStyle({ radius: R, color: "#0d0f13" }));
    m.bindPopup(() => spotPopup(s), { maxWidth: 300, minWidth: 260, autoPanPaddingTopLeft: isMobile() ? [10, 70] : [400, 20], autoPanPaddingBottomRight: isMobile() ? [10, 180] : [70, 20] });
    return m;
  };

  // Copier les coordonnées (délégation)
  document.addEventListener("click", (e) => {
    const b = e.target.closest("[data-copy]");
    if (!b) return;
    navigator.clipboard?.writeText(b.dataset.copy).then(() => toast("Coordonnées copiées"), () => toast(b.dataset.copy));
  });

  const inSources = (s) => activeSources.has(s._src) || (s._also || []).some(([k]) => activeSources.has(k));
  const visible = (s) => active.has(s[3]) && inSources(s) && (!namedOnly || s[2]);

  // Compteurs : meta.totals et overview donnent « catégorie|source|nommé(0/1) » → nombre
  const keyOk = (k) => { const [c, src, n] = k.split("|"); return active.has(c) && activeSources.has(src) && (!namedOnly || n === "1"); };
  const sumCounts = (n) => { let t = 0; for (const k in n) if (keyOk(k)) t += n[k]; return t; };
  const countBy = (part) => {
    const out = {};
    for (const [k, n] of Object.entries(meta.totals)) { const x = k.split("|")[part]; out[x] = (out[x] || 0) + n; }
    return out;
  };

  const renderOverview = () => {
    overviewLayer.clearLayers();
    if (!ovMode) return;
    const list = ovMode === "world" ? worldCells : [...chunks.values()].flatMap((c) => c.cells || []);
    const ms = [];
    for (const cell of list) {
      const n = sumCounts(cell.n);
      if (!n) continue;
      const m = L.marker(cell.c, { icon: bubble(n), count: n });
      m.on("click", () => map.setView(cell.c, ovMode === "world" ? Math.max(map.getZoom() + 2, 6) : 10));
      ms.push(m);
    }
    overviewLayer.addLayers(ms);
  };

  const refresh = () => {
    localStorage.setItem(FILTER_KEY, JSON.stringify([...active]));
    localStorage.setItem(SOURCE_KEY, JSON.stringify([...activeSources]));
    if (!meta) return;
    $("count-visible").textContent = fmt(sumCounts(meta.totals));
    cluster.clearLayers();
    const list = [];
    for (const k of shown) for (const [s, m] of tiles.get(k).items) if (visible(s)) list.push(m);
    cluster.addLayers(list);
    renderOverview();
  };

  // ================================================================ Filtres
  const buildFilters = () => {
    const counts = countBy(0);
    $("filters").innerHTML = Object.entries(CATEGORIES).map(([k, c]) => `
      <button class="chip ${active.has(k) ? "on" : ""}" data-k="${k}" style="--c:${c.color}">
        <span class="ico" style="background:${c.color}22">${c.icon}</span>
        <span class="lbl"><b>${c.label}</b><small>${fmt(counts[k] || 0)}</small></span>
      </button>`).join("");
  };
  $("filters").onclick = (e) => {
    const b = e.target.closest(".chip");
    if (!b) return;
    const k = b.dataset.k;
    active.has(k) ? active.delete(k) : active.add(k);
    b.classList.toggle("on", active.has(k));
    refresh();
  };
  document.querySelector(".mini-actions").onclick = (e) => {
    const v = e.target.dataset.all;
    if (v === undefined) return;
    active.clear();
    if (v === "1") Object.keys(CATEGORIES).forEach((k) => active.add(k));
    buildFilters();
    refresh();
  };
  $("named-only").onchange = (e) => { namedOnly = e.target.checked; refresh(); };

  const buildSourceFilters = () => {
    const counts = countBy(1);
    $("sources").innerHTML = Object.entries(SOURCES).filter(([k]) => counts[k]).map(([k, s]) => `
      <label class="src-row">
        <span class="txt"><b>${s.label}</b><small>${s.hint}</small></span>
        <span class="num">${fmt(counts[k])}</span>
        <input type="checkbox" data-k="${k}" ${activeSources.has(k) ? "checked" : ""}><i></i>
      </label>`).join("");
  };
  $("sources").onchange = (e) => {
    const k = e.target.dataset.k;
    e.target.checked ? activeSources.add(k) : activeSources.delete(k);
    refresh();
  };

  // ================================================================ Onglets
  document.querySelector(".tabs").onclick = (e) => {
    const t = e.target.closest(".tab");
    if (!t) return;
    document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("active", x === t));
    document.querySelectorAll(".tab-page").forEach((p) => p.classList.toggle("active", p.dataset.page === t.dataset.tab));
    if (isMobile()) openSheet(true);
  };

  // ================================================================ Recherche
  const norm = (s) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  // Index des noms découpé selon le début des mots (data/tiles/s/*.json) :
  // on ne télécharge que le morceau du mot le plus long tapé (même règle que build_tiles.py).
  const COMMON = new Set(("de du des la le les et au aux en sur sous ancien ancienne anciens anciennes site friche usine lieu " +
    "the of and old former der die das und alte ehemalige del di da do dos el saint sainte rue chemin route avenue dit pour " +
    "avec sans station service garage atelier societe ets etablissements entreprise").split(" "));
  const chars = (w) => Array.from(w);
  const safe = (p) => chars(p).map((c) => (/[a-z0-9_]/.test(c) ? c : "~" + c.codePointAt(0).toString(16) + ".")).join("");
  const shardKey = (w) => {
    const cs = chars(w), split = new Set(meta.split);
    let n = 3, p = cs.slice(0, n).join("");
    while (split.has(p)) {
      if (cs.length > n) p = cs.slice(0, ++n).join("");
      else { p = w + "_"; break; }
    }
    return p;
  };
  const shards = new Map();
  const loadShard = (p) => {
    if (!shards.has(p)) {
      shards.set(p, fetch(`data/tiles/s/${safe(p)}.json?v=${meta.v}`)
        .then((r) => (r.ok ? r.json() : []))
        .then((rows) => rows.map((r) => [r, norm(r[2])]))
        .catch(() => { shards.delete(p); return null; }));
    }
    return shards.get(p);
  };
  let lastFound = [];
  // Villes du monde (> 15 000 habitants, GeoNames) : chargées à la première recherche
  let citiesP = null;
  const loadCities = () => {
    if (!citiesP) {
      citiesP = fetch(`data/cities.json?v=${meta ? meta.v : 1}`)
        .then((r) => (r.ok ? r.json() : []))
        .then((rows) => rows.map((r) => [r, norm(r[0])]))
        .catch(() => { citiesP = null; return []; });
    }
    return citiesP;
  };
  const flag = (cc) => (/^[A-Z]{2}$/.test(cc) ? String.fromCodePoint(...[...cc].map((c) => 127397 + c.charCodeAt(0))) : "");
  let cityFound = [];
  const results = $("results");
  let searchTimer;
  $("search").addEventListener("input", (e) => {
    $("search-clear").hidden = !e.target.value;
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => runSearch(e.target.value), 120);
  });
  $("search").addEventListener("focus", () => { if (isMobile()) openSheet(true); });
  $("search-clear").onclick = () => { $("search").value = ""; $("search-clear").hidden = true; results.innerHTML = ""; $("search").focus(); };

  let searchSeq = 0;
  const runSearch = async (raw) => {
    const seq = ++searchSeq;
    const q = norm(raw.trim());
    results.innerHTML = "";
    if (q.length < 2) return;
    const words = q.split(/[^\p{L}\p{N}]+/u).filter(Boolean);
    const mineFound = mine.filter((m) => words.every((w) => norm(m.name || "").includes(w)));
    lastFound = [];
    cityFound = [];
    const citiesReady = loadCities();
    const key = words.filter((w) => chars(w).length >= 3 && !COMMON.has(w)).sort((a, b) => chars(b).length - chars(a).length)[0];
    let note = "";
    if (key && meta) {
      results.innerHTML = `<li class="none">Recherche…</li>`;
      const rows = await loadShard(shardKey(key));
      if (seq !== searchSeq) return;
      if (rows === null) note = "Recherche impossible, vérifie ta connexion";
      for (const [r, n] of rows || []) {
        if (words.every((w) => n.includes(w))) { lastFound.push(r); if (lastFound.length >= 50) break; }
      }
    } else if (!mineFound.length) note = "Tape un mot d'au moins 3 lettres (ex. sanatorium, Beelitz…)";
    const cities = await citiesReady;
    if (seq !== searchSeq) return;
    for (const [r, n] of cities) {
      if (n.startsWith(q) || (n.startsWith(words[0]) && words.every((w) => n.includes(w)))) {
        cityFound.push(r);
        if (cityFound.length >= 4) break;
      }
    }
    results.innerHTML = "";
    if (!mineFound.length && !lastFound.length && !cityFound.length) { results.innerHTML = `<li class="none">${note || "Aucun lieu trouvé"}</li>`; return; }
    results.innerHTML = cityFound.map((c, i) => `<li tabindex="0" data-c="${i}"><span class="ico" style="background:#5ab0ff22">🏙️</span>
        <span class="txt"><b>${esc(c[0])}</b><small>Ville · ${flag(c[3])} ${esc(c[3])}</small></span></li>`).join("") +
      mineFound.map((f) => `<li tabindex="0" data-m="${f.id}"><span class="ico" style="background:#ff3d0022">📌</span>
        <span class="txt"><b>${esc(f.name)}</b><small>Mon spot</small></span></li>`).join("") +
      lastFound.map((r, i) => {
        const c = CATEGORIES[r[3]] || CATEGORIES.autre;
        return `<li tabindex="0" data-r="${i}"><span class="ico" style="background:${c.color}22">${c.icon}</span>
          <span class="txt"><b>${esc(r[2])}</b><small>${c.label} · ${SOURCES[r[4]].label}</small></span></li>`;
      }).join("");
  };
  results.onclick = (e) => {
    const li = e.target.closest("li");
    if (!li) return;
    if (li.dataset.c) {
      const c = cityFound[+li.dataset.c];
      if (isMobile()) openSheet(false);
      map.setView([c[1], c[2]], 12);
      updateView();
    } else if (li.dataset.r) focusRemote(lastFound[+li.dataset.r]);
    else if (li.dataset.m) focusMine(mine.find((m) => m.id === li.dataset.m));
  };

  // Aller à un lieu trouvé : on centre la carte, la case se charge, puis on ouvre la fiche
  const focusRemote = (r) => {
    const [lat, lon, , cat, src, id] = r;
    if (!active.has(cat) || !activeSources.has(src) || namedOnly) {
      active.add(cat); activeSources.add(src); namedOnly = false; $("named-only").checked = false;
      buildFilters(); buildSourceFilters(); refresh();
    }
    if (isMobile()) openSheet(false);
    pendingFocus = id;
    map.setView([lat, lon], Math.max(map.getZoom(), 17));
    updateView();
  };

  // ================================================================ Mes spots
  const mineLayer = L.layerGroup().addTo(map);
  let mine = JSON.parse(localStorage.getItem(STORE_KEY) || "[]");
  const saveMine = () => { localStorage.setItem(STORE_KEY, JSON.stringify(mine.map(({ _marker, ...m }) => m))); renderMineList(); };
  const mineIcon = L.divIcon({ className: "", html: '<div class="pin mine"></div>', iconSize: [22, 22], iconAnchor: [11, 22], popupAnchor: [0, -20] });

  const renderMineList = () => {
    $("mine-count").textContent = mine.length || "";
    $("mine-list").innerHTML = mine.map((m) => `
      <li data-m="${m.id}"><span class="dia"></span>
        <span class="txt"><b>${esc(m.name)}</b><small>${m.note ? esc(m.note.slice(0, 60)) : new Date(m.created).toLocaleDateString("fr-FR")}</small></span>
      </li>`).join("");
  };
  $("mine-list").onclick = (e) => { const li = e.target.closest("li"); if (li) focusMine(mine.find((m) => m.id === li.dataset.m)); };
  const focusMine = (m) => {
    if (!m) return;
    if (isMobile()) openSheet(false);
    map.setView([m.lat, m.lon], Math.max(map.getZoom(), 16));
    setTimeout(() => m._marker.openPopup(), 300);
  };

  const minePopup = (m) => {
    const div = document.createElement("div");
    div.style.setProperty("--c", "#ff3d00");
    div.innerHTML = `
      <div class="pop-band"></div>
      <div class="pop-body pop-form">
        <div class="pop-tags"><span class="tag cat">📌 Mon spot</span><span class="tag src">Privé</span></div>
        <input class="n" value="${esc(m.name)}" placeholder="Nom du spot">
        <textarea class="t" placeholder="Notes : accès, état, date de visite…">${esc(m.note)}</textarea>
        ${coordsBtn(m.lat, m.lon)}
        ${actionsHtml(m.lat, m.lon)}
        <div class="row"><button class="btn primary s">Enregistrer</button><button class="btn danger d">Supprimer</button></div>
        <a class="src-link p" target="_blank" rel="noopener" href="#">Proposer à la carte publique ${ICONS.ext}</a>
      </div>`;
    div.querySelector(".p").onclick = (e) => {
      const name = div.querySelector(".n").value.trim();
      if (RELAY) { e.preventDefault(); openPropose({ lat: m.lat, lon: m.lon, nom: name, description: div.querySelector(".t").value }); return; }
      e.currentTarget.href = proposeUrl(m.lat, m.lon, name);
    };
    div.querySelector(".s").onclick = () => {
      m.name = div.querySelector(".n").value.trim() || "Mon spot";
      m.note = div.querySelector(".t").value;
      saveMine();
      m._marker.closePopup();
      toast("Spot enregistré");
    };
    div.querySelector(".d").onclick = () => {
      if (!confirm(`Supprimer « ${m.name} » ?`)) return;
      mine = mine.filter((x) => x !== m);
      m._marker.remove();
      saveMine();
      toast("Spot supprimé");
    };
    return div;
  };

  const addMineMarker = (m) => {
    m._marker = L.marker([m.lat, m.lon], { icon: mineIcon, draggable: true, zIndexOffset: 1000 })
      .bindPopup(() => minePopup(m), { maxWidth: 300, minWidth: 260 })
      .on("dragend", (e) => { const p = e.target.getLatLng(); m.lat = p.lat; m.lon = p.lng; saveMine(); toast("Spot déplacé"); })
      .addTo(mineLayer);
  };
  mine.forEach(addMineMarker);
  renderMineList();

  map.on("contextmenu", (e) => {
    const m = { id: Date.now().toString(36), lat: e.latlng.lat, lon: e.latlng.lng, name: "Mon spot", note: "", created: new Date().toISOString() };
    mine.push(m);
    saveMine();
    addMineMarker(m);
    m._marker.openPopup();
  });

  $("export").onclick = () => {
    if (!mine.length) return toast("Aucun spot à exporter");
    const gj = { type: "FeatureCollection", features: mine.map((m) => ({
      type: "Feature", geometry: { type: "Point", coordinates: [m.lon, m.lat] },
      properties: { name: m.name, note: m.note, created: m.created } })) };
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([JSON.stringify(gj, null, 2)], { type: "application/geo+json" }));
    a.download = `mes-spots-urbex-${new Date().toISOString().slice(0, 10)}.geojson`;
    a.click();
    URL.revokeObjectURL(a.href);
  };
  $("import").onchange = async (e) => {
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
      toast(`${n} spot${n > 1 ? "s" : ""} importé${n > 1 ? "s" : ""}`);
    } catch (err) {
      toast("Fichier invalide");
    }
    e.target.value = "";
  };

  // ================================================================ Panneau (bureau : replier / mobile : tiroir)
  const openSheet = (open) => { document.body.classList.toggle("sheet-open", open); };
  $("toggle-panel").onclick = () => {
    if (isMobile()) openSheet(!document.body.classList.contains("sheet-open"));
    else document.body.classList.toggle("collapsed");
  };
  // Glisser le tiroir sur mobile
  (() => {
    const panel = $("panel");
    let y0 = null, dy = 0, t0 = 0;
    const start = (e) => {
      if (!isMobile() || e.target.closest("input, button")) return;
      y0 = e.touches[0].clientY; dy = 0; t0 = Date.now();
      panel.style.transition = "none";
    };
    const move = (e) => {
      if (y0 === null) return;
      dy = e.touches[0].clientY - y0;
      const open = document.body.classList.contains("sheet-open");
      const base = open ? 0 : panel.offsetHeight - parseFloat(getComputedStyle(panel).getPropertyValue("--peek") || 150);
      panel.style.transform = `translateY(${Math.max(0, base + dy)}px)`;
    };
    const end = () => {
      if (y0 === null) return;
      panel.style.transition = ""; panel.style.transform = "";
      const open = document.body.classList.contains("sheet-open");
      if (Math.abs(dy) < 8 && Date.now() - t0 < 300) openSheet(!open);
      else if (dy < -50) openSheet(true);
      else if (dy > 50) openSheet(false);
      y0 = null;
    };
    for (const el of [$("grabber"), document.querySelector(".panel-head")]) {
      el.addEventListener("touchstart", start, { passive: true });
      el.addEventListener("touchmove", move, { passive: true });
      el.addEventListener("touchend", end);
    }
  })();
  map.on("click", () => { if (isMobile()) openSheet(false); });

  // ================================================================ Avertissement
  const dlg = $("disclaimer");
  $("show-disclaimer").onclick = () => dlg.showModal();

  // ================================================================ Chargement des cases visibles
  // (la fusion des doublons est faite à l'avance par scripts/build_tiles.py)
  const MAX_TILES = 40;
  const loadingEl = $("loading");
  let loadingCount = 0;
  const setLoading = (d) => { loadingCount += d; loadingEl.hidden = loadingCount <= 0; };

  const loadTile = (k) => {
    const cached = tiles.get(k);
    if (cached) { cached.used = Date.now(); return cached.ready; }
    const entry = { items: [], used: Date.now() };
    setLoading(1);
    entry.ready = fetch(`data/tiles/c/${k}.json?v=${meta.v}`)
      .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then((rows) => {
        for (const s of rows) {
          s._src = s[7];
          s._also = s[8];
          const m = makeMarker(s);
          entry.items.push([s, m]);
          byId.set(s[5], [s, m]);
        }
      })
      .catch(() => { tiles.delete(k); toast("Zone non chargée, vérifie ta connexion"); })
      .finally(() => setLoading(-1));
    tiles.set(k, entry);
    return entry.ready;
  };

  // Carrés de 10° de la vue régionale (bulles de 1° + liste des cases existantes)
  const chunkKeys = (b) => {
    const c = meta.chunk, out = [], exist = new Set(meta.chunks);
    for (let y = Math.floor(Math.max(-90, b.getSouth()) / c); y <= Math.floor(Math.min(89.9, b.getNorth()) / c); y++) {
      for (let x = Math.floor(Math.max(-180, b.getWest()) / c); x <= Math.floor(Math.min(179.9, b.getEast()) / c); x++) {
        if (exist.has(`${y}_${x}`)) out.push(`${y}_${x}`);
      }
    }
    return out;
  };
  const loadChunk = (k) => {
    if (!chunks.has(k)) {
      const entry = { cells: null };
      entry.ready = fetch(`data/tiles/o/${k}.json?v=${meta.v}`)
        .then((r) => r.json())
        .then((cells) => { entry.cells = cells; for (const c of cells) for (const t of c.t) tileExists.add(t); })
        .catch(() => { chunks.delete(k); });
      chunks.set(k, entry);
    }
    return chunks.get(k).ready;
  };

  // Cases visibles (avec une petite marge) ; null = trop de cases → vue dézoomée
  const neededTiles = () => {
    const z = map.getZoom();
    if (z < 8) return null;
    const b = map.getBounds().pad(0.15), t = meta.tile, out = [];
    for (let y = Math.floor(b.getSouth() / t); y <= Math.floor(b.getNorth() / t); y++) {
      for (let x = Math.floor(b.getWest() / t); x <= Math.floor(b.getEast() / t); x++) {
        const k = `${y}_${x}`;
        if (tileExists.has(k)) out.push(k);
      }
    }
    return z < 10 && out.length > MAX_TILES ? null : out;
  };

  // Libère la mémoire des cases vues il y a longtemps (utile si on parcourt beaucoup de pays)
  const evict = () => {
    if (tiles.size <= 160) return;
    const old = [...tiles.entries()].filter(([k]) => !shown.has(k)).sort((a, b) => a[1].used - b[1].used);
    for (const [k, e] of old.slice(0, tiles.size - 120)) {
      for (const [s] of e.items) byId.delete(s[5]);
      tiles.delete(k);
    }
  };

  let viewSeq = 0;
  const showOverview = (mode) => {
    if (map.hasLayer(cluster)) map.removeLayer(cluster);
    if (ovMode !== mode || mode === "region") { ovMode = mode; renderOverview(); }
    if (!map.hasLayer(overviewLayer)) map.addLayer(overviewLayer);
  };
  const updateView = async () => {
    if (!meta) return;
    const seq = ++viewSeq;
    if (map.getZoom() < 5) return showOverview("world");
    const fresh = chunkKeys(map.getBounds().pad(0.15)).filter((k) => !chunks.has(k) || !chunks.get(k).cells);
    if (fresh.length) { setLoading(1); await Promise.all(fresh.map(loadChunk)); setLoading(-1); }
    if (seq !== viewSeq) return;
    const need = neededTiles();
    if (!need) return showOverview("region");
    if (map.hasLayer(overviewLayer)) map.removeLayer(overviewLayer);
    if (!map.hasLayer(cluster)) map.addLayer(cluster);
    await Promise.all(need.map(loadTile));
    if (seq !== viewSeq) return; // la carte a bougé entre-temps : une vue plus récente s'en occupe
    const needSet = new Set(need), add = [], rem = [];
    for (const k of [...shown]) {
      if (needSet.has(k) && tiles.has(k)) continue;
      shown.delete(k);
      for (const [, m] of tiles.get(k)?.items || []) rem.push(m);
    }
    for (const k of need) {
      if (shown.has(k) || !tiles.has(k)) continue;
      shown.add(k);
      for (const [s, m] of tiles.get(k).items) if (visible(s)) add.push(m);
    }
    if (rem.length) cluster.removeLayers(rem);
    if (add.length) cluster.addLayers(add);
    evict();
    if (pendingFocus && byId.has(pendingFocus)) {
      const [, m] = byId.get(pendingFocus);
      pendingFocus = null;
      cluster.zoomToShowLayer(m, () => m.openPopup());
    }
  };
  map.on("moveend", updateView);

  // ================================================================ Démarrage
  (async () => {
    try {
      meta = await fetch(`data/tiles/meta.json?t=${Date.now()}`).then((r) => r.json());
      worldCells = await fetch(`data/tiles/overview.json?v=${meta.v}`).then((r) => r.json());
      $("splash-sub").textContent = `${fmt(meta.count)} lieux`;
      buildFilters();
      buildSourceFilters();
      refresh();
      updateView();
      if (meta.generated) {
        $("updated-line").textContent = `Données mises à jour le ${new Date(meta.generated).toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" })}. ${fmt(meta.merged)} doublons fusionnés entre les sources.`;
      }
    } catch {
      toast("Impossible de charger les lieux");
    } finally {
      setTimeout(() => {
        document.body.classList.add("ready");
        if (!localStorage.getItem(SEEN_KEY)) { dlg.showModal(); localStorage.setItem(SEEN_KEY, "1"); }
      }, 250);
    }
  })();
})();
