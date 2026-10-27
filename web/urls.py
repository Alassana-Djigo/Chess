from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("players/", views.player_search, name="player_search"),
    path("todos-os-tempos/", views.historic, name="historic_players"),
    path("players/<int:pk>/", views.player_detail, name="player_detail"),
]
