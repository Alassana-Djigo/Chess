"""Telling whether a platform profile and a player could be the same person."""

import re
import unicodedata


def _words(text: str) -> set[str]:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return {word for word in re.split(r"[^a-z0-9]+", plain) if len(word) > 1}


def names_compatible(claimed: str, player_name: str) -> bool:
    """False only when the profile gives a name and it shares no word with the player's name.

    Accents, case, word order and 'Surname, Given' style do not matter. A profile with no name
    gives us nothing to compare, so it never counts as a mismatch.
    """
    claimed_words = _words(claimed)
    if not claimed_words:
        return True
    return bool(claimed_words & _words(player_name))
