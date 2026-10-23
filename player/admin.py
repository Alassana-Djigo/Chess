from django.contrib import admin

from .models import Player, PlayerAccount


class PlayerAccountInline(admin.TabularInline):
    model = PlayerAccount
    extra = 0


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    search_fields = ["name", "fide_id"]
    list_display = ["name", "title", "women_title", "federation", "fide_id"]
    list_filter = ["title", "women_title", "federation"]
    inlines = [PlayerAccountInline]
