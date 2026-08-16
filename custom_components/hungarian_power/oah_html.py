"""Parser for the official OAH/Paks operating-data page."""

from __future__ import annotations

import re
from datetime import datetime
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

from .models import PaksData

LOCAL_TZ = ZoneInfo("Europe/Budapest")


class OahParseError(ValueError):
    """Raised when the OAH page shape is not recognized."""


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._row is not None and self._cell is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None


def parse_oah_html(payload: str) -> PaksData:
    """Extract the OAH timestamp and four Paks block values."""
    parser = _TableParser()
    parser.feed(payload)
    parser.close()

    text = " ".join(" ".join(row) for row in parser.rows)
    timestamp_match = re.search(
        r"Mérés\s+dátuma\s*:\s*(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\s+"
        r"(\d{1,2}):(\d{2})",
        text,
        re.IGNORECASE,
    )
    if not timestamp_match:
        raise OahParseError("OAH measurement timestamp was not found")
    timestamp = datetime(
        int(timestamp_match.group(1)),
        int(timestamp_match.group(2)),
        int(timestamp_match.group(3)),
        int(timestamp_match.group(4)),
        int(timestamp_match.group(5)),
        tzinfo=LOCAL_TZ,
    )

    values = _find_block_values(parser.rows)
    if values is None:
        raise OahParseError("OAH Paks block values were not found")
    return PaksData(timestamp=timestamp, units_mw=values)


def _find_block_values(rows: list[list[str]]) -> tuple[float | None, ...] | None:
    for row in rows:
        candidates = [_parse_mw(cell) for cell in row]
        has_mw_unit = any("mw" in cell.casefold() for cell in row)
        if has_mw_unit and len(row) >= 4 and sum(value is not None for value in candidates) >= 4:
            first_four = tuple(candidates[:4])
            if all(value is not None for value in first_four):
                return first_four

    flattened = " ".join(" ".join(row) for row in rows)
    match = re.search(
        r"1\.\s*blokk.*?2\.\s*blokk.*?3\.\s*blokk.*?4\.\s*blokk\s+"
        r"(-?[\d\s.,]+)\s*MW\s+(-?[\d\s.,]+)\s*MW\s+"
        r"(-?[\d\s.,]+)\s*MW\s+(-?[\d\s.,]+)\s*MW",
        flattened,
        re.IGNORECASE,
    )
    if not match:
        return None
    return tuple(_parse_mw(value) for value in match.groups())


def _parse_mw(value: str) -> float | None:
    match = re.search(r"(-?[\d\s.,]+)\s*(?:MW)?", value, re.IGNORECASE)
    if not match:
        return None
    try:
        return float(match.group(1).replace(" ", "").replace(",", "."))
    except ValueError:
        return None
