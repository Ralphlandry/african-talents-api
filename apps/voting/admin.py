from django.contrib import admin

from .models import Vote, VoteOrder, VotePackage


@admin.register(VotePackage)
class VotePackageAdmin(admin.ModelAdmin):
    list_display = ("label", "competition", "quantity", "price_xaf", "is_active")


@admin.register(VoteOrder)
class VoteOrderAdmin(admin.ModelAdmin):
    list_display = ("order_number", "candidate", "quantity", "amount_xaf", "status")
    list_filter = ("status", "operator")
    readonly_fields = ("order_number",)


@admin.register(Vote)
class VoteAdmin(admin.ModelAdmin):
    list_display = ("candidate", "quantity", "source", "created_at")
    list_filter = ("source",)
