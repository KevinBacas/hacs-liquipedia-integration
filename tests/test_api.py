"""Tests for Liquipedia schedule parsing."""

from custom_components.liquipedia.api import _MatchScheduleParser


def _parse_match(status_markup: str = "") -> dict[str, object]:
    parser = _MatchScheduleParser()
    parser.feed(
        f"""
        <tr class="match-row row--body" {status_markup}>
          <td><span data-timestamp="1786118400"></span></td>
          <td>Grand Final</td>
          <td><a title="Team One"></a></td>
          <td>Bo5</td>
          <td><a title="Team Two"></a></td>
        </tr>
        """
    )
    return parser.matches[0]


def test_parser_marks_explicitly_live_match_as_live() -> None:
    """An explicit live marker is exposed to the binary sensor."""
    match = _parse_match('data-match-status="live"')

    assert match["status"] == "live"


def test_parser_marks_explicitly_finished_match_as_finished() -> None:
    """A completed match must not be treated as live."""
    match = _parse_match('class="match-row row--body match-status--finished"')

    assert match["status"] == "finished"


def test_parser_does_not_infer_live_status_from_scheduled_time() -> None:
    """A timestamp without an upstream status remains unknown."""
    match = _parse_match()

    assert match["status"] == "unknown"
