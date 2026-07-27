from django.contrib import admin
from .models import HistoryRating

@admin.register(HistoryRating)
class HistoryRatingAdmin(admin.ModelAdmin):
    search_fields = ['player', 'rating']
    list_display = ['player', 'time_control', 'rating']
    list_filter = ['time_control']