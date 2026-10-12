# African Talents API

Backend Django + Django REST Framework pour le site public et l'espace administrateur
African Talents. Développé par jalons (voir `RAPPORT_ANALYSE_ET_ARCHITECTURE_API.md` fourni
séparément pour le contexte complet et les décisions d'architecture).

**⚠️ Ce dépôt n'a pas encore été exécuté** (pas d'accès Docker/PostgreSQL/réseau dans
l'environnement où il a été écrit). Toutes les commandes ci-dessous sont donc à lancer et
vérifier de votre côté — merci de me renvoyer telles quelles les erreurs éventuelles.

## Démarrage (jalon 1)

```bash
cp .env.example .env
# éditez .env si besoin (les valeurs par défaut fonctionnent en local)

make up            # construit les images, démarre db + redis + backend + worker + beat
# dans un autre terminal, une fois "backend" démarré :
make migrations     # génère les fichiers de migration (à committer ensuite dans le dépôt Git)
make migrate         # applique les migrations (crée aussi le catalogue de permissions + rôle Super Admin)
make seed            # crée les rôles prédéfinis (Contenu, Candidats, Compétition, Catégories, Équipe, Financier)
make superuser        # crée votre premier compte Super Admin (email + mot de passe demandés)
```

Vérifications rapides :
- `GET http://localhost:8000/api/v1/health/` → `{"status": "ok"}`
- `http://localhost:8000/api/docs/` → documentation Swagger (activée par défaut en dev)
- `POST http://localhost:8000/api/v1/auth/login/` avec l'email/mot de passe du superuser créé

## Tests

```bash
make test
```

La suite couvre :
- **Jalon 1** : connexion, verrouillage après échecs répétés, rotation du refresh token +
  rejeu de l'ancien jeton refusé, révocation de session à la désactivation d'un compte,
  changement de mot de passe, RBAC (permission par action, refus par défaut, anti-escalade
  de privilèges, protection du dernier Super Admin, protection des rôles système), journal
  d'audit en ajout seul, et un test qui parcourt **toutes** les routes `/api/v1/` pour
  vérifier qu'aucune ne s'appuie sur la permission par défaut (`DenyByDefault`).
- **Jalon 2** : upload de médias (rejet des fichiers déguisés — extension trompeuse et
  taille excessive — vérification par signature de fichier, pas seulement par nom), une
  seule compétition "courante" à la fois, protection d'une phase active contre la
  suppression, réordonnancement des catégories, code candidat normalisé + unicité par
  compétition, actions groupées (publier/activer/désactiver/supprimer), assainissement du
  HTML des actualités (balises `<script>`/attributs `onerror` retirés), programmation de
  publication (y compris la tâche périodique qui publie automatiquement à la date prévue),
  singleton `SiteSettings`, et l'API publique (aucune authentification requise, seuls les
  éléments publiés/actifs/visibles sont exposés, 404 propre sur un candidat non publié).
