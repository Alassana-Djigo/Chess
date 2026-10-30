from dataclasses import replace

from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from core.choices import Source, TimeCategory
from player.models import Player

from .versus import (
    MODES,
    build_insights,
    build_rows,
    head_to_head,
    latest_pool_ratings,
    resolve_player,
)


def versus_form(request):
    query_a = request.GET.get("a", "").strip()[:100]
    query_b = request.GET.get("b", "").strip()[:100]
    problems = []
    if query_a and query_b:
        a, b = resolve_player(query_a), resolve_player(query_b)
        if a is None:
            problems.append(f"Não encontrei nenhum jogador para «{query_a}».")
        if b is None:
            problems.append(f"Não encontrei nenhum jogador para «{query_b}».")
        if a and b and a.pk == b.pk:
            problems.append("Escolhe dois jogadores diferentes.")
        if not problems:
            return redirect("versus", a.pk, b.pk)
    context = {"query_a": query_a, "query_b": query_b, "problems": problems}
    return render(request, "web/versus_form.html", context)


def _hero(player: Player, pool: dict) -> dict:
    given, surname = player.name_parts
    initials = (given[:1] + surname[:1]).upper() if surname else player.name[:2].upper()
    return {
        "player": player,
        "given": given,
        "surname": surname,
        "initials": initials,
        "rating": pool.get((Source.FIDE, TimeCategory.CLASSICAL)),
    }


def versus(request, a, b):
    if a == b:
        raise Http404("Escolhe dois jogadores diferentes.")
    player_a = get_object_or_404(Player, pk=a)
    player_b = get_object_or_404(Player, pk=b)
    mode = request.GET.get("modo", "todos")
    if mode not in MODES:
        mode = "todos"

    pool_a, pool_b = latest_pool_ratings(player_a), latest_pool_ratings(player_b)
    otb, online = build_rows(pool_a, pool_b)
    if mode == "presencial":
        online = []
    elif mode == "online":
        otb = []
    h2h = head_to_head(player_a, player_b)
    insights = build_insights(
        player_a, player_b, otb + online, replace(h2h, overall=h2h.for_mode(mode))
    )
    context = {
        "a": _hero(player_a, pool_a),
        "b": _hero(player_b, pool_b),
        "mode": mode,
        "modes": [
            ("todos", "Presencial + online"),
            ("presencial", "Presencial"),
            ("online", "Online"),
        ],
        "otb": otb,
        "online": online,
        "h2h": h2h,
        "insights": insights,
    }
    return render(request, "web/versus.html", context)
