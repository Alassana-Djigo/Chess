"""Builders for Chess.com tournament tests. The shapes follow the real answers seen in use."""

SLUG = "titled-tuesday-blitz-november-03-2026-31201855"
START = 1793721600  # 2026-11-03 16:00 UTC
FINISH = 1793729685


def round_urls(slug=SLUG, rounds=11):
    return [f"https://api.chess.com/pub/tournament/{slug}/{n}" for n in range(1, rounds + 1)]


def event_data(slug=SLUG, *, status="finished", rounds=11, start=START, finish=FINISH, winner=""):
    data = {
        "name": slug.title(),
        "status": status,
        "settings": {"type": "swiss", "total_rounds": rounds, "time_class": "blitz"},
        "players": [{"username": winner, "status": "winner"}, {"username": "hikaru"}]
        if winner
        else [{"username": "hikaru", "status": "registered"}],
        "rounds": round_urls(slug, rounds),
    }
    if start is not None:
        data["start_time"] = start
    if finish is not None:
        data["finish_time"] = finish
    return data


def last_round(slug=SLUG, rounds=11, groups=1):
    base = f"https://api.chess.com/pub/tournament/{slug}/{rounds}"
    return {"groups": [f"{base}/{n}" for n in range(1, groups + 1)], "players": []}


def group_data(*scores):
    """scores: (username, points) pairs, best first. The first one is flagged as winner."""
    return {
        "games": [],
        "players": [
            {"username": name, "points": points, "is_winner": index == 0}
            for index, (name, points) in enumerate(scores)
        ],
    }
