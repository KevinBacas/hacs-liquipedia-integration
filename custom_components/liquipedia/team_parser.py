"""Parse the upcoming match cards rendered on a Liquipedia team page."""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any

BEST_OF_PATTERN = re.compile(r"\bBo\d+\b", re.IGNORECASE)
_VOID_ELEMENTS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
}
_STATUS_ATTRIBUTES = ("data-status", "data-match-status", "data-state", "data-match-state")
_LIVE_VALUES = {"live", "ongoing", "in-progress", "running"}
_FINISHED_VALUES = {"finished", "completed", "cancelled", "canceled", "notplayed", "not-played"}


def normalize_title(value: str) -> str:
    """Normalize MediaWiki page-title whitespace."""
    return " ".join(value.replace("_", " ").split())


def match_status_markers(attributes: dict[str, str | None]) -> set[str]:
    """Extract explicit state fields and match-specific status classes."""
    values = {value for name in _STATUS_ATTRIBUTES if (value := attributes.get(name))}
    values.update(
        css_class.removeprefix("match-status--")
        for css_class in (attributes.get("class") or "").split()
        if css_class.startswith("match-status--")
    )
    if attributes.get("data-finished") == "finished":
        values.add("finished")
    return {value.strip().lower().replace("_", "-") for value in values}


def match_status(values: set[str]) -> str:
    """Use explicit match state, prioritizing a terminal state."""
    if values & _FINISHED_VALUES:
        return "finished"
    if values & _LIVE_VALUES:
        return "live"
    return "unknown"


@dataclass
class _Participant:
    name_link: str | None = None
    logo_link: str | None = None
    name_text: list[str] = field(default_factory=list)
    self_link: bool = False

    def name(self, page_title: str) -> str:
        if self.self_link:
            return page_title
        return self.name_link or self.logo_link or "".join(self.name_text).strip()

    def identifies(self, page_title: str) -> bool:
        """Match the team using its self link, title, logo, or visible name."""
        return self.self_link or any(
            normalize_title(value).casefold() == page_title.casefold()
            for value in (self.name_link, self.logo_link, "".join(self.name_text))
            if value
        )


@dataclass
class _Card:
    timestamp: str | None = None
    header: list[str] = field(default_factory=list)
    participants: list[_Participant] = field(default_factory=list)
    tournament_name: list[str] = field(default_factory=list)
    tournament_page: str | None = None
    status_values: set[str] = field(default_factory=set)

    def match(self, page_title: str, game: str) -> dict[str, Any] | None:
        if self.timestamp is None or len(self.participants) != 2:
            return None
        try:
            date = datetime.fromtimestamp(int(self.timestamp), timezone.utc)
        except (ValueError, OverflowError, OSError):
            return None

        team1, team2 = (participant.name(page_title) for participant in self.participants)
        tournament = " ".join("".join(self.tournament_name).split()) or self.tournament_page
        if not (team1 and team2 and tournament):
            return None

        first_is_team, second_is_team = (
            participant.identifies(page_title) for participant in self.participants
        )
        opponent = None
        if first_is_team != second_is_team:
            opponent = team2 if first_is_team else team1

        best_of = BEST_OF_PATTERN.search(" ".join(self.header))
        return {
            "date": date,
            "title": f"{team1} vs {team2}",
            "team1": team1,
            "team2": team2,
            "opponent": opponent,
            "status": match_status(self.status_values),
            "tournament": tournament,
            "tournament_page": self.tournament_page,
            "game": game,
            "best_of": best_of.group(0).upper() if best_of else None,
        }


