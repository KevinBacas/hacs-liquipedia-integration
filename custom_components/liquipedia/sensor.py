"""Support for Liquipedia sensors."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    CONF_GAME,
    CONF_TOURNAMENT,
    DEFAULT_UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Liquipedia sensor platform."""
    coordinator = LiquipediaDataUpdateCoordinator(hass, config_entry)
    await coordinator.async_config_entry_first_refresh()

    entities = [
        LiquipediaTournamentSensor(coordinator, config_entry),
        LiquipediaUpcomingMatchesSensor(coordinator, config_entry),
    ]

    async_add_entities(entities, True)


class LiquipediaDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from Liquipedia."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.game = config_entry.data[CONF_GAME]
        self.tournament = config_entry.data.get(CONF_TOURNAMENT, "")
        
        super().__init__(
            hass,
            _LOGGER,
            name=f"Liquipedia {self.game}",
            update_interval=timedelta(seconds=DEFAULT_UPDATE_INTERVAL),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from Liquipedia."""
        try:
            # TODO: Implement actual API calls to Liquipedia
            # For now, return mock data
            return {
                "tournament_info": {
                    "name": "World Championship 2024",
                    "status": "Ongoing",
                    "prize_pool": "$2,000,000",
                    "start_date": "2024-10-01",
                    "end_date": "2024-11-01",
                },
                "upcoming_matches": [
                    {
                        "team1": "Team A",
                        "team2": "Team B",
                        "time": "2024-01-24T18:00:00Z",
                        "format": "Bo3",
                    },
                    {
                        "team1": "Team C", 
                        "team2": "Team D",
                        "time": "2024-01-24T20:00:00Z",
                        "format": "Bo5",
                    },
                ],
            }
        except Exception as exception:
            raise UpdateFailed(f"Error communicating with API: {exception}")


class LiquipediaSensor(CoordinatorEntity, SensorEntity):
    """Base class for Liquipedia sensors."""

    def __init__(self, coordinator: LiquipediaDataUpdateCoordinator, config_entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._game = config_entry.data[CONF_GAME]
        self._tournament = config_entry.data.get(CONF_TOURNAMENT, "")

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information about this entity."""
        return {
            "identifiers": {(DOMAIN, self._config_entry.entry_id)},
            "name": f"Liquipedia {self._game.title()}",
            "manufacturer": "Liquipedia",
            "model": self._game.title(),
        }


class LiquipediaTournamentSensor(LiquipediaSensor):
    """Sensor for tournament information."""

    def __init__(self, coordinator: LiquipediaDataUpdateCoordinator, config_entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, config_entry)
        self._attr_name = f"{self._game.title()} Tournament Info"
        self._attr_unique_id = f"{config_entry.entry_id}_tournament"

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        
        tournament_info = self.coordinator.data.get("tournament_info", {})
        return tournament_info.get("name", "Unknown")

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the state attributes."""
        if not self.coordinator.data:
            return None
        
        tournament_info = self.coordinator.data.get("tournament_info", {})
        return {
            "status": tournament_info.get("status"),
            "prize_pool": tournament_info.get("prize_pool"),
            "start_date": tournament_info.get("start_date"),
            "end_date": tournament_info.get("end_date"),
            "last_updated": dt_util.utcnow().isoformat(),
        }


class LiquipediaUpcomingMatchesSensor(LiquipediaSensor):
    """Sensor for upcoming matches."""

    def __init__(self, coordinator: LiquipediaDataUpdateCoordinator, config_entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, config_entry)
        self._attr_name = f"{self._game.title()} Upcoming Matches"
        self._attr_unique_id = f"{config_entry.entry_id}_matches"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        
        matches = self.coordinator.data.get("upcoming_matches", [])
        return len(matches)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the state attributes."""
        if not self.coordinator.data:
            return None
        
        matches = self.coordinator.data.get("upcoming_matches", [])
        return {
            "matches": matches,
            "last_updated": dt_util.utcnow().isoformat(),
        }