from django.contrib import admin

from .models import MediaAsset


@admin.register(MediaAsset)
class MediaAssetAdmin(admin.ModelAdmin):
    list_display = ("original_name", "kind", "size_kb", "usage", "created_at")
    list_filter = ("kind",)
    search_fields = ("original_name",)
