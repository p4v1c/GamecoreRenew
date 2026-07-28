# GameCore — Modèle de sécurité

> **Statut : les 4 phases décrites ci-dessous sont livrées et en production.**
> Ce document a été écrit comme un plan de déploiement ; il se lit désormais
> comme la description du modèle en place. Les mentions « cette PR » sont
> historiques. Vérification rapide sur un boîtier : `ss -tlnp` ne doit montrer
> que `:8443` en écoute non-loopback.

Objectif : **un seul port exposé au LAN — Caddy `:8443` en HTTPS** — tout le reste en
loopback, avec un login unique partagé appliqué par le reverse-proxy (`forward_auth`).
La TV (Electron → `http://localhost:8765`) reste **strictement inchangée** : pas de
login, pas de TLS pour elle.

## Architecture cible

```
LAN (téléphone / PC)
  └─ https://IP:8443  ── Caddy (tls internal, CA locale)
        ├─ /login*, /api/auth/*, /gc/addons, /gc/ca.crt   → core :8765 (sans auth)
        ├─ [forward_auth → core /api/auth/verify]
        │    ├─ /roms/*   → 127.0.0.1:8770  (rom-manager)
        │    ├─ /saves/*  → 127.0.0.1:8772  (save-manager)
        │    ├─ /rpcs3/*  → 127.0.0.1:8771  (rpcs3-manager)
        │    ├─ /api/*    → 403 (le cœur n'est JAMAIS exposé au LAN)
        │    └─ /…        → core :8765 (statiques : /assets/*, /covers/*)
        └─ /  → redirection /roms/
TV (boîtier)
  └─ Electron → http://localhost:8765 (loopback, aucune auth — accès physique = confiance)
```

Décisions actées : mot de passe **unique partagé** (pas de multi-comptes) ; trust CA
côté clients via **QR code** pointant sur `/gc/ca.crt` ; port Caddy **8443** ;
livraison **une branche + une PR par phase**.

## Phases

### Phase 1 — Tout en loopback (cette PR)
- Le backend écoute sur `127.0.0.1:8765` (unit systemd écrite par `install/arch.sh`,
  et fallback uvicorn d'Electron dans `electron/main.js`).
- Chaque addon écoute sur `127.0.0.1` (voir `docs/SECURITY.md` du repo
  [gamecore-addons](https://github.com/p4v1c/gamecore-addons)).
- Suppression des `CORSMiddleware allow_origins=["*"]` : derrière Caddy tout devient
  same-origin, et la TV est déjà same-origin.
- Sur une install existante, l'unit vivante `/etc/systemd/system/gamecore-backend.service`
  doit être alignée à la main (l'OTA ne réécrit pas les units) :
  `--host 0.0.0.0` → `--host 127.0.0.1`, puis `daemon-reload` + restart.

### Phase 2 — Caddy : reverse-proxy + TLS
- `install/Caddyfile` → `/etc/caddy/Caddyfile` ; `pacman -S caddy`,
  `systemctl enable --now caddy`, puis `caddy trust` (CA racine dans le trust système
  du boîtier : kiosk/Firefox sans warning).
- `tls internal` : la CA locale de Caddy sert de mini-CA. Les clients LAN installent
  la CA via `https://IP:8443/gc/ca.crt` (lien + QR sur la page de login et sur la
  page Sécurité de la TV).
- Le core gagne `GET /gc/addons` (payload du registre d'addons, consommé par la nav
  partagée — proxifié sans auth).
- Tant que la Phase 3 n'est pas déployée, `forward_auth` échoue (endpoint absent) :
  **deny-all par défaut**, aucun trou temporaire.

### Phase 3 — Login partagé
- `config/auth.json` (`{hash argon2id, generation}`, 0600) + `config/auth_secret`
  (32 octets, 0600, clé HMAC des cookies). `config/` est exclu du rsync OTA → ces
  fichiers survivent aux updates. Jamais commités (`.gitignore`).
- `backend/services/auth.py` : argon2-cffi ; cookie
  `expiry.generation.HMAC-SHA256(secret, "expiry.generation")` ; anti-bruteforce en
  mémoire (par IP via `X-Forwarded-For`, 5 échecs → backoff exponentiel).
- `backend/routers/auth.py` — exemptées de `forward_auth`, donc joignables sans
  session : `POST /api/auth/login` (cookie `gc_session` HttpOnly, Secure,
  SameSite=Lax, 30 j), `GET /api/auth/verify` (200 + `X-GC-User` / 302 vers
  `/login?next=…` / 401 — consommé par le `forward_auth` de Caddy),
  `POST /api/auth/logout`.
- `POST /api/auth/change-password` (incrémente `generation` → invalide toutes les
  sessions) est **derrière** le `forward_auth` : l'exemption large `/api/auth/*`
  la publiait au LAN entier. Sur une machine sans mot de passe elle répond 503 —
  elle ne sert pas à en définir un, elle sert à en changer un.
- Page `/login` autonome servie par le core ; définition du mot de passe : prompt
  dans `arch.sh` (l'installeur graphique l'exige), ou `gamecore-addon auth-reset`.
- Le core lui-même n'applique **aucune** auth sur ses routes (il n'est joignable
  qu'en loopback) : l'application de l'auth est le rôle exclusif de Caddy.

### Phase 4 — Addons derrière préfixe de chemin
- Chaque addon reçoit `root_path` via l'env `ADDON_BASE` (`/roms`, `/saves`,
  `/rpcs3`) ; `addon.json` gagne un champ `path`, recopié dans le registre par le
  CLI `gamecore-addon` et exposé par `/gc/addons`.
- La nav partagée et les pages des addons ne référencent plus aucun port : liens et
  fetch relatifs (ou via `/gc/addons`), les accès navigateur→core passent par les
  statiques `/assets/*` ou par un passthrough côté addon.
- Les addons n'écrivent **aucune ligne d'auth** : Caddy les protège, ils reçoivent
  seulement l'en-tête `X-GC-User`.

## Points d'exploitation
- **OTA** : `update/linux.sh` exclut `config/`, `emu/`, `emu-configs/`,
  `assets/logos|overlays/` → l'état local du boîtier (bibliothèque, auth, registre
  addons) survit aux mises à jour. L'OTA ne touche ni `/etc/systemd/*` ni
  `/etc/caddy/*`.
- **Reset du mot de passe** : `gamecore-addon auth-reset` (régénère le secret et le
  hash — toutes les sessions tombent).
- **Vérification** : `ss -tlnp` ne doit montrer, côté GameCore, que Caddy `:8443`
  exposé ; `8765/8770/8771/8772` uniquement sur `127.0.0.1`.
