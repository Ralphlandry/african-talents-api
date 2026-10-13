# CI/CD sur VPS Docker

Les dépôts du site public, de l'admin et de l'API possèdent chacun un workflow GitHub Actions.
Une pull request vers `main` lance les vérifications sans déployer. Un push sur `main` ne
déploie qu'après réussite des tests et builds. Le déploiement synchronise les sources par SSH,
puis reconstruit et redémarre le service Docker correspondant.

## Préparer le VPS une fois

Utiliser un VPS Linux avec Docker Engine, le plugin Docker Compose, `rsync` et Caddy installés.
Créer un compte de déploiement non-root autorisé à exécuter Docker. Configurer Caddy afin de
servir les domaines en HTTPS et de transférer les requêtes vers ces ports locaux :

```caddyfile
site.example.com {
    reverse_proxy 127.0.0.1:8080
}

admin.example.com {
    reverse_proxy 127.0.0.1:8081
}

api.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

Remplacer les trois noms de domaine par les domaines réels et faire pointer leur DNS vers le
VPS. Caddy obtient et renouvelle automatiquement les certificats TLS.

Créer les dossiers de déploiement et y déposer les fichiers `.env` **avant le premier push** :

```sh
sudo install -d -o DEPLOY_USER -g DEPLOY_USER \
  /opt/african-talents/site \
  /opt/african-talents/admin \
  /opt/african-talents/api
```

Le compte SSH configuré dans GitHub doit pouvoir écrire dans ces trois dossiers et lancer
`docker compose`. Les fichiers `.env` restent sur le VPS : le workflow les exclut pendant la
synchronisation et échoue explicitement si l'un manque.

### API

Partir de `african-talents-api/.env.example`, le copier comme
`/opt/african-talents/api/.env`, puis retirer les lignes `COMPOSE_FILE` et
`COMPOSE_PATH_SEPARATOR` (elles activent la configuration locale de développement). Régler
au minimum :

- `DJANGO_SETTINGS_MODULE=config.settings.prod`, `DEBUG=False` et une `SECRET_KEY` aléatoire
  de production d'au moins 40 caractères ;
- `ALLOWED_HOSTS` avec le domaine API ;
- `CORS_ALLOWED_ORIGINS` et `CSRF_TRUSTED_ORIGINS` avec les domaines du site et de l'admin,
  en HTTPS ;
- `POSTGRES_PASSWORD` avec un mot de passe fort et unique ;
- les clés de paiement et URLs de retour/webhook correspondant à l'environnement choisi.

Le Compose de l'API lance PostgreSQL, Redis, l'API, Celery worker et Celery beat. Le backend
exécute migrations et `collectstatic` au démarrage selon les variables de production.

### Site public et admin

Créer `/opt/african-talents/site/.env` et `/opt/african-talents/admin/.env`. Chaque fichier doit
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

Les domaines, DNS, Caddy, les fichiers `.env` de production et les identifiants GitHub doivent
être configurés une fois sur le VPS/GitHub ; ils ne sont pas créés par un push.
