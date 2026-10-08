from django.contrib import admin

from .models import Competition, Phase


class PhaseInline(admin.TabularInline):
    model = Phase
    extra = 0


@admin.register(Competition)
class CompetitionAdmin(admin.ModelAdmin):
    list_display = ("name", "status", "is_current", "votes_open", "start_date", "end_date")
    list_filter = ("status", "is_current")
    inlines = [PhaseInline]
