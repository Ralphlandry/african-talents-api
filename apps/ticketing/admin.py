from django.contrib import admin

from .models import TicketOrder, TicketType


@admin.register(TicketType)
class TicketTypeAdmin(admin.ModelAdmin):
    list_display = ("competition", "ticket_class", "label", "price_xaf", "is_active")
    list_filter = ("ticket_class", "is_active", "competition")


@admin.register(TicketOrder)
class TicketOrderAdmin(admin.ModelAdmin):
    list_display = ("order_number", "buyer_first_name", "buyer_last_name", "ticket_type", "amount_xaf", "status")
    list_filter = ("status", "operator", "ticket_type")
    search_fields = ("order_number", "buyer_first_name", "buyer_last_name", "customer_phone")
    readonly_fields = ("order_number", "buyer_first_name", "buyer_last_name", "customer_phone", "amount_xaf", "operator", "idempotency_key")
