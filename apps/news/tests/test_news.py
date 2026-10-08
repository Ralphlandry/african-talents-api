import pytest
from django.utils import timezone

NEWS = "/api/v1/news/"


@pytest.mark.django_db
def test_create_draft_and_content_is_sanitized(auth_client, make_role, make_user):
    user = make_user("n@example.com", make_role("News", ["news.view", "news.create"]))
    response = auth_client(user).post(NEWS, {
        "title": "Lancement de la saison",
        "content_html": "<p>Bienvenue</p><script>alert(1)</script><img src=x onerror=alert(2)>",
    }, format="json")
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "draft"
    assert "<script>" not in body["content_html"]
    assert "onerror" not in body["content_html"]
    assert "<p>Bienvenue</p>" in body["content_html"]


@pytest.mark.django_db
def test_scheduling_requires_date_and_sets_status(auth_client, make_role, make_user):
    user = make_user("n@example.com", make_role("News", ["news.view", "news.create"]))
    client = auth_client(user)

    missing_date = client.post(NEWS, {"title": "X", "status": "scheduled"}, format="json")
    assert missing_date.status_code == 422

    future = (timezone.now() + timezone.timedelta(days=2)).isoformat()
    scheduled = client.post(NEWS, {"title": "Calendrier finale", "scheduled_at": future}, format="json")
    assert scheduled.status_code == 201 and scheduled.json()["status"] == "scheduled"


@pytest.mark.django_db
def test_publish_now_and_unpublish(auth_client, make_role, make_user):
    user = make_user("n@example.com", make_role("News", ["news.view", "news.create", "news.publish"]))
    client = auth_client(user)
    post_id = client.post(NEWS, {"title": "Article"}, format="json").json()["id"]

    published = client.post(f"{NEWS}{post_id}/publish/")
    assert published.status_code == 200 and published.json()["status"] == "published"
    assert published.json()["published_at"] is not None

    unpublished = client.post(f"{NEWS}{post_id}/unpublish/")
    assert unpublished.status_code == 200 and unpublished.json()["status"] == "draft"


@pytest.mark.django_db
def test_scheduled_task_publishes_due_posts():
    from apps.news.models import NewsPost
    from apps.news.services import publish_due_scheduled_posts

    past = NewsPost.objects.create(title="En retard", slug="en-retard", scheduled_at=timezone.now() - timezone.timedelta(minutes=5), status=NewsPost.SCHEDULED)
    future = NewsPost.objects.create(title="Plus tard", slug="plus-tard", scheduled_at=timezone.now() + timezone.timedelta(days=1), status=NewsPost.SCHEDULED)

    count = publish_due_scheduled_posts()
    assert count == 1
    past.refresh_from_db()
    future.refresh_from_db()
    assert past.status == NewsPost.PUBLISHED
    assert future.status == NewsPost.SCHEDULED


@pytest.mark.django_db
def test_bulk_delete_news(auth_client, make_role, make_user):
    user = make_user("n@example.com", make_role("News", ["news.view", "news.create", "news.delete"]))
    client = auth_client(user)
    ids = [client.post(NEWS, {"title": f"Art {i}"}, format="json").json()["id"] for i in range(2)]
    response = client.post(f"{NEWS}bulk-delete/", {"ids": ids}, format="json")
    assert response.status_code == 200 and response.json()["deleted"] == 2
