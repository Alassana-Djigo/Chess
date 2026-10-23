"""Helpers to build small FIDE-style rating lists for tests."""

import zipfile
from pathlib import Path


def player_xml(
    fide_id,
    name="Silva, Ana",
    country="ANG",
    title="",
    w_title="",
    rating="",
    rapid="",
    blitz="",
    birthday="",
    flag="",
):
    return (
        f"<player><fideid>{fide_id}</fideid><name>{name}</name><country>{country}</country>"
        f"<sex>M</sex><title>{title}</title><w_title>{w_title}</w_title><o_title></o_title>"
        f"<foa_title></foa_title><rating>{rating}</rating><games>0</games><k>20</k>"
        f"<rapid_rating>{rapid}</rapid_rating><rapid_games>0</rapid_games><rapid_k>20</rapid_k>"
        f"<blitz_rating>{blitz}</blitz_rating><blitz_games>0</blitz_games><blitz_k>20</blitz_k>"
        f"<birthday>{birthday}</birthday><flag>{flag}</flag></player>"
    )


def write_list(directory, *players, as_zip=True) -> Path:
    """Write a rating list with the given <player> snippets and return its path."""
    xml = '<?xml version="1.0" encoding="utf-8"?>\n<playerslist>\n' + "\n".join(players)
    xml += "\n</playerslist>\n"
    directory = Path(directory)
    if as_zip:
        path = directory / "players_list_xml.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("players_list_xml_foa.xml", xml)
    else:
        path = directory / "players_list_xml_foa.xml"
        path.write_text(xml, encoding="utf-8")
    return path
