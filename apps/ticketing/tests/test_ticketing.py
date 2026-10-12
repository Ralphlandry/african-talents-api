import pytest
from rest_framework_simplejwt.tokens import AccessToken

from apps.accounts.models import Permission, Role, User
from apps.payments.models import Payment
from apps.ticketing.models import TicketOrder, TicketType
from apps.voting.models import Vote

PUBLIC = "/api/v1/public"


class FakeGatewayClient:
    def __init__(self):
        self.status = {"status": "PENDING"}

    def create_mobile_money_payin(self, **kwargs):
        return {"status": "PENDING", "provider_reference": "HRS-TICKET-1"}

    def get_payment_status(self, reference):
        return self.status


@pytest.fixture
def ticket_type(make_competition):
    from apps.competition.models import Competition

    competition = Competition.objects.filter(is_current=True).first() or make_competition(is_current=True)
    competition.ticket_sales_open = True
    competition.save(update_fields=["ticket_sales_open"])
    return TicketType.objects.create(
        competition=competition,
        ticket_class=TicketType.CLASSIC,
        label="Billet classique",
        price_xaf=5000,
    )


@pytest.mark.django_db
def test_public_ticket_types_only_show_active_current_competition(api, ticket_type, make_competition):
    other_competition = make_competition(name="Autre", is_current=False)
    TicketType.objects.create(
        competition=ticket_type.competition,
        ticket_class=TicketType.VIP,
        label="Billet VIP",
        price_xaf=10000,
        is_active=False,
    )
    TicketType.objects.create(
        competition=other_competition,
        ticket_class=TicketType.CLASSIC,
        label="Ancien billet",
        price_xaf=3000,
    )

    response = api.get(f"{PUBLIC}/ticket-types/")

    assert response.status_code == 200
    assert [item["label"] for item in response.json()] == ["Billet classique"]


@pytest.mark.django_db
def test_ticket_sales_control_opens_and_closes_public_sales(
    api, ticket_type, make_role, make_user, auth_client
):
    from apps.competition.models import Competition

    competition = ticket_type.competition
    competition.ticket_sales_open = False
    competition.save(update_fields=["ticket_sales_open"])
    manager_role = make_role("Ticket Manager", perms=["tickets.manage"])
    manager = make_user("ticket-manager@example.com", manager_role)
    admin = auth_client(manager)
    control_url = "/api/v1/ticket-sales/control/"

    assert admin.get(control_url).json() == {
        "competition_id": str(competition.pk),
        "is_open": False,
    }
    assert api.get(f"{PUBLIC}/ticket-types/").json() == []
    closed_order = api.post(
        f"{PUBLIC}/ticket-orders/",
        {
            "ticket_type": str(ticket_type.pk),
            "first_name": "Amina",
            "last_name": "Njoya",
            "phone": "+237655500001",
            "operator": "MTN",
            "idempotency_key": "ticket-order-closed",
            "accept_terms": True,
        },
        format="json",
    )
    assert closed_order.status_code == 422
    assert not TicketOrder.objects.exists()

    opened = admin.post(control_url, {"is_open": True}, format="json")
    assert opened.status_code == 200
    assert opened.json()["is_open"] is True
    assert admin.get(control_url).json()["is_open"] is True
    assert [item["id"] for item in api.get(f"{PUBLIC}/ticket-types/").json()] == [str(ticket_type.pk)]

    closed = admin.post(control_url, {"is_open": False}, format="json")
    assert closed.status_code == 200
    assert closed.json()["is_open"] is False
    assert api.get(f"{PUBLIC}/ticket-types/").json() == []
    assert Competition.objects.get(pk=competition.pk).ticket_sales_open is False


