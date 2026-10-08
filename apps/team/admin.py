from django.contrib import admin

from .models import TeamMember


@admin.register(TeamMember)
class TeamMemberAdmin(admin.ModelAdmin):
    list_display = ("full_name", "type", "role_title", "order", "is_visible")
    list_filter = ("type", "is_visible")
