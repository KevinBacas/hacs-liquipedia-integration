"""Support for Liquipedia sensors."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import aiohttp
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util import dt as dt_util

from .api import LiquipediaAPI
from .const import (
    CONF_GAME,
    CONF_TOURNAMENT,
    DOMAIN,
    DEFAULT_UPDATE_INTERVAL,
    USER_AGENT,
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

    async_add_entities([LiquipediaUpcomingMatchSensor(coordinator, config_entry)], True)


class LiquipediaDataUpdateCoordinator(DataUpdateCoordinator[list[dict[str, Any]]]):
    """Class to manage fetching data from Liquipedia."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.game = config_entry.data[CONF_GAME]
        self.tournament = config_entry.data[CONF_TOURNAMENT]
        self.api = LiquipediaAPI(
            self.game,
            async_create_clientsession(
                hass,
                headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"},
            ),
        )

        super().__init__(
            hass,
            _LOGGER,
            name=f"Liquipedia {self.game}",
            update_interval=timedelta(seconds=DEFAULT_UPDATE_INTERVAL),
        )

    async def _async_update_data(self) -> list[dict[str, Any]]:
        """Fetch data from Liquipedia."""
        try:
            return await self.api.get_upcoming_matches(self.tournament)
        except (aiohttp.ClientError, ValueError) as exception:
            raise UpdateFailed(f"Error communicating with API: {exception}") from exception


class LiquipediaSensor(CoordinatorEntity, SensorEntity):
    """Base class for Liquipedia sensors."""

    def __init__(self, coordinator: LiquipediaDataUpdateCoordinator, config_entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._game = config_entry.data[CONF_GAME]
        self._tournament = config_entry.data.get(CONF_TOURNAMENT, "")

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information about this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._config_entry.entry_id)},
            name=f"Liquipedia {self._game.title()}",
            manufacturer="Liquipedia",
            model=self._game.title(),
        )


class LiquipediaUpcomingMatchSensor(LiquipediaSensor):
    """Sensor showing the next upcoming match."""

    def __init__(self, coordinator: LiquipediaDataUpdateCoordinator, config_entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, config_entry)
        self._attr_name = f"{self._game.title()} Upcoming Match"
        self._attr_unique_id = f"{config_entry.entry_id}_upcoming_match"
        self._attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self) -> datetime | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data[0]["date"]

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the state attributes."""
        if not self.coordinator.data:
            return None
        match = self.coordinator.data[0]
        return {
            "title": match["title"],
            "team1": match["team1"],
            "team2": match["team2"],
            "tournament": match.get("tournament") or self._tournament,
            "best_of": match.get("best_of"),
            "last_updated": dt_util.utcnow().isoformat(),
        }
