from django.contrib import admin

from .models import Candidate


@admin.register(Candidate)
class CandidateAdmin(admin.ModelAdmin):
    list_display = ("code", "first_name", "last_name", "category", "status", "is_active")
    list_filter = ("status", "is_active", "category")
    search_fields = ("code", "first_name", "last_name")
