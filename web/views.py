from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, render

from player.models import Player

from .charts import build_chart
from .services import (
    historic_players,
    latest_ratings,
    pick_series,
    rating_series,
    recent_games,
    search_players,
    summarize,
    top_rated,
)


def home(request):
    top, period = top_rated(limit=20)
    return render(
        request,
        "web/home.html",
        {"top": top, "period": period, "player_count": Player.objects.count()},
    )


def historic(request):
    paginator = Paginator(historic_players(), 50)
    page = paginator.get_page(request.GET.get("page"))
    return render(request, "web/historic_players.html", {"page": page})


def player_search(request):
    query = request.GET.get("q", "").strip()[:100]
    players = search_players(query) if query else []
    return render(request, "web/player_search.html", {"query": query, "players": players})


def player_detail(request, pk):
    player = get_object_or_404(Player.objects.prefetch_related("accounts"), pk=pk)
    ratings = latest_ratings(player)
    selected = pick_series(ratings, request.GET.get("source"), request.GET.get("category"))
    chart = (
        build_chart(rating_series(player, selected.source, selected.category)) if selected else None
    )
    return render(
        request,
        "web/player_detail.html",
        {
            "player": player,
            "accounts": list(player.accounts.all()),
            "ratings": ratings,
            "selected": selected,
            "chart": chart,
            "summary": summarize(player),
            "games": recent_games(player),
        },
    )
