"""A tiny SVG line chart for rating history. No JavaScript and no dependencies."""

import math
from dataclasses import dataclass
from datetime import date

WIDTH, HEIGHT = 640, 220
PAD_LEFT, PAD_RIGHT, PAD_TOP, PAD_BOTTOM = 52, 16, 16, 28


@dataclass(frozen=True)
class Chart:
    width: int
    height: int
    line: str  # SVG path of the rating line, empty when there is a single point
    area: str  # closed path under the line, empty when there is a single point
    last_x: float
    last_y: float
    y_min: int
    y_max: int
    first_date: date
    last_date: date
    y_ticks: list[tuple[float, int]]  # (pixel position, rating) for the grid
    count: int


def _bounds(low: int, high: int) -> tuple[int, int]:
    """Round the vertical range outwards so the line never touches the edges."""
    step = 50 if high - low >= 100 else 10
    y_min = math.floor((low - step / 2) / step) * step
    y_max = math.ceil((high + step / 2) / step) * step
    return y_min, y_max


def build_chart(points: list[tuple[date, int]]) -> Chart | None:
    """Turn (date, rating) points into drawing coordinates, or None if there are none."""
    if not points:
        return None
    points = sorted(points)
    first, last = points[0][0], points[-1][0]
    ratings = [rating for _, rating in points]
    y_min, y_max = _bounds(min(ratings), max(ratings))

    left, right = PAD_LEFT, WIDTH - PAD_RIGHT
    bottom, top = HEIGHT - PAD_BOTTOM, PAD_TOP
    span = (last - first).days

    def x_of(day: date) -> float:
        return left + (right - left) * ((day - first).days / span) if span else (left + right) / 2

    def y_of(rating: float) -> float:
        return bottom - (bottom - top) * ((rating - y_min) / (y_max - y_min))

    coords = [(x_of(day), y_of(rating)) for day, rating in points]
    last_x, last_y = coords[-1]
    if len(coords) > 1:
        line = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in coords)
        area = f"{line} L{coords[-1][0]:.1f} {bottom} L{coords[0][0]:.1f} {bottom} Z"
    else:
        line = area = ""

    middle = round((y_min + y_max) / 2)
    ticks = [(round(y_of(value), 1), value) for value in (y_min, middle, y_max)]
    return Chart(
        width=WIDTH,
        height=HEIGHT,
        line=line,
        area=area,
        last_x=round(last_x, 1),
        last_y=round(last_y, 1),
        y_min=y_min,
        y_max=y_max,
        first_date=first,
        last_date=last,
        y_ticks=ticks,
        count=len(points),
    )
