/*
 * Boutons « ✅ Accepter » / « ❌ Refuser » des tickets.
 *
 * GET  /moderer?n=12&a=accepter   → page de confirmation (ou demande du code modérateur)
 * POST /moderer                   → applique : accepter = pose le label « validé » (le workflow GitHub
 *                                   ajoute ou retire alors le lieu), refuser = ferme le ticket « not planned »
 *
 * Le dépôt est public : n'importe qui voit les boutons. Seul celui qui connaît le code modérateur
 * (secret MODO_CODE) peut s'en servir. Le code est demandé une fois, puis gardé dans un cookie
 * signé (HttpOnly, Secure, SameSite=Strict, 1 an) sur le domaine du relais.
 */

const COOKIE = "modo";

async function hmac(secret, text) {
  const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(text));
  return [...new Uint8Array(sig)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function same(a, b) {   // comparaison à temps constant
  if (a.length !== b.length) return false;
  let d = 0;
  for (let i = 0; i < a.length; i++) d |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return d === 0;
}

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function page(title, inner, status = 200, extraHeaders = {}) {
  return new Response(`<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">
<title>${esc(title)} · Urbex Map</title>
<style>
  body{margin:0;min-height:100vh;display:grid;place-items:center;background:#0d0f13;color:#eef0f4;font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
  main{width:min(420px,calc(100vw - 32px));background:#16191f;border:1px solid #262a33;border-radius:20px;padding:26px}
  h1{font-size:20px;margin:0 0 6px} p{color:#a9afbb;margin:6px 0 16px} b{color:#eef0f4}
  .t{background:#1d2028;border-radius:12px;padding:12px 14px;margin:0 0 18px;color:#eef0f4}
  input{width:100%;box-sizing:border-box;font:inherit;padding:12px;border-radius:12px;border:1px solid #333845;background:#0f1116;color:#fff;margin-bottom:12px}
  button,a.btn{display:block;width:100%;box-sizing:border-box;text-align:center;font:600 15px system-ui,sans-serif;padding:13px;border:0;border-radius:12px;cursor:pointer;text-decoration:none}
  .ok{background:#2ea44f;color:#fff}.no{background:#d73a4a;color:#fff}.gh{background:#262a33;color:#fff;margin-top:10px}
</style></head><body><main>${inner}</main></body></html>`, {
    status, headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store", "X-Frame-Options": "DENY", ...extraHeaders },
  });
}

async function gh(env, method, path, body) {
  return fetch(`${env.GITHUB_API || "https://api.github.com"}/repos/${env.REPO}${path}`, {
    method,
    headers: { "Authorization": `Bearer ${env.GITHUB_TOKEN}`, "Accept": "application/vnd.github+json",
      "User-Agent": "urbex-map-relais", "X-GitHub-Api-Version": "2022-11-28" },
    body: body ? JSON.stringify(body) : undefined,
  });
}

const ACTIONS = {
  accepter: { verbe: "Accepter", cls: "ok", icone: "✅" },
  refuser: { verbe: "Refuser", cls: "no", icone: "❌" },
};

export async function moderate(request, env) {
  if (!env.MODO_CODE) return page("Indisponible", "<h1>Modération pas encore configurée</h1><p>Le code modérateur n'est pas défini.</p>", 503);
  const url = new URL(request.url);
  const expected = await hmac(env.MODO_CODE, "moderateur-urbex-map");
  const cookie = (request.headers.get("Cookie") || "").match(new RegExp(`${COOKIE}=([a-f0-9]{64})`));
  let authed = !!cookie && same(cookie[1], expected);

  let n, a, code = "";
  if (request.method === "POST") {
    const f = await request.formData();
    n = f.get("n"); a = f.get("a"); code = String(f.get("code") || "");
  } else {
    n = url.searchParams.get("n"); a = url.searchParams.get("a");
  }
  n = String(n || ""); a = String(a || "");
  if (!/^\d{1,7}$/.test(n) || !ACTIONS[a]) return page("Lien invalide", "<h1>Lien invalide</h1><p>Ce lien de modération n'est pas complet.</p>", 400);
  const act = ACTIONS[a];
  const ghLink = `https://github.com/${env.REPO}/issues/${n}`;

  // Code modérateur envoyé : on le vérifie (limité à 5 essais par minute)
  let setCookie = {};
  if (!authed && code) {
    const ip = request.headers.get("CF-Connecting-IP") || "anonyme";
    if (env.LIMITER && !(await env.LIMITER.limit({ key: `modo:${ip}` })).success) {
      return page("Trop d'essais", "<h1>Trop d'essais</h1><p>Réessaie dans une minute.</p>", 429);
    }
    if (same(await hmac(env.MODO_CODE, code), await hmac(env.MODO_CODE, env.MODO_CODE))) {
      authed = true;
      setCookie = { "Set-Cookie": `${COOKIE}=${expected}; Max-Age=31536000; Path=/moderer; HttpOnly; SameSite=Strict${url.protocol === "https:" ? "; Secure" : ""}` };
    }
  }

  const issueR = await gh(env, "GET", `/issues/${n}`);
  if (!issueR.ok) return page("Ticket introuvable", `<h1>Ticket #${n} introuvable</h1>`, 404);
  const issue = await issueR.json();
  const labels = issue.labels.map((l) => l.name);
  if (!labels.includes("signalement") && !labels.includes("proposition")) {
    return page("Pas un ticket de la carte", `<h1>Ticket #${n}</h1><p>Ce n'est ni un signalement ni une proposition.</p>`, 400);
  }
  const kind = labels.includes("signalement") ? "signalement" : "proposition";
  const effet = a === "accepter"
    ? (kind === "signalement" ? "Le lieu sera <b>retiré de la carte</b>." : "Le lieu sera <b>ajouté à la carte</b>.")
    : "Le ticket sera <b>fermé</b>, la carte ne change pas.";
  const head = `<h1>${act.icone} ${act.verbe} ${kind === "signalement" ? "ce signalement" : "cette proposition"}</h1><div class="t">#${n} · ${esc(issue.title)}</div>`;

  if (!authed) {
    const wrong = code ? `<p style="color:#ff7b7b">Code incorrect.</p>` : "";
    return page("Code modérateur", `${head}<p>Entre ton <b>code modérateur</b>. Il ne sera plus demandé sur cet appareil.</p>${wrong}
      <form method="post"><input type="hidden" name="n" value="${n}"><input type="hidden" name="a" value="${a}">
      <input type="password" name="code" placeholder="Code modérateur" autocomplete="current-password" required autofocus>
      <button class="${act.cls}">${act.verbe}</button></form><a class="btn gh" href="${ghLink}">Voir le ticket</a>`, code ? 403 : 200);
  }

  // Déjà traité ?
  if (issue.state === "closed" || labels.includes("validé")) {
    return page("Déjà traité", `${head}<p>Ce ticket est déjà ${labels.includes("validé") ? "<b>accepté</b>" : "<b>fermé</b>"}.</p>
      <a class="btn gh" href="${ghLink}">Voir le ticket</a>`, 200, setCookie);
  }

  // Simple ouverture du lien (GET) : on demande confirmation, pour qu'un aperçu de lien ne déclenche rien
  if (request.method !== "POST") {
    return page("Confirmer", `${head}<p>${effet}</p>
      <form method="post"><input type="hidden" name="n" value="${n}"><input type="hidden" name="a" value="${a}">
      <button class="${act.cls}">Confirmer : ${act.verbe.toLowerCase()}</button></form>
      <a class="btn gh" href="${ghLink}">Voir le ticket</a>`, 200, setCookie);
  }

  // Confirmé : on applique
  const r = a === "accepter"
    ? await gh(env, "POST", `/issues/${n}/labels`, { labels: ["validé"] })
    : await gh(env, "PATCH", `/issues/${n}`, { state: "closed", state_reason: "not_planned" });
  if (!r.ok) {
    console.log("GitHub", r.status, await r.text());
    return page("Erreur", `${head}<p style="color:#ff7b7b">GitHub n'a pas répondu, réessaie dans un instant.</p>`, 502, setCookie);
  }
  if (a === "refuser") await gh(env, "POST", `/issues/${n}/comments`, { body: "❌ Refusé : la carte ne change pas." });
  const done = a === "accepter"
    ? `<p>✅ C'est fait. ${kind === "signalement" ? "Le lieu disparaîtra de la carte" : "Le lieu apparaîtra sur la carte"} d'ici <b>5 minutes</b>, et le ticket se fermera tout seul.</p>`
    : "<p>❌ Ticket refusé et fermé.</p>";
  return page("Fait", `${head}${done}<a class="btn gh" href="${ghLink}">Voir le ticket</a>`, 200, setCookie);
}

// Ligne de boutons ajoutée en tête des tickets
export const buttons = (origin, n) =>
  `**[✅ Accepter](${origin}/moderer?n=${n}&a=accepter)** · **[❌ Refuser](${origin}/moderer?n=${n}&a=refuser)**`;
