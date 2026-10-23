import math
from io import BytesIO
from pathlib import Path

from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.text import slugify
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from rest_framework import serializers, viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.candidates.models import Candidate
from apps.competition.models import Competition
from apps.core.exceptions import ServiceUnavailableError
from apps.core.permissions import RBACPermission
from apps.core.throttles import VoteOrderRateThrottle
from apps.payments.models import Payment
from apps.payments.services import initiate_payment, refresh_pending_payment

from .models import TicketOrder, TicketType
from .serializers import (
    PublicTicketTypeSerializer,
    TicketOrderCreateSerializer,
    TicketOrderStatusSerializer,
    TicketTypeSerializer,
)
from .services import create_ticket_order, set_ticket_sales_open


class TicketSalesControlSerializer(serializers.Serializer):
    is_open = serializers.BooleanField()


@extend_schema(tags=["ticketing"])
class TicketSalesControlView(APIView):
    permission_classes = [RBACPermission]
    permission_map = {"GET": "tickets.manage", "POST": "tickets.manage"}

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        competition = Competition.objects.filter(is_current=True).first()
        return Response({
            "competition_id": str(competition.pk) if competition else None,
            "is_open": bool(competition and competition.ticket_sales_open),
        })

    @extend_schema(request=TicketSalesControlSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        serializer = TicketSalesControlSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        competition = Competition.objects.filter(is_current=True).first()
        if competition is None:
            return Response({"detail": "Aucune compétition en cours n’est configurée."}, status=404)
        competition = set_ticket_sales_open(
            competition_id=competition.pk,
            is_open=serializer.validated_data["is_open"],
            actor=request.user,
            request=request,
        )
        return Response({
            "competition_id": str(competition.pk),
            "is_open": competition.ticket_sales_open,
        })


def _draw_star(pdf, x, y, radius, color):
    path = pdf.beginPath()
    for point in range(10):
        angle = point * math.pi / 5 - math.pi / 2
        distance = radius if point % 2 == 0 else radius * 0.42
        px, py = x + distance * math.cos(angle), y + distance * math.sin(angle)
        if point == 0:
            path.moveTo(px, py)
        else:
            path.lineTo(px, py)
    path.close()
    pdf.setFillColor(color)
    pdf.drawPath(path, fill=1, stroke=0)


def _basic_ticket_pdf(order):
    template_path = Path(__file__).resolve().parent / "assets" / "ticket-basic-template.png"
    template = ImageReader(str(template_path))
    image_width, image_height = template.getSize()
    width = 320 * mm
    image_display_height = width * image_height / image_width
    footer_height = 25 * mm
    height = image_display_height + footer_height
    scale = width / image_width
    output = BytesIO()
    pdf = canvas.Canvas(output, pagesize=(width, height), pageCompression=0)
    pdf.setTitle(f"Billet African Talents - {order.ticket_code}")
    pdf.setAuthor("African Talents")
    pdf.setFillColor(colors.HexColor("#030817"))
    pdf.rect(0, 0, width, height, fill=1, stroke=0)
    pdf.drawImage(template, 0, footer_height, width=width, height=image_display_height)

    weekdays = ("Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim")
    months = ("janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc.")
    event_date = order.ticket_type.competition.start_date
    date_label = f"{weekdays[event_date.weekday()]} {event_date.day} {months[event_date.month - 1]}"
    event_label = f"{date_label} · 15 H · À la salle ARENA Bonamoussadi, Douala"
    pdf.setFillColor(colors.HexColor("#050D2B"))
    pdf.rect(87 * scale, footer_height + 31 * scale, 475 * scale, 25 * scale, fill=1, stroke=0)
    pdf.setFillColor(colors.HexColor("#FFF9E9"))
    pdf.setFont("Helvetica-Bold", 7)
    pdf.drawCentredString(325 * scale, footer_height + 39 * scale, event_label)

    pdf.setFillColor(colors.HexColor("#030A20"))
    pdf.rect(564 * scale, footer_height, 74 * scale, image_display_height, fill=1, stroke=0)
    pdf.saveState()
    pdf.translate(601 * scale, footer_height + image_display_height / 2)
    pdf.rotate(90)
    pdf.setFillColor(colors.HexColor("#FFF9E9"))
    pdf.setFont("Helvetica-Bold", 9)
    pass_label = f"PASS BASIC · {order.amount_xaf:,}".replace(",", " ") + " FCFA"
    pdf.drawCentredString(0, 0, pass_label)
    pdf.restoreState()

    pdf.setStrokeColor(colors.HexColor("#E5B83F"))
    pdf.setLineWidth(1)
    pdf.line(0, footer_height, width, footer_height)
    pdf.setFillColor(colors.HexColor("#E5B83F"))
    pdf.setFont("Helvetica-Bold", 7)
    pdf.drawString(8 * mm, 18 * mm, "TITULAIRE")
    holder_name = f"{order.buyer_first_name} {order.buyer_last_name}"
    pdf.setFillColor(colors.HexColor("#FFF9E9"))
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(8 * mm, 11 * mm, holder_name[:52])
    pdf.setFillColor(colors.HexColor("#E5B83F"))
    pdf.setFont("Helvetica-Bold", 7)
    pdf.drawString(105 * mm, 18 * mm, "NUMÉRO UNIQUE")
    pdf.setFillColor(colors.HexColor("#FFF9E9"))
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(105 * mm, 11 * mm, order.ticket_code)
    pdf.setFillColor(colors.HexColor("#E5B83F"))
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawCentredString(202 * mm, 11 * mm, "ACCÈS À LA SALLE")
    qr = QrCodeWidget(order.ticket_code)
    qr.barLevel = "M"
    qr_bounds = qr.getBounds()
    qr_size = 18 * mm
    qr_drawing = Drawing(qr_size, qr_size, transform=[
        qr_size / (qr_bounds[2] - qr_bounds[0]), 0, 0,
        qr_size / (qr_bounds[3] - qr_bounds[1]), 0, 0,
    ])
    qr_drawing.add(qr, name="ticket-code")
    renderPDF.draw(qr_drawing, pdf, width - 23 * mm, 3 * mm)

    pdf.showPage()
    pdf.save()
    return output.getvalue()


def _classic_ticket_pdf(order):
    template_path = Path(__file__).resolve().parent / "assets" / "ticket-classic-template.png"
    template = ImageReader(str(template_path))
    image_width, image_height = template.getSize()
    width = 320 * mm
    image_display_height = width * image_height / image_width
    footer_height = 20 * mm
    height = image_display_height + footer_height
    scale = width / image_width
    output = BytesIO()
    pdf = canvas.Canvas(output, pagesize=(width, height), pageCompression=0)
    pdf.setTitle(f"Billet African Talents - {order.ticket_code}")
    pdf.setAuthor("African Talents")
    pdf.setFillColor(colors.HexColor("#030817"))
    pdf.rect(0, 0, width, height, fill=1, stroke=0)
    pdf.drawImage(template, 0, footer_height, width=width, height=image_display_height)

    pass_name = "PASS BASIC" if order.ticket_type.ticket_class == TicketType.BASIC else "PASS STANDARD"
    if order.ticket_type.ticket_class == TicketType.BASIC:
        pass_name += f" · {order.amount_xaf:,}".replace(",", " ") + " FCFA"
    pdf.setFillColor(colors.HexColor("#030A20"))
    pdf.rect(948 * scale, footer_height, 128 * scale, image_display_height, fill=1, stroke=0)
    pdf.saveState()
    pdf.translate(1012 * scale, footer_height + image_display_height / 2)
    pdf.rotate(90)
    pdf.setFillColor(colors.HexColor("#FFF9E9"))
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawCentredString(0, 0, pass_name)
    pdf.restoreState()

    event_date = order.ticket_type.competition.start_date
    weekdays = ("Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim")
    months = ("janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc.")
    date_label = f"{weekdays[event_date.weekday()]} {event_date.day} {months[event_date.month - 1]}"
    event_label = f"{date_label} · 15 H · ARENA Bonamoussadi, Douala"

    pdf.setFillColor(colors.HexColor("#050D2B"))
    pdf.rect(145 * scale, footer_height + 48 * scale, 720 * scale, 50 * scale, fill=1, stroke=0)
    pdf.setFillColor(colors.HexColor("#E5B83F"))
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawCentredString(505 * scale, footer_height + 66 * scale, event_label)

    pdf.setFillColor(colors.HexColor("#030A20"))
    pdf.rect(1080 * scale, footer_height, 192 * scale, image_display_height, fill=1, stroke=0)
    pdf.setStrokeColor(colors.HexColor("#E5B83F"))
    pdf.setLineWidth(1)
    pdf.line(1080 * scale, footer_height, 1080 * scale, height)
    pdf.saveState()
    pdf.translate(1123 * scale, footer_height + image_display_height / 2)
    pdf.rotate(90)
    pdf.setFillColor(colors.HexColor("#FFF9E9"))
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawCentredString(0, 0, "NUMÉRO UNIQUE")
    pdf.restoreState()
    pdf.saveState()
    pdf.translate(1208 * scale, footer_height + image_display_height / 2)
    pdf.rotate(90)
    pdf.setFillColor(colors.HexColor("#E5B83F"))
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawCentredString(0, 0, order.ticket_code)
    pdf.restoreState()

    pdf.setStrokeColor(colors.HexColor("#E5B83F"))
    pdf.setLineWidth(1)
    pdf.line(0, footer_height, width, footer_height)
    pdf.setFillColor(colors.HexColor("#E5B83F"))
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawCentredString(width / 2, 13 * mm, "ACCÈS À LA SALLE")
    pdf.drawCentredString(width / 2, 5 * mm, "BOISSON INCLUSE")

    pdf.showPage()
    pdf.save()
    return output.getvalue()


def _vip_ticket_pdf(order):
    template_path = Path(__file__).resolve().parent / "assets" / "ticket-vip-template.png"
    template = ImageReader(str(template_path))
    image_width, image_height = template.getSize()
    width = 320 * mm
    image_display_height = width * image_height / image_width
    footer_height = 22 * mm
    height = image_display_height + footer_height
    scale = width / image_width
    output = BytesIO()
    pdf = canvas.Canvas(output, pagesize=(width, height), pageCompression=0)
    pdf.setTitle(f"Billet African Talents - {order.ticket_code}")
    pdf.setAuthor("African Talents")
    pdf.setFillColor(colors.HexColor("#030817"))
    pdf.rect(0, 0, width, height, fill=1, stroke=0)
    pdf.drawImage(template, 0, footer_height, width=width, height=image_display_height)

    pdf.setFillColor(colors.HexColor("#030A20"))
    pdf.rect(947 * scale, footer_height, 220 * scale, image_display_height, fill=1, stroke=0)
    pdf.saveState()
    pdf.translate(1057 * scale, footer_height + image_display_height / 2)
    pdf.rotate(90)
    pdf.setFillColor(colors.HexColor("#FFF9E9"))
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawCentredString(0, 0, "PASS PREMIUM")
    pdf.restoreState()

    event_date = order.ticket_type.competition.start_date
    weekdays = ("Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim")
    months = ("janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc.")
    date_label = f"{weekdays[event_date.weekday()]} {event_date.day} {months[event_date.month - 1]}"
    event_label = f"{date_label} · 15 H · À la salle ARENA Bonamoussadi, Douala"

    pdf.setFillColor(colors.HexColor("#050D2B"))
    pdf.rect(65 * scale, footer_height + 48 * scale, 900 * scale, 50 * scale, fill=1, stroke=0)
    pdf.setFillColor(colors.HexColor("#FFF9E9"))
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawCentredString(515 * scale, footer_height + 66 * scale, event_label)

    pdf.setFillColor(colors.HexColor("#030A20"))
    pdf.rect(1170 * scale, footer_height, 101 * scale, image_display_height, fill=1, stroke=0)
    pdf.setStrokeColor(colors.HexColor("#E5B83F"))
    pdf.setLineWidth(1)
    pdf.line(1170 * scale, footer_height, 1170 * scale, height)
    pdf.saveState()
    pdf.translate(1218 * scale, footer_height + image_display_height / 2)
    pdf.rotate(90)
    pdf.setFillColor(colors.HexColor("#E5B83F"))
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawCentredString(0, 0, order.ticket_code)
    pdf.restoreState()

    pdf.setStrokeColor(colors.HexColor("#E5B83F"))
    pdf.setLineWidth(1)
    pdf.line(0, footer_height, width, footer_height)
    pdf.setFillColor(colors.HexColor("#E5B83F"))
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawCentredString(width / 2, 14 * mm, "ACCÈS À LA SALLE · BOISSON INCLUSE")
    pdf.drawCentredString(width / 2, 7 * mm, "PREMIÈRES PLACES · PHOTO AVEC LES STARS")

    pdf.showPage()
    pdf.save()
    return output.getvalue()


def _ticket_pdf(order):
    if order.ticket_type.ticket_class == TicketType.BASIC:
        return _basic_ticket_pdf(order)
    if order.ticket_type.ticket_class == TicketType.STANDARD:
        return _classic_ticket_pdf(order)
    if order.ticket_type.ticket_class == TicketType.PREMIUM:
        return _vip_ticket_pdf(order)

    width, height = 260 * mm, 105 * mm
    gold = colors.HexColor("#E5B83F")
    pale_gold = colors.HexColor("#F8D982")
    navy = colors.HexColor("#050D2B")
    panel = colors.HexColor("#071538")
    dark = colors.HexColor("#030817")
    white = colors.HexColor("#FFF9E9")
    output = BytesIO()
    pdf = canvas.Canvas(output, pagesize=(width, height), pageCompression=0)
    pdf.setTitle(f"Billet African Talents - {order.ticket_code}")
    pdf.setAuthor("African Talents")

    pdf.setFillColor(navy)
    pdf.roundRect(0, 0, width, height, 5 * mm, fill=1, stroke=0)
    pdf.setStrokeColor(gold)
    pdf.setLineWidth(1.4)
    pdf.roundRect(2, 2, width - 4, height - 4, 5 * mm, fill=0, stroke=1)

    stub_width = 72 * mm
    pass_width = 32 * mm
    side_width = 22 * mm
    split_y = 34 * mm
    pass_x = width - pass_width - side_width
    stub_right = stub_width
    header_center = pass_x / 2

    pdf.setFillColor(panel)
    pdf.rect(stub_right, split_y, width - stub_right, height - split_y, fill=1, stroke=0)
    pdf.setFillColor(dark)
    pdf.rect(2, 2, stub_width, split_y - 2, fill=1, stroke=0)
    pdf.setFillColor(colors.HexColor("#08153A"))
    pdf.rect(pass_x, split_y, pass_width, height - split_y, fill=1, stroke=0)
    pdf.setFillColor(colors.HexColor("#030A20"))
    pdf.rect(width - side_width, split_y, side_width, height - split_y, fill=1, stroke=0)

    pdf.setStrokeColor(gold)
    pdf.setLineWidth(1)
    pdf.line(stub_right, 3, stub_right, height - 3)
    pdf.line(stub_right, split_y, width - 3, split_y)
    pdf.line(pass_x, split_y, pass_x, height - 3)
    pdf.line(width - side_width, split_y, width - side_width, height - 3)

    for x, y, radius in [
        (10 * mm, height - 10 * mm, 2.3 * mm),
        (18 * mm, height - 21 * mm, 1.6 * mm),
        (width - 110 * mm, height - 12 * mm, 1.9 * mm),
        (width - 103 * mm, split_y + 10 * mm, 1.4 * mm),
    ]:
        _draw_star(pdf, x, y, radius, gold)

    pdf.setStrokeColor(gold)
    pdf.setLineWidth(0.8)
    pdf.circle(header_center, height - 18 * mm, 10 * mm, fill=0, stroke=1)
    pdf.setFillColor(white)
    pdf.setFont("Helvetica-Bold", 7.2)
    pdf.drawCentredString(header_center, height - 16.5 * mm, "AFRICAN")
    pdf.setFillColor(gold)
    pdf.setFont("Helvetica-Oblique", 8)
    pdf.drawCentredString(header_center, height - 20 * mm, "Talents")

    pdf.setFillColor(pale_gold)
    pdf.setFont("Helvetica-Oblique", 8)
    pdf.drawCentredString(header_center, height - 34 * mm, "Vous êtes convié à la")
    pdf.setFillColor(white)
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawCentredString(header_center, height - 43 * mm, "FINALE DU CONCOURS")
    pdf.setFillColor(gold)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawCentredString(header_center, height - 49 * mm, order.ticket_type.competition.name[:48].upper())

    pdf.setStrokeColor(gold)
    pdf.setLineWidth(0.8)
    pdf.line(header_center - 42 * mm, height - 54 * mm, header_center + 42 * mm, height - 54 * mm)
    pdf.setFillColor(gold)
    pdf.setFont("Helvetica-Bold", 6.5)
    pdf.drawCentredString(header_center, height - 57 * mm, "TITULAIRE")
    holder_name = f"{order.buyer_first_name} {order.buyer_last_name}"
    name_size = min(11, 11 * (pass_x - 20 * mm) / stringWidth(holder_name, "Helvetica-Bold", 11))
    pdf.setFillColor(pale_gold)
    pdf.setFont("Helvetica-Bold", name_size)
    pdf.drawCentredString(header_center, height - 62 * mm, holder_name)
    pdf.setFillColor(white)
    pdf.setFont("Helvetica", 7)
    pdf.drawCentredString(header_center, height - 69 * mm, order.ticket_type.label.upper())
    pdf.setFillColor(white)
    pdf.drawCentredString(
        header_center,
        height - 73 * mm,
        f"{order.amount_xaf:,}".replace(",", " ") + " FCFA",
    )

    pdf.saveState()
    pdf.translate(pass_x + pass_width / 2, split_y + (height - split_y) / 2)
    pdf.rotate(90)
    pdf.setFillColor(gold)
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawCentredString(0, -2, "PASS PREMIUM")
    pdf.restoreState()

    pdf.saveState()
    pdf.translate(width - side_width / 2, split_y + (height - split_y) / 2)
    pdf.rotate(90)
    pdf.setFillColor(white)
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawCentredString(0, 9, "BILLET NOMINATIF")
    pdf.setFillColor(gold)
    pdf.setFont("Helvetica-Bold", 7)
    pdf.drawCentredString(0, -4, order.ticket_code)
    pdf.restoreState()

    pdf.saveState()
    pdf.translate(8 * mm, split_y / 2)
    pdf.rotate(90)
    pdf.setFillColor(white)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawCentredString(0, 0, "UNE ENTRÉE")
    pdf.restoreState()

    qr = QrCodeWidget(order.ticket_code)
    qr.barLevel = "M"
    qr_bounds = qr.getBounds()
    qr_size = 20 * mm
    qr_drawing = Drawing(qr_size, qr_size, transform=[
        qr_size / (qr_bounds[2] - qr_bounds[0]), 0, 0,
        qr_size / (qr_bounds[3] - qr_bounds[1]), 0, 0,
    ])
    qr_drawing.add(qr, name="ticket-code")
    renderPDF.draw(qr_drawing, pdf, 19 * mm, 7 * mm)

    pdf.setFillColor(gold)
    pdf.setFont("Helvetica-Bold", 6.5)
    pdf.drawString(42 * mm, 19 * mm, "BILLET N°")
    pdf.setFillColor(white)
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawString(42 * mm, 13 * mm, order.ticket_code)

    terms_center = stub_right + (pass_x - stub_right) / 2
    pdf.setFillColor(white)
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawCentredString(terms_center, split_y - 6 * mm, "ACCÈS À LA SALLE")
    pdf.setFillColor(pale_gold)
    pdf.setFont("Helvetica-Bold", 5.8)
    event_date = order.ticket_type.competition.start_date.strftime("%d/%m/%Y")
    pdf.drawCentredString(
        terms_center,
        split_y - 11 * mm,
        f"{event_date} · 15 H · ARENA BONAMOUSSADI, DOUALA",
    )
    pdf.setFillColor(gold)
    perk = (
        "PREMIUM : ACCÈS SALLE · BOISSON · PREMIÈRES PLACES · PHOTO AVEC LES STARS"
        if order.ticket_type.ticket_class == TicketType.PREMIUM
        else "PASS BASIC · ACCÈS À LA SALLE"
        if order.ticket_type.ticket_class == TicketType.BASIC
        else "PASS STANDARD · ACCÈS À LA SALLE · BOISSON INCLUSE"
    )
    pdf.drawCentredString(terms_center, split_y - 16 * mm, perk)
    pdf.setFillColor(white)
    pdf.setFont("Helvetica", 5.8)
    pdf.drawCentredString(terms_center, split_y - 21 * mm, "Ce billet n'admet qu'une seule personne.")
    pdf.drawCentredString(terms_center, split_y - 26 * mm, "Perdu, volé ou détruit : ce billet ne peut pas être remplacé.")
    pdf.drawCentredString(terms_center, split_y - 31 * mm, "Vente définitive et non remboursable, sauf annulation ou report.")

    pdf.showPage()
    pdf.save()
    return output.getvalue()


class TicketTypeViewSet(viewsets.ModelViewSet):
    serializer_class = TicketTypeSerializer
    permission_classes = [RBACPermission]
    permission_map = {
        "list": "tickets.manage",
        "retrieve": "tickets.manage",
        "create": "tickets.manage",
        "update": "tickets.manage",
        "partial_update": "tickets.manage",
    }

    def get_queryset(self):
        return TicketType.objects.filter(competition__is_current=True).select_related("competition")


@extend_schema(tags=["ticketing"])
class TicketStatisticsView(APIView):
    permission_classes = [RBACPermission]
    permission_map = {"GET": "tickets.statistics"}

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        competition = Competition.objects.filter(is_current=True).first()
        if competition is None:
            return Response({"total_paid": 0, "candidates": [], "ticket_types": []})

        paid_filter = Q(ticket_orders__status=TicketOrder.PAID)
        candidates = Candidate.objects.filter(
            competition=competition, status=Candidate.PUBLISHED, is_active=True
        ).annotate(ticket_sales=Count("ticket_orders", filter=paid_filter)).order_by("-ticket_sales", "code")
        ticket_types = TicketType.objects.filter(competition=competition).annotate(
            sales=Count("orders", filter=Q(orders__status=TicketOrder.PAID))
        )
        return Response({
            "total_paid": TicketOrder.objects.filter(ticket_type__competition=competition, status=TicketOrder.PAID).count(),
            "candidates": [
                {
                    "candidate_id": str(candidate.pk),
                    "name": candidate.display_name,
                    "code": candidate.code,
                    "points": candidate.ticket_sales,
                    "tickets_sold": candidate.ticket_sales,
                }
                for candidate in candidates
            ],
            "ticket_types": [
                {
                    "ticket_class": item.ticket_class,
                    "label": item.label,
                    "price_xaf": item.price_xaf,
                    "tickets_sold": item.sales,
                }
                for item in ticket_types
            ],
        })


class PublicTicketTypeListView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(tags=["public"], responses=PublicTicketTypeSerializer(many=True))
    def get(self, request):
        competition = Competition.objects.filter(is_current=True).first()
        ticket_types = TicketType.objects.filter(
            competition=competition, is_active=True
        ) if competition and competition.ticket_sales_open else TicketType.objects.none()
        return Response(PublicTicketTypeSerializer(ticket_types, many=True).data)


class PublicTicketOrderCreateView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [VoteOrderRateThrottle]

    @extend_schema(tags=["public"], request=TicketOrderCreateSerializer, responses=TicketOrderStatusSerializer)
    def post(self, request):
        serializer = TicketOrderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        order, created = create_ticket_order(
            ticket_type=values["ticket_type"],
            first_name=values["first_name"],
            last_name=values["last_name"],
            phone=values["phone"],
            operator=values["operator"],
            promo_candidate=values.get("promo_candidate"),
            idempotency_key=values["idempotency_key"],
            request=request,
        )
        payment = Payment.objects.filter(ticket_order=order).first()
        if created:
            try:
                payment = initiate_payment(order, request=request)
            except ServiceUnavailableError:
                payment = Payment.objects.filter(ticket_order=order).first()
            order.refresh_from_db()
        response = TicketOrderStatusSerializer(order).data
        response["payment_status"] = payment.status if payment else "PENDING"
        return Response(response, status=201 if created else 200)


class PublicTicketOrderStatusView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [VoteOrderRateThrottle]

    @extend_schema(tags=["public"], responses=TicketOrderStatusSerializer)
    def get(self, request, order_number):
        order = get_object_or_404(
            TicketOrder.objects.select_related("ticket_type", "promo_candidate"),
            order_number=order_number,
        )
        payment = Payment.objects.filter(ticket_order=order).first()
        if payment and payment.status == Payment.PENDING:
            refresh_pending_payment(payment, request=request)
            order.refresh_from_db()
        return Response(TicketOrderStatusSerializer(order).data)


class PublicTicketPdfView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [VoteOrderRateThrottle]

    @extend_schema(tags=["public"], responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    def get(self, request, order_number):
        order = get_object_or_404(
            TicketOrder.objects.select_related("ticket_type", "promo_candidate"),
            order_number=order_number,
            status=TicketOrder.PAID,
        )
        response = HttpResponse(_ticket_pdf(order), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="billet-{slugify(order.ticket_code)}.pdf"'
        response["Cache-Control"] = "private, no-store"
        return response
