import pytest

PUBLIC = "/api/v1/public"


@pytest.mark.django_db
def test_public_endpoints_need_no_authentication(api):
    assert api.get(f"{PUBLIC}/categories/").status_code == 200
    assert api.get(f"{PUBLIC}/candidates/").status_code == 200
    assert api.get(f"{PUBLIC}/news/").status_code == 200
    assert api.get(f"{PUBLIC}/team/").status_code == 200
    assert api.get(f"{PUBLIC}/site/").status_code == 200


@pytest.mark.django_db
def test_current_competition_only(api, make_competition):
    make_competition(name="Ancienne", is_current=False)
    make_competition(name="Actuelle", is_current=True)
    response = api.get(f"{PUBLIC}/competition/")
    assert response.status_code == 200 and response.json()["name"] == "Actuelle"


@pytest.mark.django_db
def test_no_current_competition_returns_null_not_error(api):
    response = api.get(f"{PUBLIC}/competition/")
    assert response.status_code == 200 and response.json() is None


@pytest.mark.django_db
def test_only_published_active_candidates_are_public(api, make_competition, make_category, make_candidate):
    competition = make_competition()
    category = make_category(competition=competition)
    visible = make_candidate(competition, category, code="AT-001", status="published", is_active=True)
    make_candidate(competition, category, code="AT-002", status="draft", is_active=True)
    make_candidate(competition, category, code="AT-003", status="published", is_active=False)

    response = api.get(f"{PUBLIC}/candidates/")
    codes = [c["code"] for c in response.json()["results"]]
    assert codes == ["AT-001"]

    detail = api.get(f"{PUBLIC}/candidates/{visible.slug}/")
    assert detail.status_code == 200 and detail.json()["display_name"] == "Dupont Jean"


@pytest.mark.django_db
def test_unpublished_candidate_detail_is_404(api, make_competition, make_category, make_candidate):
    competition = make_competition()
    category = make_category(competition=competition)
    draft = make_candidate(competition, category, status="draft", is_active=True)
    assert api.get(f"{PUBLIC}/candidates/{draft.slug}/").status_code == 404


@pytest.mark.django_db
def test_only_published_news_are_public(api):
    from apps.news.models import NewsPost

    NewsPost.objects.create(title="Publié", slug="publie", status=NewsPost.PUBLISHED)
    NewsPost.objects.create(title="Brouillon", slug="brouillon", status=NewsPost.DRAFT)
    response = api.get(f"{PUBLIC}/news/").json()
    assert [n["title"] for n in response["results"]] == ["Publié"]


@pytest.mark.django_db
def test_only_visible_team_members_are_public(api):
    from apps.team.models import TeamMember

    TeamMember.objects.create(type="coach", full_name="Visible", is_visible=True, order=1)
    TeamMember.objects.create(type="coach", full_name="Caché", is_visible=False, order=2)
    response = api.get(f"{PUBLIC}/team/").json()
    assert [m["full_name"] for m in response] == ["Visible"]


@pytest.mark.django_db
def test_public_team_members_follow_configured_order(api):
    from apps.team.models import TeamMember

    TeamMember.objects.create(type="team", full_name="Troisième", order=3)
    TeamMember.objects.create(type="team", full_name="Premier", order=1)
    TeamMember.objects.create(type="team", full_name="Deuxième", order=2)

    response = api.get(f"{PUBLIC}/team/").json()
    assert [member["full_name"] for member in response] == ["Premier", "Deuxième", "Troisième"]


@pytest.mark.django_db
def test_candidates_filterable_by_category(api, make_competition, make_category, make_candidate):
    competition = make_competition()
    music = make_category("Musique", competition=competition)
    art = make_category("Arts Visuels", competition=competition)
    make_candidate(competition, music, code="AT-001")
    make_candidate(competition, art, code="AT-002")

    response = api.get(f"{PUBLIC}/candidates/?category=musique").json()
    assert [c["code"] for c in response["results"]] == ["AT-001"]
