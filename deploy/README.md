# CI/CD sur VPS Docker

Les dépôts du site public, de l'admin et de l'API possèdent chacun un workflow GitHub Actions.
Une pull request vers `main` lance les vérifications sans déployer. Un push sur `main` ne
déploie qu'après réussite des tests et builds. Le déploiement synchronise les sources par SSH,
puis reconstruit et redémarre le service Docker correspondant.

## Préparer le VPS une fois

Le VPS utilise Hestia Control Panel avec Nginx et Apache actifs. Hestia reste responsable des
ports publics 80/443, des domaines et des certificats Let's Encrypt ; ne pas installer Caddy
ni exposer directement les ports des conteneurs sur Internet. Configurer le proxy Nginx de
chaque domaine Hestia vers le service local correspondant :

| Domaine | Service local |
|---|---|
| `african-talents.socoprocaap.com` | `http://127.0.0.1:8080` |
| `admin-african-talents.socoprocaap.com` | `http://127.0.0.1:8081` |
| `api-african.socoprocaap.com` | `http://127.0.0.1:8000` |

Les trois enregistrements DNS A doivent pointer vers l'IPv4 du VPS et les certificats HTTPS
doivent être actifs dans Hestia avant d'activer le proxy des domaines.

Créer les dossiers de déploiement dans l'espace Web Hestia et les attribuer au compte
de déploiement `deploy`, puis y déposer les fichiers `.env` **avant le premier push** :

```sh
sudo install -d -o deploy -g deploy -m 755 \
  /home/socoprocaap/web/apps/site \
  /home/socoprocaap/web/apps/admin \
  /home/socoprocaap/web/apps/api
```

Utiliser `deploy` comme secret `VPS_USER` dans les trois dépôts GitHub. Ce compte doit pouvoir
écrire dans ces dossiers et lancer `docker compose`. L'accès au groupe `docker` équivaut à des
privilèges élevés sur le VPS. Les fichiers `.env` restent sur le VPS : le workflow les exclut
pendant la synchronisation et échoue explicitement si l'un manque.

### API

Partir de `african-talents-api/.env.example`, le copier comme
`/home/socoprocaap/web/apps/api/.env`, puis retirer les lignes `COMPOSE_FILE` et
`COMPOSE_PATH_SEPARATOR` (elles activent la configuration locale de développement). Régler
au minimum :

- `DJANGO_SETTINGS_MODULE=config.settings.prod`, `DEBUG=False` et une `SECRET_KEY` aléatoire
  de production d'au moins 40 caractères ;
- `ALLOWED_HOSTS=api-african.socoprocaap.com` ;
- `CORS_ALLOWED_ORIGINS` et `CSRF_TRUSTED_ORIGINS` avec
  `https://african-talents.socoprocaap.com` et
  `https://admin-african-talents.socoprocaap.com` ;
- `POSTGRES_PASSWORD` avec un mot de passe fort et unique ;
- les clés de paiement et URLs de retour/webhook correspondant à l'environnement choisi.

Le Compose de l'API lance PostgreSQL, Redis, l'API, Celery worker et Celery beat. Le backend
exécute migrations et `collectstatic` au démarrage selon les variables de production.

### Site public et admin

Créer `/home/socoprocaap/web/apps/site/.env` et
`/home/socoprocaap/web/apps/admin/.env`. Chaque fichier doit
contenir l'URL publique de l'API, utilisée lors de la compilation Vite :

```dotenv
VITE_API_BASE_URL=https://api.example.com/api/v1
PUBLIC_SITE_PORT=8080
```

Pour l'admin, utiliser le port `8081` :

```dotenv
VITE_API_BASE_URL=https://api.example.com/api/v1
ADMIN_SITE_PORT=8081
```

Dans les deux fichiers `.env`, remplacer `https://api.example.com/api/v1` par
`https://api-african.socoprocaap.com/api/v1`.

Le site et l'admin sont servis par Nginx dans des conteneurs distincts. Le fallback SPA permet
aux routes Vue d'être rechargées directement.

## Configurer GitHub Actions

Dans **Settings → Secrets and variables → Actions** de chacun des trois dépôts, ajouter les
secrets suivants :

| Secret | Valeur |
|---|---|
| `VPS_HOST` | Adresse IP ou nom SSH du VPS |
| `VPS_USER` | Compte SSH non-root de déploiement |
| `VPS_SSH_KEY` | Clé privée SSH dédiée au déploiement |
| `VPS_KNOWN_HOSTS` | Ligne d'empreinte SSH vérifiée pour le VPS (`ssh-keyscan -H <hôte>`) |

Dans les dépôts du site et de l'admin, ajouter la variable (non secrète) `VITE_API_BASE_URL`
avec l'URL HTTPS de l'API, par exemple `https://api.example.com/api/v1`.

Ajouter la clé publique correspondante dans `~/.ssh/authorized_keys` du compte de déploiement.
Vérifier l'empreinte SSH du VPS par un canal de confiance avant de renseigner `VPS_KNOWN_HOSTS`.
Ne jamais mettre une clé privée, un mot de passe ou un fichier `.env` dans Git.
Le mot de passe PostgreSQL est obligatoire dans le Compose de production ; il n'y a pas de mot
de passe par défaut. Choisir des caractères alphanumériques ou encoder correctement les
caractères réservés d'une URL, car cette valeur sert aussi à construire `DATABASE_URL`.

## Déployer

Après la configuration initiale, fusionner ou pousser les changements sur `main` dans le dépôt
concerné. Son workflow lance les contrôles, puis déploie automatiquement le service concerné.
Une pull request ne déploie jamais. Un déploiement manuel du dernier commit de `main` est
également disponible dans l'onglet **Actions** via `workflow_dispatch`.

Les domaines, DNS, certificats Hestia, proxy Nginx, fichiers `.env` et identifiants GitHub
doivent être configurés une fois ; ils ne sont pas créés par un push.
