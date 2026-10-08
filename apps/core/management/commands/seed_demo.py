"""
Jeu de données de démonstration pour tester l'admin et le site public sans tout
créer à la main. Idempotent (peut être relancé sans tout dupliquer) et refuse de
s'exécuter hors DEBUG (jamais de mots de passe de démo connus en production).

Usage : python manage.py seed_demo
"""
import io
import random
import uuid
from datetime import timedelta

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.accounts.models import Role, User
from apps.accounts.rbac import seed_preset_roles, sync_rbac
from apps.candidates.models import Candidate
from apps.categories.models import Category
from apps.competition.models import Competition, Phase
from apps.core.models import SiteSettings
from apps.media.models import MediaAsset
from apps.news.models import NewsPost
from apps.payments.models import Payment
from apps.team.models import TeamMember
from apps.voting.models import Vote, VoteOrder, VotePackage

DEMO_PASSWORD = "demo1234!"


def _placeholder_image(label: str, color: tuple) -> ContentFile:
    """Génère un petit PNG de couleur unie (évite de dépendre de vrais fichiers média)."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (480, 480), color=color)
    draw = ImageDraw.Draw(img)
    draw.text((20, 220), label[:28], fill=(255, 255, 255))
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=70)
    return ContentFile(buffer.getvalue(), name=f"{slugify(label)}-{uuid.uuid4().hex[:6]}.jpg")


class Command(BaseCommand):
    help = "Crée un jeu de données de démonstration complet (admins, compétition, candidats, votes, actualités...)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force", action="store_true",
            help="Autorise l'exécution même si DEBUG=False (déconseillé — mots de passe de démo connus).",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError(
                "Refus de semer des données de démonstration hors DEBUG (mots de passe connus : "
                f"{DEMO_PASSWORD!r}). Relancez avec --force si vous savez ce que vous faites."
            )

        with transaction.atomic():
            sync_rbac()
            seed_preset_roles()
            admins = self._seed_admins()
            competition, phases = self._seed_competition()
            categories = self._seed_categories(competition)
            media = self._seed_media(admins["super"])
            candidates = self._seed_candidates(competition, categories, media)
            packages = self._seed_vote_packages(competition)
            self._seed_votes_and_payments(candidates, packages, phases)
            self._seed_news(competition, categories, media, admins)
            self._seed_team(media)
            self._seed_site_settings(media)

        self.stdout.write(self.style.SUCCESS("Jeu de données de démonstration prêt."))
        self.stdout.write(f"Comptes admin (mot de passe pour tous : {DEMO_PASSWORD}) :")
        for email, role in [
            ("super.admin@demo.africantalents.africa", "Super Administrateur"),
            ("contenu@demo.africantalents.africa", "Administrateur Contenu"),
            ("candidats@demo.africantalents.africa", "Administrateur Candidats"),
            ("finance@demo.africantalents.africa", "Administrateur Financier"),
        ]:
            self.stdout.write(f"  - {email}  ({role})")

    # -- Comptes administrateurs --------------------------------------------
    def _seed_admins(self):
        super_role = Role.objects.get(slug="super_admin")
        super_user, super_created = User.objects.get_or_create(
            email="super.admin@demo.africantalents.africa",
            defaults={"full_name": "Aïcha Ndiaye", "role": super_role, "is_active": True},
        )
        if super_created or not super_user.has_usable_password():
            super_user.set_password(DEMO_PASSWORD)
            super_user.save(update_fields=["password"])

        pairs = [
            ("contenu@demo.africantalents.africa", "Junior Mbarga", "content_admin"),
            ("candidats@demo.africantalents.africa", "Grace Owusu", "candidates_admin"),
            ("finance@demo.africantalents.africa", "Patricia Fotso", "finance_admin"),
        ]
        for email, name, role_slug in pairs:
            role = Role.objects.filter(slug=role_slug).first()
            if role is None:
                continue
            user, created = User.objects.get_or_create(email=email, defaults={"full_name": name, "role": role})
            if created or not user.has_usable_password():
                user.set_password(DEMO_PASSWORD)
                user.save(update_fields=["password"])
        return {"super": super_user}

    # -- Compétition -----------------------------------------------------------
    def _seed_competition(self):
        today = timezone.localdate()
        competition, _ = Competition.objects.update_or_create(
            slug="saison-2026",
            defaults={
                "name": "African Talents — Saison 2026",
                "description": "Compétition continentale valorisant les talents africains dans cinq catégories.",
                "start_date": today - timedelta(days=90),
                "end_date": today + timedelta(days=90),
                "status": Competition.ACTIVE,
                "votes_open": True,
                "is_current": True,
            },
        )
        Competition.objects.exclude(pk=competition.pk).update(is_current=False)

        phase_defs = [
            ("Sélection", 1, -90, -60, Phase.ENDED),
            ("Votes", 2, -59, 60, Phase.ACTIVE),
            ("Finale", 3, 61, 75, Phase.SELECTION),
            ("Résultats", 4, 80, 90, Phase.SELECTION),
        ]
        phases = {}
        for name, order, start_offset, end_offset, status in phase_defs:
            phase, _ = Phase.objects.update_or_create(
                competition=competition, order=order,
                defaults={
                    "name": name, "start_date": today + timedelta(days=start_offset),
                    "end_date": today + timedelta(days=end_offset), "status": status,
                },
            )
            phases[name] = phase
        return competition, phases

    # -- Catégories --------------------------------------------------------
    def _seed_categories(self, competition):
        defs = [
            ("Musique", "music", "Chant, composition et performance musicale."),
            ("Mode & Design", "shirt", "Stylisme, création et mise en scène de mode."),
            ("Entrepreneuriat", "briefcase", "Initiatives entrepreneuriales à impact."),
            ("Arts Visuels", "palette", "Peinture, sculpture, photographie et arts numériques."),
            ("Sport", "trophy", "Talents sportifs émergents."),
        ]
        categories = {}
        for i, (name, icon, description) in enumerate(defs, start=1):
            category, _ = Category.objects.update_or_create(
                competition=competition, slug=slugify(name),
                defaults={"name": name, "description": description, "icon": icon, "order": i, "status": Category.PUBLISHED},
            )
            categories[name] = category
        return categories

    # -- Médias (placeholders générés, pas de vrais fichiers à fournir) -----
    def _seed_media(self, uploader):
        palette = [(11, 30, 77), (201, 162, 39), (27, 58, 128), (132, 99, 21), (30, 142, 90)]
        media = {}
        for i, label in enumerate(["candidate-1", "candidate-2", "candidate-3", "news-1", "team-1"]):
            asset, created = MediaAsset.objects.get_or_create(
                original_name=f"{label}.jpg",
                defaults={
                    "kind": MediaAsset.KIND_IMAGE, "mime_type": "image/jpeg", "size_bytes": 20_000,
                    "usage": "demo", "uploaded_by": uploader,
                },
            )
            if created or not asset.file:
                asset.file.save(f"{label}.jpg", _placeholder_image(label, palette[i % len(palette)]), save=True)
            media[label] = asset
        return media

    # -- Candidats -----------------------------------------------------------
    def _seed_candidates(self, competition, categories, media):
        defs = [
            ("AT-001", "Aminata", "Diallo", "Musique", "Conakry", "Guinée", "Chanteuse, mélange afrobeat et sonorités mandingues."),
            ("AT-002", "Kwame", "Asante", "Entrepreneuriat", "Kumasi", "Ghana", "Fondateur d'une plateforme agri-tech pour petits producteurs."),
            ("AT-003", "Fatou", "Cissé", "Mode & Design", "Dakar", "Sénégal", "Styliste, fusionne tissus traditionnels et coupes contemporaines."),
            ("AT-004", "Chidi", "Okafor", "Arts Visuels", "Lagos", "Nigéria", "Peintre figuratif explorant la mémoire diasporique."),
            ("AT-005", "Naledi", "Mokoena", "Musique", "Johannesburg", "Afrique du Sud", "Compositrice et violoniste, jazz sud-africain."),
            ("AT-006", "Grace", "Mwangi", "Entrepreneuriat", "Nairobi", "Kenya", "Coopérative de recyclage textile."),
            ("AT-007", "Ismaël", "Traoré", "Arts Visuels", "Bamako", "Mali", "Photographe documentaire, villes ouest-africaines."),
            ("AT-008", "Zainab", "Abubakar", "Mode & Design", "Kano", "Nigéria", "Designer textile, broderie hausa réinventée."),
            ("AT-009", "Junior", "Ngoma", "Musique", "Kinshasa", "RD Congo", "Rappeur et slameur engagé."),
            ("AT-010", "Thabo", "Nkosi", "Arts Visuels", "Durban", "Afrique du Sud", "Sculpteur sur métal, pièces monumentales urbaines."),
        ]
        photo_keys = ["candidate-1", "candidate-2", "candidate-3"]
        candidates = {}
        for i, (code, first, last, cat_name, city, country, bio) in enumerate(defs):
            candidate, _ = Candidate.objects.update_or_create(
                competition=competition, code=code,
                defaults={
                    "category": categories[cat_name], "first_name": first, "last_name": last,
                    "slug": slugify(f"{first}-{last}-{code}"), "bio": bio, "city": city, "country": country,
                    "photo": media[photo_keys[i % len(photo_keys)]], "status": Candidate.PUBLISHED, "is_active": True,
                },
            )
            candidates[code] = candidate
        return candidates

    # -- Forfaits de vote (décision B : définis ici comme un admin le ferait) ---
    def _seed_vote_packages(self, competition):
        defs = [("10 votes", 10, 1000), ("50 votes", 50, 4500), ("100 votes", 100, 8000)]
        packages = []
        for i, (label, quantity, price) in enumerate(defs, start=1):
            package, _ = VotePackage.objects.update_or_create(
                competition=competition, label=label,
                defaults={"quantity": quantity, "price_xaf": price, "is_active": True, "order": i},
            )
            packages.append(package)
        return packages

    # -- Votes (ledger) + quelques paiements d'exemple pour les écrans finance --
    def _seed_votes_and_payments(self, candidates, packages, phases):
        random.seed(42)  # résultats reproductibles d'une exécution à l'autre
        vote_phase = phases.get("Votes")

        if Vote.objects.exists():
            return  # déjà semé : on ne regénère pas un classement différent à chaque run

        for candidate in candidates.values():
            for _ in range(random.randint(2, 6)):
                Vote.objects.create(
                    candidate=candidate, phase=vote_phase, quantity=random.randint(5, 80), source=Vote.PAID,
                )

        # Quelques commandes/paiements d'exemple pour peupler les écrans Paiements/Transactions.
        sample_candidates = list(candidates.values())[:3]
        for i, candidate in enumerate(sample_candidates):
            package = packages[i % len(packages)]
            order = VoteOrder.objects.create(
                candidate=candidate, vote_package=package, phase=vote_phase,
                quantity=package.quantity, amount_xaf=package.price_xaf,
                customer_phone=f"+23765550000{i}", operator="MTN" if i % 2 == 0 else "ORANGE",
                status=[VoteOrder.PAID, VoteOrder.PENDING, VoteOrder.FAILED][i % 3],
                idempotency_key=f"demo-seed-{i}",
            )
            Payment.objects.create(
                vote_order=order, reference=order.order_number, environment="test",
                amount_xaf=order.amount_xaf, phone=order.customer_phone, operator=order.operator,
                status={"PAID": Payment.SUCCESS, "PENDING": Payment.PENDING, "FAILED": Payment.FAILED}[order.status],
                confirmed_at=timezone.now() if order.status != VoteOrder.PENDING else None,
            )
            if order.status == VoteOrder.PAID:
                # Garde la même invariante que le vrai flux (apps.voting.services.credit_paid_order) :
                # un paiement SUCCESS a toujours exactement un Vote lié via vote_order.
                Vote.objects.create(candidate=candidate, phase=vote_phase, quantity=order.quantity, source=Vote.PAID, vote_order=order)

    # -- Actualités ----------------------------------------------------------
    def _seed_news(self, competition, categories, media, admins):
        defs = [
            ("Lancement officiel de la saison 2026", "Les candidatures sont ouvertes pour la cinquième édition.", NewsPost.PUBLISHED, -80),
            ("Les votes sont ouverts !", "Le public peut désormais soutenir ses candidats favoris.", NewsPost.PUBLISHED, -59),
            ("Calendrier de la phase finale", "Toutes les dates clés de la finale continentale.", NewsPost.SCHEDULED, 30),
            ("Coulisses du tournage des portraits", "Retour sur la semaine de captation à Dakar.", NewsPost.DRAFT, None),
        ]
        today = timezone.now()
        for title, excerpt, status, offset in defs:
            NewsPost.objects.update_or_create(
                slug=slugify(title),
                defaults={
                    "title": title, "excerpt": excerpt, "content_html": f"<p>{excerpt}</p>",
                    "main_image": media.get("news-1"), "category": random.choice(list(categories.values())),
                    "author": admins["super"], "status": status,
                    "published_at": today + timedelta(days=offset) if status == NewsPost.PUBLISHED else None,
                    "scheduled_at": today + timedelta(days=offset) if status == NewsPost.SCHEDULED else None,
                },
            )

    # -- Équipe & coachs -------------------------------------------------------
    def _seed_team(self, media):
        defs = [
            (TeamMember.COACH, "Mariam Koné", "Coach chant"),
            (TeamMember.COACH, "David Mensah", "Coach stylisme"),
            (TeamMember.TEAM, "Samuel Biya", "Responsable partenariats"),
            (TeamMember.TEAM, "Linda Abena", "Coordinatrice logistique"),
        ]
        for i, (kind, name, role_title) in enumerate(defs, start=1):
            TeamMember.objects.update_or_create(
                full_name=name, type=kind,
                defaults={"role_title": role_title, "photo": media.get("team-1"), "order": i, "is_visible": True},
            )

    # -- Paramètres du site ----------------------------------------------------
    def _seed_site_settings(self, media):
        settings_obj = SiteSettings.load()
        settings_obj.site_name = "African Talents"
        settings_obj.tagline = "La plate-forme où vous êtes impactés pour impacter"
        settings_obj.description = "Plateforme continentale de compétition et de valorisation des talents africains."
        settings_obj.contact_phone = "+237 6 90 00 00 00"
        settings_obj.contact_email = "contact@africantalents.africa"
        settings_obj.contact_address = "Douala, Cameroun"
        settings_obj.facebook_url = "https://facebook.com/africantalents"
        settings_obj.instagram_url = "https://instagram.com/africantalents"
        settings_obj.tiktok_url = "https://tiktok.com/@africantalents"
        settings_obj.stats = [
            {"label": "Talents", "value": "300"}, {"label": "Domaines", "value": "5"},
            {"label": "Finalistes", "value": "12"}, {"label": "Pays", "value": "20"},
        ]
        settings_obj.save()
