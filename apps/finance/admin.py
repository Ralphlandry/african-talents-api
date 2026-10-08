from django.contrib import admin

from .models import ReconciliationItem, ReconciliationRun


class ReconciliationItemInline(admin.TabularInline):
    model = ReconciliationItem
    extra = 0
    readonly_fields = [f.name for f in ReconciliationItem._meta.fields]
    can_delete = False


@admin.register(ReconciliationRun)
class ReconciliationRunAdmin(admin.ModelAdmin):
    list_display = ("period_from", "period_to", "status", "finished_at")
    inlines = [ReconciliationItemInline]