class TeamPageParser(HTMLParser):
    """Read the team infobox and match ticker cards from parsed wiki HTML."""

    def __init__(self, page_title: str, game: str) -> None:
        super().__init__()
        self._page_title = page_title
        self._game = game
        self._elements: list[tuple[str, set[str]]] = []
        self._team_infobox_depth: int | None = None
        self._team_topcontent_depth: int | None = None
        self._ticker_depth: int | None = None
        self._card: _Card | None = None
        self._cta_text: list[str] = []
        self.matches: list[dict[str, Any]] = []
        self.has_team_layout = False
        self.has_ticker = False
        self.invalid_ticker = False

    @classmethod
    def parse_matches(cls, html: str, page_title: str, game: str) -> list[dict[str, Any]]:
        """Return a team's matches or report an unrecognized team/ticker layout."""
        parser = cls(page_title, game)
        parser.feed(html)
        parser.close()
        if not parser.has_team_layout:
            raise ValueError("Liquipedia did not return a supported team page")
        if parser.invalid_ticker or (parser.has_ticker and not parser.matches):
            raise ValueError("Liquipedia returned an unsupported team match ticker")
        # The wiki omits the ticker entirely when there are no matches to show.
        return sorted(parser.matches, key=lambda match: match["date"])

    def _inside(self, css_class: str) -> bool:
        return any(css_class in classes for _, classes in self._elements)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        if tag not in _VOID_ELEMENTS:
            self._elements.append((tag, classes))

        if attributes.get("data-analytics-infobox-type") == "Team":
            self._team_infobox_depth = len(self._elements) - 1
        if (
            self._team_infobox_depth is not None
            and "fo-nttax-infobox-topcontent" in classes
        ):
            self._team_topcontent_depth = len(self._elements) - 1
        if (
            attributes.get("id") == "Upcoming_Matches"
            and self._team_topcontent_depth is not None
        ):
            for index in range(len(self._elements) - 1, 0, -1):
                if self._elements[index][0] not in {"h2", "h3"}:
                    continue
                parent = index - 1
                if "mw-heading" in self._elements[parent][1]:
                    parent -= 1
                self._ticker_depth = parent
                self.has_ticker = True
                break
        if "error" in classes and self._team_topcontent_depth is not None:
            self.invalid_ticker = True

        if (
            self._ticker_depth is not None
            and "match-ticker-card" in classes
            and self._inside("match-ticker-carousel")
        ):
            self._card = _Card()
        if (card := self._card) is None:
            return

        if "match-ticker-card__opponent" in classes:
            card.participants.append(_Participant())
        if self._inside("match-ticker-card__header") or "match-ticker-card" in classes:
            card.status_values.update(match_status_markers(attributes))
        if self._inside("match-ticker-card__header") and "timer-object" in classes:
            card.timestamp = attributes.get("data-timestamp")

        if tag != "a":
            return
        title = normalize_title(attributes.get("title") or "")
        if self._inside("match-ticker-card__opponent") and card.participants:
            participant = card.participants[-1]
            if self._inside("team-name-dynamic"):
                if "new" not in classes:
                    participant.name_link = title or None
                participant.self_link = bool(classes & {"mw-selflink", "selflink"})
            elif self._inside("team-template-image-icon") and title:
                participant.logo_link = title
        elif self._inside("match-ticker-card-tournament-name") and title and "new" not in classes:
            card.tournament_page = title.split("#", 1)[0]

    def handle_data(self, data: str) -> None:
        if (card := self._card) is None:
            return
        if self._inside("match-ticker-card__header"):
            card.header.append(data)
        if self._inside("team-name") and card.participants:
            card.participants[-1].name_text.append(data)
        if self._inside("match-ticker-card-tournament-name"):
            card.tournament_name.append(data)
        if (
            self._inside("match-info-links")
            and self._inside("livestream")
            and self._inside("match-button-cta-text")
        ):
            self._cta_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self._elements) - 1, -1, -1):
            if self._elements[index][0] != tag:
                continue
            closing = self._elements[index:]
            del self._elements[index:]
            break
        else:
            return

        if self._team_infobox_depth is not None and index <= self._team_infobox_depth:
            self._team_infobox_depth = None
        if self._team_topcontent_depth is not None and index <= self._team_topcontent_depth:
            self.has_team_layout |= index == self._team_topcontent_depth
            self._team_topcontent_depth = None
        if self._ticker_depth is not None and index <= self._ticker_depth:
            self._ticker_depth = None
        if (card := self._card) is None:
            return
        if any("match-button-cta-text" in classes for _, classes in closing):
            # The upstream stream widget emits this CTA only for an ongoing match.
            if " ".join("".join(self._cta_text).split()) == "Watch now":
                card.status_values.add("live")
            self._cta_text.clear()
        if any("match-ticker-card" in classes for _, classes in closing):
            if (match := card.match(self._page_title, self._game)) is None:
                self.invalid_ticker = True
            elif match["opponent"] is not None:
                self.matches.append(match)
            self._card = None

    def close(self) -> None:
        """Detect a truncated card as well as malformed complete cards."""
        super().close()
        if self._card is not None:
            self.invalid_ticker = True