- **Jalon 3** : forfaits de vote définis par l'admin (quantité/prix non fixes, pas de prix
  codé en dur), création de commande idempotente (rejeu de la même clé = même commande, pas
  de doublon), rejet si votes fermés ou forfait d'une autre compétition, **le prix ne peut
  jamais venir du client** (test explicite d'injection), ajustement manuel avec motif
  obligatoire, classement calculé depuis le grand livre des votes (pas un compteur
  dénormalisé) — y compris via l'endpoint HTTP réel, pas seulement la fonction service.
  Côté paiement : client HR-Skills Pay testé avec un faux transport HTTP (jeton mis en
  cache, préfixe sandbox, erreurs réseau et erreurs API distinguées), machine à états
  (transitions illégales refusées, un paiement terminal ignore tout événement tardif, un
  rejeu du même statut ne crédite jamais deux fois), webhook testé à la fois comme fonction
  service **et** comme vrai appel HTTP (signature invalide → 400, rien ne bouge ; signature
  valide → revérification du montant avant tout crédit ; événement rejoué → non retraité),
  expiration automatique des paiements orphelins, remboursement limité aux paiements
  réussis. Côté finance : agrégats, compte marchand (erreur propre si HR-Skills Pay est
  injoignable), rapprochement (MATCH/MISSING/AMOUNT MISMATCH/STATUS MISMATCH/UNMATCHED
  PROVIDER), rapports par période. Et le parcours public complet, de bout en bout : liste
  des forfaits actifs → création de commande → suivi par polling.
- **Jalon 4** : un scénario de bout en bout unique qui traverse (presque) toute
  l'application avec de vrais appels HTTP, dans l'ordre où un utilisateur réel les
  déclencherait — connexion admin → création de compétition/phase/catégorie/candidat/forfait
  → le site public voit tout ça → un visiteur vote → webhook confirme le paiement → le
  classement public ET admin reflètent le vote → la finance admin voit la transaction →
  actualité et membre d'équipe publiés → le journal d'audit contient bien toutes les actions
  clés — plus un test dédié qui vérifie qu'un admin "Contenu" reste bloqué partout ailleurs
  tout au long de ce même parcours. Et la commande `seed_demo` : données créées en nombre
  attendu, connexion possible avec le mot de passe documenté, rejeu sans duplication, refus
  hors DEBUG.

### Documentation interactive (OpenAPI)

`http://localhost:8000/api/docs/` (Swagger, activé par défaut en dev) décrit maintenant
chaque groupe de routes avec une description, et les paramètres de requête des endpoints de
filtrage/statistiques (rapports financiers, séries de votes, classement...) sont documentés
avec leurs valeurs possibles — pas seulement les corps de requête des créations/modifications.

### Paiement international par carte

Le parcours de vote peut proposer Visa/Mastercard via la page hébergée E-NKAP de HR-Skills Pay.
Les données de carte restent chez le prestataire ; les votes sont crédités uniquement après
confirmation serveur (webhook signé et statut relu chez le prestataire). En test, configurez
`HRSKILLS_CARD_ENABLED=True`, les clés `HRSKILLS_*` de test et
`HRSKILLS_CARD_RETURN_URL=https://votre-site.example/paiement/retour`. Cette URL est complétée
automatiquement par la référence de commande. La route de retour ne fait qu'interroger l'API :
elle ne considère jamais le simple retour navigateur comme une preuve de paiement.

Avant d'accepter des paiements réels, validez le parcours avec les clés de test puis activez
`HRSKILLS_ENVIRONMENT=live`, `HRSKILLS_ALLOW_LIVE=True` et `HRSKILLS_CARD_ENABLED=True`.
En production, l'URL de retour doit être en HTTPS. Le prestataire doit aussi avoir le webhook
de paiement configuré vers `/api/v1/payments/webhooks/hrskills/`.

## Billetterie en ligne

Après déploiement, appliquez les migrations puis configurez les deux tarifs (`Billet classique`
et `Billet VIP`) dans **Admin > Billetterie**. La route publique `/billetterie` affiche
uniquement les tarifs actifs de la compétition en cours lorsque la vente est ouverte. La vente
est fermée par défaut ; un compte disposant de `tickets.manage` peut l'ouvrir ou la clôturer
depuis **Admin > Billetterie**. L'API refuse également la création de commandes tant qu'elle est
fermée. Le minuteur de l'accueil s'affiche pendant l'ouverture et disparaît à la clôture ; il
compte jusqu'à la date de fin de la compétition configurée dans l'administration. Chaque fiche
candidat propose aussi un lien `/billetterie?promo=CODE-CANDIDAT` à partager : le code attribue
la vente au candidat, sans réduction de prix. Les montants sont toujours relus côté serveur.

Les paiements sont initiés par MTN Mobile Money ou Orange Money via HR-Skills Pay. Une commande
reste en attente tant que le prestataire n'a pas confirmé le paiement ; seul un billet payé
compte comme point candidat et autorise le téléchargement du PDF. Le webhook reste revérifié
auprès du prestataire avant de confirmer une commande. Le PDF reprend le style des billets
physiques, affiche le nom du titulaire, un code unique et son QR code ; le nom et une pièce
d'identité sont à vérifier à l'entrée. Configurez d'abord les identifiants de test Mobile Money
et réalisez un achat de test avant toute activation en production. La page et
le PDF n'inventent pas de date ou de lieu d'événement, ces informations n'ayant pas encore été
définies.

## Commandes utiles

| Commande | Effet |
|---|---|
| `make up` / `make down` | Démarre / arrête tous les services |
| `make logs` | Suit les logs du backend |
| `make migrations` | Génère les migrations (à committer) |
| `make migrate` | Applique les migrations |
| `make seed` | Crée les rôles prédéfinis |
| `make superuser` | Crée un Super Admin |
| `make test` | Lance `pytest` |
| `make shell` | Shell Django (`manage.py shell`) dans le conteneur |

## État d'avancement

| Jalon | Contenu | Statut |
|---|---|---|
| **1** | Socle (settings dev/prod/test, erreurs, pagination), comptes, JWT (access + refresh en cookie HttpOnly, rotation + liste noire), RBAC (`RBACPermission`, refus par défaut), gestion des administrateurs et des rôles avec garde-fous anti-escalade, journal d'audit en ajout seul | **Livré et testé en local (Docker + Postgres réels)** |
| **2** | Médiathèque (upload validé par signature de fichier), compétition + phases, catégories (réordonnancement, publication), candidats (galerie, réseaux sociaux, actions groupées), actualités (contenu HTML assaini côté serveur, programmation via Celery Beat), équipe & coachs, `SiteSettings` (singleton), API publique en lecture seule (`/api/v1/public/...`) | **Livré** |
| **3** | Forfaits de vote **définis par l'admin** (quantité + prix, décision B), commandes de vote + paiement Mobile Money (HR-Skills Pay), webhook sécurisé (signature + revérification + déduplication), ajustement manuel de votes, finance (vue d'ensemble, compte marchand, rapprochement, rapports), classement réel (agrégation du grand livre de votes, plus de zéro provisoire) | **Livré** |
| **4** | Tests bout en bout (un scénario complet traversant toutes les apps), OpenAPI finalisé (tags, descriptions, paramètres de requête documentés), jeu de données de démonstration (`seed_demo`) | **Livré ici** |
| 5 | Connexion des deux frontends Vue à l'API (remplacement des services mockés) | À venir |

