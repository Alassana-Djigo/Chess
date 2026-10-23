from django.contrib import admin

from .models import Match


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    autocomplete_fields = ["player_white", "player_black", "tournament"]
    list_display = ["player_white", "player_black", "outcome", "time_category", "date"]
    list_filter = ["time_category", "outcome", "online", "source"]
    list_select_related = ["player_white", "player_black"]
    date_hierarchy = "date"
