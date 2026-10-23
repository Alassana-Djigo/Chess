from django.contrib import admin

from .models import HistoryRating


@admin.register(HistoryRating)
class HistoryRatingAdmin(admin.ModelAdmin):
    search_fields = ["player__name", "player__id_fide"]
    list_display = ["player", "time_control", "rating_date", "rating"]
    list_filter = ["time_control"]
    list_select_related = ["player"]