### Jalon 4 — un bug trouvé et corrigé par le test de bout en bout

En écrivant le scénario complet (`apps/core/tests/test_end_to_end.py`), j'ai trouvé un vrai bug
introduit au jalon 2 : contrairement à `Competition`, `Candidate` et `NewsPost`, le champ `slug`
de `Category` n'était **pas** marqué `read_only` dans son sérialiseur, alors que le service le
génère automatiquement. Conséquence concrète : créer une catégorie sans fournir explicitement
un `slug` aurait échoué avec une erreur de validation — exactement le genre de problème que les
tests unitaires isolés (qui testent chaque service directement) ne voient pas forcément, mais
qu'un test passant par le vrai point d'entrée HTTP révèle. Corrigé dans
`apps/categories/serializers.py`. C'est aussi la preuve que ce test de bout en bout apporte
quelque chose que les ~160 tests unitaires précédents ne couvraient pas à eux seuls.

### Démarrage rapide avec des données de démonstration

```bash
make seed            # rôles prédéfinis (si pas déjà fait)
make seed-demo        # compétition, catégories, candidats, votes, actualités, équipe, paramètres...
```
Comptes créés (mot de passe unique : `demo1234!`) :
`super.admin@demo.africantalents.africa` (Super Admin), `contenu@…` (Contenu),
`candidats@…` (Candidats), `finance@…` (Financier). La commande refuse de s'exécuter si
`DEBUG=False` sans `--force` (ces mots de passe sont publics, ne jamais les utiliser en
production).

### Jalon 3 — points à lire avant de tester les paiements

