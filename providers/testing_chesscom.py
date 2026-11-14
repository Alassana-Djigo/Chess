"""Builders for Chess.com tests. Payloads follow the published-data API documentation."""

END_TIME = 1_760_000_000  # 2025-10-09 08:53:20 UTC


def chesscom_profile(
    username="AnaGM",
    *,
    name="Ana Silva",
    title=None,
    avatar="https://images.example.com/avatar.png",
    status="premium",
    player_id=123,
):
    data = {"username": username, "player_id": player_id, "status": status, "name": name}
    if title:
        data["title"] = title
    if avatar:
        data["avatar"] = avatar
    return data


def chesscom_game(
    game_id="100001",
    *,
    white="AnaGM",
    black="RuiGM",
    white_result="win",
    black_result="checkmated",
    time_class="blitz",
    time_control="180+2",
    rules="chess",
    rated=True,
    end_time=END_TIME,
    white_rating=2400,
    black_rating=2350,
    tournament=None,
    eco="B90",
    opening_slug="Sicilian-Defense-Najdorf-Variation-6.Be3-e5",
):
    data = {
        "url": f"https://www.chess.com/game/live/{game_id}",
        "pgn": (
            f'[Event "Live Chess"]\n[ECO "{eco}"]\n'
            f'[ECOUrl "https://www.chess.com/openings/{opening_slug}"]\n\n1. e4 c5 *'
        ),
        "time_control": time_control,
        "end_time": end_time,
        "rated": rated,
        "time_class": time_class,
        "rules": rules,
        "white": {"username": white, "rating": white_rating, "result": white_result},
        "black": {"username": black, "rating": black_rating, "result": black_result},
    }
    if tournament:
        data["tournament"] = f"https://api.chess.com/pub/tournament/{tournament}"
    return data
