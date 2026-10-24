"""
Catalogue des permissions (taxonomie `ressource.action`, identique à l'espace admin).
Ajouter une permission = ajouter une ligne ici ; elle est synchronisée en base à chaque `migrate`.
"""

PERMISSION_GROUPS = [
    {"key": "candidates", "label": "Candidats", "permissions": [
        ("candidates.view", "Voir les candidats"),
        ("candidates.create", "Créer un candidat"),
        ("candidates.edit", "Modifier un candidat"),
        ("candidates.delete", "Supprimer un candidat"),
        ("candidates.publish", "Publier un candidat"),
    ]},
    {"key": "categories", "label": "Catégories", "permissions": [
        ("categories.view", "Voir les catégories"),
        ("categories.create", "Créer une catégorie"),
        ("categories.edit", "Modifier une catégorie"),
        ("categories.delete", "Supprimer une catégorie"),
        ("categories.publish", "Publier une catégorie"),
    ]},
    {"key": "news", "label": "Actualités", "permissions": [
        ("news.view", "Voir les actualités"),
        ("news.create", "Créer un article"),
        ("news.edit", "Modifier un article"),
        ("news.delete", "Supprimer un article"),
        ("news.publish", "Publier un article"),
    ]},
    {"key": "team", "label": "Équipe & coachs", "permissions": [
        ("team.view", "Voir l'équipe et les coachs"),
        ("team.create", "Ajouter un membre"),
        ("team.edit", "Modifier un membre"),
        ("team.delete", "Supprimer un membre"),
    ]},
    {"key": "partners", "label": "Partenaires", "permissions": [
        ("partners.view", "Voir les partenaires"),
        ("partners.create", "Ajouter un partenaire"),
        ("partners.edit", "Modifier un partenaire"),
        ("partners.delete", "Supprimer un partenaire"),
    ]},
    {"key": "competition", "label": "Compétition", "permissions": [
        ("competition.view", "Voir la compétition"),
        ("competition.edit", "Modifier la compétition et ses phases"),
        ("competition.start", "Démarrer la compétition"),
        ("competition.stop", "Arrêter la compétition"),
    ]},
    {"key": "vote_packages", "label": "Forfaits de vote", "permissions": [
        ("vote_packages.view", "Voir les forfaits de vote"),
        ("vote_packages.create", "Créer un forfait de vote"),
        ("vote_packages.edit", "Modifier un forfait de vote"),
        ("vote_packages.delete", "Supprimer un forfait de vote"),
    ]},
    {"key": "votes", "label": "Votes & classement", "permissions": [
        ("votes.view", "Voir les votes"),
        ("votes.export", "Exporter les votes"),
        ("votes.statistics", "Voir les statistiques de vote"),
        ("votes.adjust", "Ajuster manuellement des votes"),
        ("rankings.view", "Voir le classement"),
    ]},
    {"key": "payments", "label": "Paiements & finance", "permissions": [
        ("payments.view", "Voir les paiements et transactions"),
        ("payments.statistics", "Voir les statistiques financières"),
        ("payments.export", "Exporter les données financières"),
        ("payments.refund", "Rembourser un paiement"),
        ("payments.view_sensitive", "Voir les numéros de téléphone en clair"),
        ("merchant.view", "Voir le compte marchand HR-Skills Pay"),
        ("reconciliation.view", "Voir le rapprochement financier"),
        ("reconciliation.run", "Lancer un rapprochement financier"),
    ]},
    {"key": "ticketing", "label": "Billetterie", "permissions": [
        ("tickets.manage", "Gérer les tarifs des billets"),
        ("tickets.statistics", "Voir les ventes et points de billetterie"),
    ]},
    {"key": "media", "label": "Médiathèque", "permissions": [
        ("media.view", "Voir la médiathèque"),
        ("media.upload", "Ajouter un média"),
        ("media.delete", "Supprimer un média"),
    ]},
    {"key": "admins", "label": "Administration", "permissions": [
        ("admins.view", "Voir les administrateurs"),
        ("admins.create", "Créer un administrateur"),
        ("admins.edit", "Modifier un administrateur"),
        ("admins.delete", "Supprimer / désactiver un administrateur"),
        ("admins.permissions", "Gérer les rôles et permissions"),
        ("audit.view", "Voir le journal d'activité"),
    ]},
    {"key": "notifications", "label": "Notifications", "permissions": [
        ("notifications.view", "Voir les notifications"),
        ("notifications.manage", "Gérer les notifications"),
    ]},
    {"key": "advertising", "label": "Publicité", "permissions": [
        ("advertising.view", "Voir les publicités"),
        ("advertising.manage", "Créer et gérer les publicités"),
    ]},
    {"key": "settings", "label": "Paramètres", "permissions": [
        ("settings.view", "Voir les paramètres"),
        ("settings.edit", "Modifier les paramètres"),
    ]},
]

GROUP_ORDER = [g["key"] for g in PERMISSION_GROUPS]
ALL_PERMISSION_CODENAMES = [code for g in PERMISSION_GROUPS for code, _ in g["permissions"]]

SUPER_ADMIN_SLUG = "super_admin"

# Rôles proposés au premier lancement (créés une seule fois, ensuite librement modifiables par le Super Admin).
PRESET_ROLES = [
    {
        "slug": "content_admin", "name": "Administrateur Contenu", "color": "blue",
        "description": "Gère les actualités. Aucun accès aux données financières ni aux candidats.",
        "permissions": ["news.view", "news.create", "news.edit", "news.publish", "partners.view", "partners.create", "partners.edit", "partners.delete", "categories.view", "media.view", "media.upload"],
    },
    {
        "slug": "candidates_admin", "name": "Administrateur Candidats", "color": "blue",
        "description": "Gère les fiches candidats, leurs photos et leur publication.",
        "permissions": ["candidates.view", "candidates.create", "candidates.edit", "candidates.publish", "categories.view", "media.view", "media.upload"],
    },
    {
        "slug": "competition_admin", "name": "Administrateur Compétition", "color": "blue",
        "description": "Gère la compétition, les candidats, les votes et les tarifs de billetterie.",
        "permissions": [
            "competition.view", "competition.edit", "competition.start", "competition.stop",
            "candidates.view", "candidates.create", "candidates.edit", "candidates.publish",
            "categories.view", "categories.create", "categories.edit", "categories.delete",
            "votes.view", "votes.statistics", "rankings.view",
            "tickets.manage", "tickets.statistics",
        ],
    },
    {
        "slug": "categories_admin", "name": "Administrateur Catégories", "color": "blue",
        "description": "Gère les catégories de la compétition.",
        "permissions": ["categories.view", "categories.create", "categories.edit", "categories.delete", "categories.publish"],
    },
    {
        "slug": "team_admin", "name": "Administrateur Équipe", "color": "blue",
        "description": "Gère l'équipe et les coachs affichés sur le site.",
        "permissions": ["team.view", "team.create", "team.edit", "team.delete", "media.view", "media.upload"],
    },
    {
        "slug": "finance_admin", "name": "Administrateur Financier", "color": "emerald",
        "description": "Consulte paiements, transactions, compte marchand et rapprochement. Aucun droit sur le contenu.",
        "permissions": [
            "payments.view", "payments.statistics", "payments.export", "merchant.view",
            "reconciliation.view", "votes.view", "votes.statistics", "rankings.view",
            "tickets.statistics",
        ],
    },
]
