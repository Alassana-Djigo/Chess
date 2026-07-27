from django.contrib import admin
from .models import Match

@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    autocomplete_fields = ['player_white', 'player_black', 'tournament']
    list_display = ['player_white', 'player_black', 'time_control', 'date']