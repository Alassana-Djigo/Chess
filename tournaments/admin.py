from django.contrib import admin
from .models import Tournament

@admin.register(Tournament)
class TournamentAdmin(admin.ModelAdmin):
    search_fields = ['name', 'local']
    list_display = ['name', 'formate', 'prize']
    list_filter = ['name', 'formate']