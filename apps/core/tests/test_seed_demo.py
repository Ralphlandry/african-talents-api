import pytest
from django.core.management import call_command


@pytest.mark.django_db
def test_seed_demo_creates_expected_data():
    call_command("seed_demo", "--force")

    from apps.accounts.models import User
    from apps.candidates.models import Candidate
    from apps.categories.models import Category
    from apps.competition.models import Competition
    from apps.news.models import NewsPost
    from apps.payments.models import Payment
    from apps.team.models import TeamMember
    from apps.voting.models import Vote, VotePackage

    assert Competition.objects.filter(is_current=True).count() == 1
    assert Category.objects.count() == 5
    assert Candidate.objects.count() == 10
    assert VotePackage.objects.count() == 3
    assert Vote.objects.exists()
    assert NewsPost.objects.count() == 4
    assert TeamMember.objects.count() == 4
    assert Payment.objects.count() == 3
    assert User.objects.filter(email="super.admin@demo.africantalents.africa").exists()


@pytest.mark.django_db
def test_seed_demo_login_works_with_documented_password(api):
    call_command("seed_demo", "--force")

    response = api.post(
        "/api/v1/auth/login/",
        {"email": "super.admin@demo.africantalents.africa", "password": "demo1234!"},
        format="json",
    )
    assert response.status_code == 200
    assert response.json()["user"]["permissions"] == ["*"]


@pytest.mark.django_db
def test_seed_demo_is_idempotent():
    from apps.candidates.models import Candidate
    from apps.competition.models import Competition
    from apps.voting.models import Vote

    call_command("seed_demo", "--force")
    first_candidates = Candidate.objects.count()
    first_votes = Vote.objects.count()
    first_competitions = Competition.objects.count()

    call_command("seed_demo", "--force")  # rejoué : ne doit rien dupliquer
    assert Candidate.objects.count() == first_candidates
    assert Vote.objects.count() == first_votes  # le ledger n'est semé qu'une fois (classement stable)
    assert Competition.objects.count() == first_competitions


@pytest.mark.django_db
def test_seed_demo_refuses_to_run_without_debug_or_force(settings):
    from django.core.management.base import CommandError

    settings.DEBUG = False
    with pytest.raises(CommandError):
        call_command("seed_demo")
