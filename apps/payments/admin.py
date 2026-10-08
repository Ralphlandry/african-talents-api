from django.contrib import admin

from .models import Payment, PaymentEvent


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("reference", "status", "amount_xaf", "operator", "initiated_at")
    list_filter = ("status", "operator", "environment")
    search_fields = ("reference", "provider_reference")


@admin.register(PaymentEvent)
class PaymentEventAdmin(admin.ModelAdmin):
    list_display = ("reference", "event_type", "signature_valid", "processed", "created_at")
    list_filter = ("signature_valid", "processed")