**L'intégration HR-Skills Pay n'est PAS vérifiée contre un vrai sandbox.** Comme expliqué
dans le rapport d'architecture (§12), je n'ai pas pu accéder à `hrskills-pay.com/docs` (site
en JavaScript, sous-domaine `docs.` qui bloque l'accès automatisé) ni installer le SDK
officiel (pas de réseau ici). `apps/payments/gateway.py` implémente donc le **contrat HTTP
documenté** dans les README publics des SDK (endpoints, en-têtes, statuts) plutôt qu'une API
de SDK que je ne pouvais pas vérifier — c'est le choix le plus sûr, mais :
- les noms exacts des champs de réponse (`status`, `provider_reference`, `fees`...) sont une
  reconstruction prudente (`_extract` lit plusieurs noms plausibles) ;
- le préfixe `/sandbox` en environnement de test est **activé par défaut** mais configurable
  (`HRSKILLS_USE_SANDBOX_PREFIX`) à cause d'une contradiction relevée entre les SDK Python et Go ;
- **avant toute connexion à de vraies clés de test**, il faudra très probablement ajuster
  `gateway.py` selon ce que l'API réelle renvoie (un simple test avec vos clés `hrsk_*_test_...`
  suffira à le voir).

**Trois simplifications volontaires** par rapport au rapport d'architecture initial :
- Pas de modèle `IdempotencyRecord` séparé : l'unicité de `VoteOrder.idempotency_key` et de
  `VoteOrder.order_number` (repris comme référence de paiement et comme en-tête
  `Idempotency-Key` envoyé à HR-Skills Pay) couvre déjà le besoin sans table supplémentaire.
- Pas de modèle `MerchantSnapshot` persisté : le solde marchand est mis en cache 2 minutes
  (Django cache) plutôt qu'historisé en base — suffisant pour l'affichage, à revoir si un
  historique du solde devient nécessaire.
- Un remboursement ne retire **pas** automatiquement les votes déjà crédités (accounting
  choice : un vote émis reste compté). Pour les retirer, l'admin utilise l'ajustement manuel
  (`votes.adjust`) séparément, avec motif et traçabilité.

**Ce qui est solide indépendamment de ces réserves** : la machine à états des paiements est
monotone et testée (pas de retour en arrière possible depuis un état terminal), le webhook
revérifie toujours le statut auprès de l'API avant de créditer un vote (jamais de confiance
aveugle dans le contenu du webhook), un montant qui ne correspond pas bloque le crédit, les
événements rejoués ne sont jamais retraités, et le prix d'un vote ne peut jamais être choisi
par le client — toujours résolu côté serveur depuis un `VotePackage` existant.

### Note sur le classement (jalon 2 → jalon 3)

Le champ `votes_total` renvoyé par l'API (candidats, API publique) vaut **toujours 0** pour
l'instant : le classement dépend du grand livre des votes (`Vote`), qui n'existe qu'à partir
du jalon 3 (système de paiement). Les modèles Candidat/Catégorie sont déjà prêts à recevoir
cette agrégation sans changement de schéma.

### Corrections apportées pendant les tests du jalon 1 (Docker/Windows)

En testant en local, trois ajustements ont été nécessaires et sont déjà intégrés ici :
- Le *healthcheck* PostgreSQL attendait trop peu de temps lors de la toute première
  initialisation de la base (`start_period` et `retries` augmentés).
- Le port du backend est maintenant configurable via `BACKEND_PORT` dans `.env` (utile si
  8000 est déjà pris par un autre projet local — les listes `ports:` de Docker Compose
  s'additionnent entre `docker-compose.yml` et `docker-compose.dev.yml`, elles ne se
  remplacent pas, d'où l'intérêt de ne le déclarer qu'à un seul endroit).

## Notes de sécurité déjà en place

- Aucune donnée de carte bancaire n'est acceptée par l'API (retiré du formulaire de vote au jalon 3, cf. décision A).
- `SECRET_KEY`, clés HR-Skills Pay et autres secrets : jamais codés en dur, jamais journalisés
  (`apps/core/log_filters.py` les masque même en cas de fuite accidentelle dans un message de log).
- `config/settings/prod.py` refuse de démarrer si `DEBUG=True`, si `SECRET_KEY` ressemble à une
  clé de développement, ou si `ALLOWED_HOSTS`/`CORS_ALLOWED_ORIGINS` contiennent un joker.
- Toute route de l'API doit déclarer explicitement sa permission ; la permission par défaut
  (`DenyByDefault`) refuse tout, et c'est vérifié par un test automatique.
#   a f r i c a n - t a l e n t s - a p i  
 