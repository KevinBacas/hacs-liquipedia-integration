"""Liquipedia API client."""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime
from typing import Any, Dict

import aiohttp
from bs4 import BeautifulSoup

from .const import LIQUIPEDIA_API_URL, USER_AGENT

_LOGGER = logging.getLogger(__name__)


class LiquipediaAPI:
    """API client for Liquipedia."""

    def __init__(self, game: str) -> None:
        """Initialize the API client."""
        self.game = game
        self.session = None
        self._base_url = LIQUIPEDIA_API_URL.format(game=game)

    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession(
            headers={"User-Agent": USER_AGENT},
            timeout=aiohttp.ClientTimeout(total=30),
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()

    async def get_tournament_info(self, tournament_name: str = None) -> Dict[str, Any]:
        """Get tournament information from Liquipedia."""
        if not tournament_name:
            tournament_name = "Main_Page"

        try:
            # Get page content using MediaWiki API
            params = {
                "action": "query",
                "format": "json",
                "titles": tournament_name,
                "prop": "revisions",
                "rvprop": "content",
                "rvslots": "main"
            }

            async with self.session.get(self._base_url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    pages = data.get("query", {}).get("pages", {})

                    if pages:
                        page_id = next(iter(pages))
                        page_content = pages[page_id]

                        if "revisions" in page_content:
                            wiki_text = page_content["revisions"][0]["slots"]["main"]["*"]
                            return self._parse_tournament_info(wiki_text, tournament_name)

                    _LOGGER.warning("Tournament page not found: %s", tournament_name)
                    return {"name": tournament_name, "status": "Not Found"}
                else:
                    _LOGGER.error("Failed to get tournament info: %s", response.status)
                    return {}

        except Exception as e:
            _LOGGER.error("Error getting tournament info: %s", e)
            return {}

    def _parse_tournament_info(self, wiki_text: str, tournament_name: str) -> Dict[str, Any]:
        """Parse tournament information from wiki text."""
        info = {"name": tournament_name}

        # Parse infobox data using regex patterns
        patterns = {
            "prize_pool": r"\|(?:prizepool|prize.*pool)\s*=\s*([^\n|]+)",
            "start_date": r"\|(?:sdate|start.*date)\s*=\s*([^\n|]+)",
            "end_date": r"\|(?:edate|end.*date)\s*=\s*([^\n|]+)",
            "location": r"\|(?:location|venue)\s*=\s*([^\n|]+)",
            "organizer": r"\|(?:organizer|org)\s*=\s*([^\n|]+)",
            "format": r"\|(?:format|type)\s*=\s*([^\n|]+)"
        }

        for key, pattern in patterns.items():
            match = re.search(pattern, wiki_text, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                # Clean up wiki markup
                value = re.sub(r'\{\{.*?\}\}', '', value)  # Remove templates
                value = re.sub(r'\[\[([^|]*)\|([^\]]*)\]\]', r'\2', value)  # Wiki links
                value = re.sub(r'\[\[([^\]]*)\]\]', r'\1', value)  # Simple wiki links
                info[key] = value

        # Determine status based on dates
        try:
            if "start_date" in info and "end_date" in info:
                start = info["start_date"]
                end = info["end_date"]
                current_date = datetime.now().strftime("%Y-%m-%d")

                if start > current_date:
                    info["status"] = "Upcoming"
                elif end < current_date:
                    info["status"] = "Completed"
                else:
                    info["status"] = "Ongoing"
        except:
            info["status"] = "Unknown"

        return info

    async def get_upcoming_matches(self, tournament_name: str = None) -> list[Dict[str, Any]]:
        """Get upcoming matches from Liquipedia."""
        try:
            # Search for match pages or use a specific tournament page
            if tournament_name:
                # Get matches from a specific tournament page
                return await self._get_tournament_matches(tournament_name)
            else:
                # Get general upcoming matches
                return await self._get_general_matches()

        except Exception as e:
            _LOGGER.error("Error getting upcoming matches: %s", e)
            return []

    async def _get_tournament_matches(self, tournament_name: str) -> list[Dict[str, Any]]:
        """Get matches from a specific tournament page."""
        try:
            params = {
                "action": "query",
                "format": "json",
                "titles": tournament_name,
                "prop": "revisions",
                "rvprop": "content",
                "rvslots": "main"
            }

            async with self.session.get(self._base_url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    pages = data.get("query", {}).get("pages", {})

                    if pages:
                        page_id = next(iter(pages))
                        page_content = pages[page_id]

                        if "revisions" in page_content:
                            wiki_text = page_content["revisions"][0]["slots"]["main"]["*"]
                            return self._parse_matches_from_wiki(wiki_text, tournament_name)

                return []
        except Exception as e:
            _LOGGER.error("Error getting tournament matches: %s", e)
            return []

    async def _get_general_matches(self) -> list[Dict[str, Any]]:
        """Get general upcoming matches by searching recent changes."""
        try:
            # Get recent changes to find match pages
            params = {
                "action": "query",
                "format": "json",
                "list": "recentchanges",
                "rcnamespace": "0",  # Main namespace
                "rclimit": "50",
                "rcprop": "title|timestamp",
                "rcshow": "!bot"
            }

            matches = []
            async with self.session.get(self._base_url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    changes = data.get("query", {}).get("recentchanges", [])

                    # Filter for match-related pages
                    match_pages = [
                        change["title"] for change in changes
                        if any(keyword in change["title"].lower()
                              for keyword in ["match", "bracket", "tournament"])
                    ][:5]  # Limit to 5 recent match pages

                    # Get details for each match page
                    for page_title in match_pages:
                        page_matches = await self._get_tournament_matches(page_title)
                        matches.extend(page_matches[:2])  # Limit matches per page

            return matches[:10]  # Limit total matches

        except Exception as e:
            _LOGGER.error("Error getting general matches: %s", e)
            return []

    def _parse_matches_from_wiki(self, wiki_text: str, tournament_name: str) -> list[Dict[str, Any]]:
        """Parse match information from wiki text."""
        matches = []

        # Look for match templates and brackets
        match_patterns = [
            r'\{\{(?:Match|Bracket.*?)\s*\|([^}]+)\}\}',
            r'\|\s*team1\s*=\s*([^\n|]+).*?\|\s*team2\s*=\s*([^\n|]+)',
        ]

        for pattern in match_patterns:
            for match in re.finditer(pattern, wiki_text, re.IGNORECASE | re.DOTALL):
                try:
                    match_data = self._extract_match_data(match.group(0), tournament_name)
                    if match_data:
                        matches.append(match_data)
                except Exception as e:
                    _LOGGER.debug("Error parsing match: %s", e)
                    continue

        # If no matches found, create sample matches
        if not matches:
            matches = [{
                "team1": "TBD",
                "team2": "TBD",
                "time": "TBD",
                "format": "Unknown",
                "tournament": tournament_name
            }]

        return matches[:5]  # Limit to 5 matches

    def _extract_match_data(self, match_text: str, tournament_name: str) -> Dict[str, Any] | None:
        """Extract match data from a match template."""
        match_info = {"tournament": tournament_name}

        # Extract team names
        team1_match = re.search(r'team1\s*=\s*([^\n|]+)', match_text, re.IGNORECASE)
        team2_match = re.search(r'team2\s*=\s*([^\n|]+)', match_text, re.IGNORECASE)

        if team1_match and team2_match:
            match_info["team1"] = self._clean_team_name(team1_match.group(1))
            match_info["team2"] = self._clean_team_name(team2_match.group(1))
        else:
            return None

        # Extract time/date
        time_patterns = [
            r'date\s*=\s*([^\n|]+)',
            r'time\s*=\s*([^\n|]+)',
            r'datetime\s*=\s*([^\n|]+)'
        ]

        for pattern in time_patterns:
            time_match = re.search(pattern, match_text, re.IGNORECASE)
            if time_match:
                match_info["time"] = time_match.group(1).strip()
                break
        else:
            match_info["time"] = "TBD"

        # Extract format
        format_match = re.search(r'(?:format|type)\s*=\s*([^\n|]+)', match_text, re.IGNORECASE)
        if format_match:
            match_info["format"] = format_match.group(1).strip()
        else:
            match_info["format"] = "TBD"

        return match_info

    def _clean_team_name(self, team_name: str) -> str:
        """Clean team name from wiki markup."""
        # Remove wiki markup
        team_name = re.sub(r'\{\{.*?\}\}', '', team_name)  # Remove templates
        team_name = re.sub(r'\[\[([^|]*)\|([^\]]*)\]\]', r'\2', team_name)  # Wiki links with text
        team_name = re.sub(r'\[\[([^\]]*)\]\]', r'\1', team_name)  # Simple wiki links
        return team_name.strip()

    async def search_tournaments(self, query: str, limit: int = 10) -> list[Dict[str, Any]]:
        """Search for tournaments on Liquipedia."""
        try:
            params = {
                "action": "query",
                "format": "json",
                "list": "search",
                "srsearch": f"tournament {query}",
                "srnamespace": "0",  # Main namespace only
                "srlimit": str(limit),
                "srprop": "titlesnippet|snippet"
            }

            async with self.session.get(self._base_url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    results = data.get("query", {}).get("search", [])

                    tournaments = []
                    for result in results:
                        tournaments.append({
                            "title": result.get("title", ""),
                            "snippet": result.get("snippet", ""),
                            "size": result.get("size", 0)
                        })

                    return tournaments
                else:
                    _LOGGER.error("Failed to search tournaments: %s", response.status)
                    return []

        except Exception as e:
            _LOGGER.error("Error searching tournaments: %s", e)
            return []
