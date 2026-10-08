from django.contrib import admin

from .models import Partner


@admin.register(Partner)
class PartnerAdmin(admin.ModelAdmin):
    list_display = ("name", "order", "is_visible")
    list_filter = ("is_visible",)
    search_fields = ("name",)