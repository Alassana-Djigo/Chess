from django.contrib import admin
from .models import Jogador


@admin.register(Jogador)
class JogadorAdmin(admin.ModelAdmin):
    search_fields = ['name', 'id_fide']