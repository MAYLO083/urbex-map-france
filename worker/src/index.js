/*
 * Relais Urbex Map → GitHub (Cloudflare Worker)
 *
 * Reçoit les signalements et les propositions envoyés depuis la carte (sans compte),
 * vérifie qu'ils viennent bien d'un humain (Cloudflare Turnstile), limite le nombre d'envois,
 * puis crée l'issue GitHub correspondante. L'issue a exactement le même format que les
 * formulaires GitHub (.github/ISSUE_TEMPLATE), donc la modération ne change pas :
 * label « validé » → le lieu est retiré (signalement) ou ajouté (proposition).
 *
 * Secrets (npx wrangler secret put …) :
 *   GITHUB_TOKEN      jeton GitHub « fine-grained », droit Issues: Read and write sur ce dépôt seulement
 *   TURNSTILE_SECRET  clé secrète du widget Turnstile (facultatif mais conseillé)
 * Variables (wrangler.toml) : REPO, ALLOWED_ORIGINS
 */

const REASONS = [
  "Démoli ou détruit",
  "Rénové, réhabilité ou reconstruit (plus abandonné)",
  "Habité ou de nouveau en activité",
  "N'existe pas à cet endroit (erreur de position ou de données)",
  "Autre",
];
const CATEGORIES = [
  "Industriel", "Militaire / bunkers", "Hôpitaux / sanatoriums", "Châteaux / manoirs", "Religieux",
  "Transport / gares / tunnels", "Hôtels / écoles / loisirs", "Maisons / fermes", "Ruines", "Autre",
];

// Texte libre : longueur bornée, pas de mention @quelqu'un ni de titre Markdown qui casserait le formulaire
const clean = (v, max) => String(v ?? "")
  .replace(/[\u0000-\u0008\u000b-\u001f]/g, "")
  .replace(/@/g, "@​")
  .replace(/^#+/gm, "")
  .trim()
  .slice(0, max);

const section = (title, value) => `### ${title}\n\n${value || "_No response_"}\n\n`;
const SITE = "https://maylo083.github.io/urbex-map-france/";
const header = (link) => `_Envoyé depuis la carte (sans compte GitHub)._ · **[📍 Voir sur la carte](${link})**\n\n`;

function json(data, status, origin) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Access-Control-Allow-Origin": origin,
      "Vary": "Origin",
    },
  });
}

async function human(env, token, ip) {
  if (!env.TURNSTILE_SECRET) return true; // Turnstile pas encore configuré
  if (!token) return false;
  const form = new FormData();
  form.append("secret", env.TURNSTILE_SECRET);
  form.append("response", token);
  if (ip) form.append("remoteip", ip);
  const r = await fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify", { method: "POST", body: form });
  return (await r.json()).success === true;
}

function report(d) {
  const refs = String(d.lieu || "").match(/\b[a-z_]+:[A-Za-z0-9_.-]+/g);
  if (!refs || refs.length > 10) return { error: "Lieu inconnu : ouvre le signalement depuis la fiche du lieu." };
  if (!REASONS.includes(d.probleme)) return { error: "Choisis le problème dans la liste." };
  const nom = clean(d.nom, 120);
  const pos = String(d.position || "").match(/(-?\d{1,2}\.\d+),\s*(-?\d{1,3}\.\d+)/);
  const link = `${SITE}?lieu=${encodeURIComponent(refs.join(" "))}` + (pos ? `#18/${pos[1]}/${pos[2]}` : "");
  return {
    title: `[Signalement] ${nom || "Lieu sans nom"}`,
    labels: ["signalement"],
    body: header(link)
      + section("Identifiant du lieu (ne pas modifier)", refs.join(" "))
      + section("Nom du lieu", nom)
      + section("Position", clean(d.position, 60))
      + section("Quel est le problème ?", d.probleme)
      + section("Détails (facultatif)", clean(d.details, 1500)),
  };
}

function proposal(d) {
  const nom = clean(d.nom, 120);
  const m = String(d.coordonnees || "").match(/(-?\d{1,2}(?:[.,]\d+)?)\s*[,; ]\s*(-?\d{1,3}(?:[.,]\d+)?)/);
  if (!nom) return { error: "Donne un nom au lieu." };
  if (!m) return { error: "Coordonnées invalides (format « 45.12345, 4.56789 »)." };
  const lat = parseFloat(m[1].replace(",", ".")), lon = parseFloat(m[2].replace(",", "."));
  if (!(lat >= -85 && lat <= 85 && lon >= -180 && lon <= 180) || (lat === 0 && lon === 0)) return { error: "Coordonnées invalides." };
  if (!CATEGORIES.includes(d.categorie)) return { error: "Choisis une catégorie." };
  if (d.regles !== true) return { error: "Confirme que le lieu n'est pas habité." };
  return {
    title: `[Spot] ${nom}`,
    labels: ["proposition"],
    body: header(`${SITE}?repere=${lat.toFixed(5)},${lon.toFixed(5)}#17/${lat.toFixed(5)}/${lon.toFixed(5)}`)
      + section("Nom du lieu", nom)
      + section("Coordonnées GPS", `${lat.toFixed(5)}, ${lon.toFixed(5)}`)
      + section("Catégorie", d.categorie)
      + section("Description", clean(d.description, 1500))
      + section("Confirmation", "- [X] Ce lieu n'est pas habité et je n'ai pas d'information indiquant que son propriétaire refuse sa diffusion."),
  };
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const origin = request.headers.get("Origin") || "";
    const allowed = env.ALLOWED_ORIGINS.split(",").map((s) => s.trim());
    const ok = allowed.includes(origin) ? origin : allowed[0];

    if (request.method === "OPTIONS") {
      return new Response(null, { headers: {
        "Access-Control-Allow-Origin": ok, "Access-Control-Allow-Methods": "POST",
        "Access-Control-Allow-Headers": "Content-Type", "Access-Control-Max-Age": "86400", "Vary": "Origin" } });
    }
    if (request.method !== "POST" || !["/signaler", "/proposer"].includes(url.pathname)) {
      return json({ error: "Introuvable" }, 404, ok);
    }
    if (!allowed.includes(origin)) return json({ error: "Origine refusée" }, 403, ok);

    const ip = request.headers.get("CF-Connecting-IP") || "";
    if (env.LIMITER) {
      const { success } = await env.LIMITER.limit({ key: ip || "anonyme" });
      if (!success) return json({ error: "Trop d'envois d'un coup : réessaie dans une minute." }, 429, ok);
    }

    let d;
    try { d = await request.json(); } catch { return json({ error: "Requête invalide" }, 400, ok); }
    if (d.site) return json({ ok: true }, 200, ok); // champ piège : rempli seulement par les robots
    if (!(await human(env, d.turnstile, ip))) return json({ error: "Vérification anti-robots échouée, réessaie." }, 403, ok);

    const issue = url.pathname === "/signaler" ? report(d) : proposal(d);
    if (issue.error) return json({ error: issue.error }, 400, ok);

    const r = await fetch(`${env.GITHUB_API || "https://api.github.com"}/repos/${env.REPO}/issues`, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${env.GITHUB_TOKEN}`,
        "Accept": "application/vnd.github+json",
        "User-Agent": "urbex-map-relais",
        "X-GitHub-Api-Version": "2022-11-28",
      },
      body: JSON.stringify(issue),
    });
    if (!r.ok) {
      console.log("GitHub", r.status, await r.text());
      return json({ error: "Envoi impossible pour le moment, réessaie plus tard." }, 502, ok);
    }
    const created = await r.json();
    return json({ ok: true, numero: created.number }, 200, ok);
  },
};
