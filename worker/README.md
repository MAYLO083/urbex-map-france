# Relais Urbex Map → GitHub

Permet de **signaler** un lieu et de **proposer** un lieu depuis la carte, **sans compte GitHub et sans quitter le site**.
Le relais (un Cloudflare Worker, gratuit) vérifie que l'envoi vient d'un humain (Cloudflare Turnstile),
limite à 5 envois par minute et par personne, puis crée l'issue GitHub. Elle a le même format que les formulaires
GitHub, donc la modération ne change pas : label `validé` → lieu retiré (signalement) ou ajouté (proposition).

## Mise en ligne (une seule fois)

1. **Compte Cloudflare** (gratuit, sans carte) : <https://dash.cloudflare.com/sign-up>
2. **Turnstile** (anti-robots) : tableau de bord Cloudflare → *Turnstile* → *Add widget*
   - nom : `Urbex Map`, domaine : `maylo083.github.io`, mode : *Managed*
   - noter la **Site Key** (publique) et la **Secret Key** (secrète)
3. **Jeton GitHub** : <https://github.com/settings/personal-access-tokens/new>
   - *Repository access* : seulement `MAYLO083/urbex-map-france`
   - *Permissions* → *Issues* : **Read and write** (rien d'autre)
4. Dans un terminal, dossier `worker/` :

   ```
   npx wrangler login
   npx wrangler secret put GITHUB_TOKEN        # coller le jeton GitHub
   npx wrangler secret put TURNSTILE_SECRET    # coller la Secret Key Turnstile
   npx wrangler secret put MODO_CODE           # code modérateur (boutons Accepter / Refuser)
   npx wrangler deploy
   ```

   `deploy` affiche l'adresse du relais, du type `https://urbex-map-relais.<compte>.workers.dev`.
5. Dans `js/app.js`, renseigner `RELAY` (adresse du relais) et `TURNSTILE_SITEKEY` (Site Key), puis publier.

Tant que `RELAY` est vide, l'appli garde les liens vers les formulaires GitHub.

## Essai en local

`.dev.vars` (non versionné) : `GITHUB_TOKEN=…` et, pour ne rien créer, `GITHUB_API=http://127.0.0.1:9999` (faux serveur).
Puis `npx wrangler dev --port 8787` et, dans `js/app.js`, `RELAY = "http://127.0.0.1:8787"`.

## Boutons Accepter / Refuser

Chaque ticket commence par **✅ Accepter · ❌ Refuser** (lien vers `/moderer` du relais).
Le dépôt est public : les boutons ne marchent qu'avec le **code modérateur** (secret `MODO_CODE`),
demandé une fois par appareil puis gardé un an dans un cookie du relais.
- Accepter → pose le label `validé` (le workflow GitHub retire ou ajoute le lieu, puis ferme le ticket)
- Refuser → ferme le ticket (« not planned ») avec un commentaire, la carte ne change pas