@pytest.mark.django_db
def test_ticket_payment_confirmation_assigns_one_point_and_unlocks_pdf(
    api, monkeypatch, ticket_type, make_category, make_candidate, make_competition
):
    from apps.payments import services as payment_services

    competition = ticket_type.competition
    category = make_category(competition=competition)
    candidate = make_candidate(competition, category, code="AT-001")
    fake = FakeGatewayClient()
    monkeypatch.setattr(payment_services, "build_client_from_settings", lambda: fake)
    payload = {
        "ticket_type": str(ticket_type.pk),
        "first_name": "Amina",
        "last_name": "Njoya",
        "phone": "+237655500001",
        "operator": "MTN",
        "promo_code": "at-001",
        "idempotency_key": "ticket-order-flow-1",
        "accept_terms": True,
        "amount_xaf": 1,
    }

    created = api.post(f"{PUBLIC}/ticket-orders/", payload, format="json")
    assert created.status_code == 201
    order_number = created.json()["order_number"]
    order = TicketOrder.objects.get(order_number=order_number)
    assert order.amount_xaf == 5000
    assert order.ticket_code.startswith("AT-")
    assert len(order.ticket_code) == 15
    assert order.status == TicketOrder.PENDING
    assert order.promo_candidate == candidate
    assert not Vote.objects.exists()
    assert api.get(f"{PUBLIC}/ticket-orders/{order_number}/pdf/").status_code == 404

    fake.status = {"status": "SUCCESS", "amount_xaf": 5000, "currency": "XAF"}
    status = api.get(f"{PUBLIC}/ticket-orders/{order_number}/")

    order.refresh_from_db()
    payment = Payment.objects.get(ticket_order=order)
    assert status.status_code == 200
    assert status.json()["status"] == TicketOrder.PAID
    assert payment.status == Payment.SUCCESS
    assert not Vote.objects.exists()

    admin_role = Role.objects.create(name="Ticket Stats", slug="ticket-stats-test")
    admin_role.permissions.set(Permission.objects.filter(codename="tickets.statistics"))
    admin = User.objects.create_user("ticket-stats@example.com", "Str0ng-Pass-123!", role=admin_role)
    token = AccessToken.for_user(admin)
    stats = api.get("/api/v1/ticket-sales/statistics/", HTTP_AUTHORIZATION=f"Bearer {token}")
    assert stats.status_code == 200
    assert stats.json()["total_paid"] == 1
    assert stats.json()["candidates"][0]["points"] == 1

    pdf = api.get(f"{PUBLIC}/ticket-orders/{order_number}/pdf/")
    assert pdf.status_code == 200
    assert pdf["Content-Type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")
    assert order.ticket_code.encode() in pdf.content
    assert b"Amina Njoya" in pdf.content


@pytest.mark.django_db
def test_vip_ticket_pdf_includes_vip_access_benefits(api, monkeypatch, ticket_type):
    from reportlab.pdfgen.canvas import Canvas

    rendered_text = []
    draw_centred_string = Canvas.drawCentredString

    def track_drawn_text(pdf, x, y, text):
        rendered_text.append(text)
        return draw_centred_string(pdf, x, y, text)

    monkeypatch.setattr(Canvas, "drawCentredString", track_drawn_text)
    vip_type = TicketType.objects.create(
        competition=ticket_type.competition,
        ticket_class=TicketType.VIP,
        label="Billet VIP",
        price_xaf=10000,
    )
    order = TicketOrder.objects.create(
        ticket_type=vip_type,
        buyer_first_name="Amina",
        buyer_last_name="Njoya",
        customer_phone="+237655500001",
        amount_xaf=vip_type.price_xaf,
        operator="MTN",
        status=TicketOrder.PAID,
        idempotency_key="vip-ticket-pdf-benefits",
    )

    response = api.get(f"{PUBLIC}/ticket-orders/{order.order_number}/pdf/")
    assert response.status_code == 200
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")
    assert "PASS VIP" in rendered_text
    assert "VIP : PREMIÈRES PLACES · BOISSON · PHOTOS AVEC LA STAR" in rendered_text


@pytest.mark.django_db
def test_ticket_idempotency_reuses_order_and_rejects_changed_payload(api, monkeypatch, ticket_type):
    from apps.payments import services as payment_services

    monkeypatch.setattr(payment_services, "build_client_from_settings", lambda: FakeGatewayClient())
    payload = {
        "ticket_type": str(ticket_type.pk),
        "first_name": "Amina",
        "last_name": "Njoya",
        "phone": "+237655500001",
        "operator": "ORANGE",
        "idempotency_key": "ticket-order-repeat-1",
        "accept_terms": True,
    }

    first = api.post(f"{PUBLIC}/ticket-orders/", payload, format="json")
    retry = api.post(f"{PUBLIC}/ticket-orders/", payload, format="json")
    conflict = api.post(f"{PUBLIC}/ticket-orders/", {**payload, "phone": "+237655500002"}, format="json")

    assert first.status_code == 201
    assert retry.status_code == 200
    assert first.json()["order_number"] == retry.json()["order_number"]
    assert conflict.status_code == 409
    assert TicketOrder.objects.filter(idempotency_key="ticket-order-repeat-1").count() == 1
    assert Payment.objects.filter(ticket_order__idempotency_key="ticket-order-repeat-1").count() == 1
    other = api.post(
        f"{PUBLIC}/ticket-orders/",
        {**payload, "idempotency_key": "ticket-order-repeat-2"},
        format="json",
    )
    assert other.status_code == 201
    assert other.json()["order_number"] != first.json()["order_number"]
    first_code = TicketOrder.objects.get(order_number=first.json()["order_number"]).ticket_code
    other_code = TicketOrder.objects.get(order_number=other.json()["order_number"]).ticket_code
    assert first_code != other_code
