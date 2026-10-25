"""Reading the monthly FIDE rating list (https://ratings.fide.com/download_lists.phtml).

The list is a ZIP with one very large XML file (almost two million players), so it is
parsed as a stream and never loaded into memory at once. The file comes from FIDE over HTTPS
and Python's expat parser already limits entity expansion, so the standard library parser is
enough here.
"""

import re
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

import requests

from core.choices import TimeCategory

from .models import Title, WomenTitle

FIDE_LIST_URL = "https://ratings.fide.com/download/players_list_xml.zip"
USER_AGENT = "Chess-stats/0.1 (+https://github.com/Alassana-Djigo/Chess)"

NAME_MAX_LENGTH = 150
MAX_PLAUSIBLE_RATING = 5000  # sanity limit, far above any real rating

# Everything that can go wrong while reading a list: missing or unreadable file, corrupt or
# truncated ZIP, malformed or cut-off XML.
READ_ERRORS = (ValueError, OSError, ElementTree.ParseError, zipfile.BadZipFile)

_FEDERATION = re.compile(r"^[A-Z]{3}$")
_RATING_TAGS = {
    TimeCategory.CLASSICAL: "rating",
    TimeCategory.RAPID: "rapid_rating",
    TimeCategory.BLITZ: "blitz_rating",
}
_OPEN_TITLES = {title.value for title in Title}
_WOMEN_TITLES = {title.value for title in WomenTitle}


@dataclass(frozen=True)
class FidePlayer:
    fide_id: int
    name: str
    federation: str
    birth_year: int | None
    title: str
    women_title: str
    ratings: dict[TimeCategory, int]


def clean_name(raw: str) -> str:
    name = re.sub(r"\s+", " ", raw).replace(" ,", ",").replace(",,", ",").strip()
    return name[:NAME_MAX_LENGTH]


def split_titles(title: str, women_title: str) -> tuple[str, str]:
    """Return (open title, women's title).

    Each value is classified by what it is rather than by the tag it came in, so the result
    does not depend on which tag FIDE uses for women's titles. Other titles (arbiters,
    organisers...) are ignored.
    """
    open_title = women = ""
    for value in (title, women_title):
        value = value.strip().upper()
        if value in _OPEN_TITLES:
            open_title = value
        elif value in _WOMEN_TITLES:
            women = value
    return open_title, women


def _text(element: ElementTree.Element, tag: str) -> str:
    child = element.find(tag)
    return (child.text or "").strip() if child is not None else ""


def _positive_int(value: str, maximum: int | None = None) -> int | None:
    try:
        number = int(value)
    except ValueError:
        return None
    if number <= 0 or (maximum is not None and number > maximum):
        return None
    return number


def parse_player(element: ElementTree.Element) -> FidePlayer | None:
    """Turn one <player> element into a FidePlayer, or None if it has no usable FIDE id."""
    fide_id = _positive_int(_text(element, "fideid"))
    if fide_id is None:
        return None

    federation = _text(element, "country").upper()
    birth_year = _positive_int(_text(element, "birthday"))
    if birth_year is not None and not 1900 <= birth_year <= 2100:
        birth_year = None
    title, women_title = split_titles(_text(element, "title"), _text(element, "w_title"))

    ratings = {}
    for category, tag in _RATING_TAGS.items():
        rating = _positive_int(_text(element, tag), maximum=MAX_PLAUSIBLE_RATING)
        if rating is not None:
            ratings[category] = rating

    return FidePlayer(
        fide_id=fide_id,
        name=clean_name(_text(element, "name")) or f"FIDE #{fide_id}",
        federation=federation if _FEDERATION.match(federation) else "",
        birth_year=birth_year,
        title=title,
        women_title=women_title,
        ratings=ratings,
    )


@contextmanager
def open_list(path: Path):
    """Open the XML inside a FIDE ZIP, or a plain .xml file, as a binary stream."""
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            names = [name for name in archive.namelist() if name.lower().endswith(".xml")]
            if not names:
                raise ValueError(f"No .xml file found inside {path}")
            with archive.open(names[0]) as stream:
                yield stream
    else:
        with Path(path).open("rb") as stream:
            yield stream


def iter_players(path: Path) -> Iterator[FidePlayer]:
    """Yield the players of a FIDE list one at a time, with constant memory use."""
    with open_list(path) as stream:
        root = None
        for event, element in ElementTree.iterparse(stream, events=("start", "end")):
            if root is None:
                root = element
            if event == "end" and element.tag == "player":
                player = parse_player(element)
                root.clear()  # drop the players already read
                if player is not None:
                    yield player


def download_list(destination: Path, url: str = FIDE_LIST_URL) -> Path:
    """Download the list to `destination`. The file only appears there once it is complete."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part")
    headers = {"User-Agent": USER_AGENT}
    with requests.get(url, stream=True, timeout=(10, 120), headers=headers) as response:
        response.raise_for_status()
        with partial.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                handle.write(chunk)
    partial.replace(destination)
    return destination
