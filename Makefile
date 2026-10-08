DC = docker compose

.PHONY: up down logs migrations migrate seed superuser test shell fmt

up:            ## Démarre tout (dev) : db, redis, api, worker, beat
	$(DC) up --build

down:
	$(DC) down

logs:
	$(DC) logs -f backend

migrations:    ## Génère les fichiers de migration (à committer)
	$(DC) run --rm -e RUN_MIGRATIONS=0 backend python manage.py makemigrations

migrate:
	$(DC) run --rm -e AUTO_MAKEMIGRATIONS=0 backend python manage.py migrate

seed:          ## Rôles prédéfinis (Contenu, Candidats, Catégories, Équipe, Financier)
	$(DC) exec backend python manage.py seed_rbac

seed-demo:     ## Jeu de données de démo complet (admins, compétition, candidats, votes, actualités...)
	$(DC) exec backend python manage.py seed_demo

superuser:     ## Crée le premier Super Administrateur (mot de passe saisi au clavier)
	$(DC) exec backend python manage.py createsuperuser

test:          ## Lance la suite de tests (génère d'abord les migrations si absentes)
	$(DC) run --rm -e AUTO_MAKEMIGRATIONS=1 -e RUN_MIGRATIONS=0 backend pytest

shell:
	$(DC) exec backend python manage.py shell
