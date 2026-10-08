from django.contrib import admin

from .models import NewsPost


@admin.register(NewsPost)
class NewsPostAdmin(admin.ModelAdmin):
    list_display = ("title", "status", "scheduled_at", "published_at")
    list_filter = ("status",)
    search_fields = ("title",)
