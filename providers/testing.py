"""Fakes and builders for Lichess tests. Payloads follow the official API specification."""

import json

import requests

CREATED_AT = 1_760_000_000_000  # 2025-10-09 08:53:20 UTC, in milliseconds


def lichess_user(
    username="Anna",
    *,
    fide_id=None,
    title=None,
    real_name=None,
    disabled=False,
    perfs=None,
):
    data = {
        "id": username.lower(),
        "username": username,
        "createdAt": CREATED_AT,
        "perfs": perfs
        if perfs is not None
        else {
            "bullet": {"games": 10, "rating": 2100, "rd": 60, "prog": 3},
            "blitz": {"games": 50, "rating": 2200, "rd": 50, "prog": -4},
            "rapid": {"games": 5, "rating": 1900, "rd": 120, "prog": 0, "prov": True},
            "classical": {"games": 0, "rating": 1500, "rd": 350, "prog": 0, "prov": True},
            "correspondence": {"games": 7, "rating": 1800, "rd": 80, "prog": 0},
        },
    }
    if title:
        data["title"] = title
    if real_name:
        data["profile"] = {"realName": real_name}
    if fide_id:
        data["fideId"] = fide_id
    if disabled:
        data["disabled"] = True
    return data


def lichess_game(
    game_id="game0001",
    *,
    white="Anna",
    black="Bruno",
    winner="white",
    status="mate",
    speed="blitz",
    variant="standard",
    initial=180,
    increment=2,
    created_at=CREATED_AT,
    eco="C20",
    opening="King's Pawn Game",
    white_rating=2400,
    black_rating=2350,
):
    def side(name, rating):
        return {"user": {"name": name, "id": name.lower()}, "rating": rating, "ratingDiff": 4}

    data = {
        "id": game_id,
        "rated": True,
        "variant": variant,
        "speed": speed,
        "perf": speed,
        "createdAt": created_at,
        "lastMoveAt": created_at + 60_000,
        "status": status,
        "players": {"white": side(white, white_rating), "black": side(black, black_rating)},
        "opening": {"eco": eco, "name": opening, "ply": 3},
        "moves": "e4 e5 Nf3",
        "pgn": '[Event "Rated blitz game"]\n\n1. e4 e5 2. Nf3 *',
        "clock": {
            "initial": initial,
            "increment": increment,
            "totalTime": initial + 40 * increment,
        },
    }
    if winner:
        data["winner"] = winner
    return data


class FakeResponse:
    def __init__(self, status_code=200, payload=None, lines=None, stream_error=None):
        self.status_code = status_code
        self.payload = payload
        self.lines = lines or []
        self.stream_error = stream_error
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    def close(self):
        self.closed = True

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")

    def json(self):
        if self.payload is None:
            raise ValueError("not json")
        return self.payload

    def iter_lines(self):
        for line in self.lines:
            yield line if isinstance(line, bytes) else json.dumps(line).encode()
        if self.stream_error:
            raise self.stream_error


class FakeSession:
    """Answers each request with the next scripted response and remembers the requests."""

    def __init__(self, *responses, error=None):
        self.responses = list(responses)
        self.error = error
        self.headers = {}
        self.calls = []

    def get(self, url, params=None, stream=False, headers=None, timeout=None):
        self.calls.append({"url": url, "params": params, "stream": stream, "headers": headers})
        if self.error:
            raise self.error
        return self.responses.pop(0)
