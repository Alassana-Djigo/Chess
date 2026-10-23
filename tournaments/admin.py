from django.contrib import admin

from .models import Tournament


@admin.register(Tournament)
class TournamentAdmin(admin.ModelAdmin):
    search_fields = ["name", "venue"]
    list_display = ["name", "format", "status", "start_date", "end_date"]
    list_filter = ["format", "status", "start_date"]
