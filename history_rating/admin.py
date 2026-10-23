from django.contrib import admin

from .models import HistoryRating


@admin.register(HistoryRating)
class HistoryRatingAdmin(admin.ModelAdmin):
    autocomplete_fields = ["player"]
    search_fields = ["player__name", "player__fide_id"]
    list_display = ["player", "source", "time_category", "rating_date", "rating"]
    list_filter = ["source", "time_category"]
    list_select_related = ["player"]
