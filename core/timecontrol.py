from .choices import TimeCategory

BULLET_LIMIT = 180
BLITZ_LIMIT = 480
RAPID_LIMIT = 1500


def categorize_time_control(base_seconds: int, increment_seconds: int = 0) -> TimeCategory:
    """Classify a clock (base time + increment, in seconds) the way Lichess does.

    Estimated duration = base + 40 * increment (a nominal 40-move game). Under 180 s is
    bullet, under 480 s blitz, under 1500 s rapid, and anything longer is classical.

    Chess.com and FIDE draw these lines slightly differently, so importers should keep the
    category the source provides whenever there is one, and use this only as a fallback.
    """
    estimated = base_seconds + 40 * increment_seconds
    if estimated < BULLET_LIMIT:
        return TimeCategory.BULLET
    if estimated < BLITZ_LIMIT:
        return TimeCategory.BLITZ
    if estimated < RAPID_LIMIT:
        return TimeCategory.RAPID
    return TimeCategory.CLASSICAL
