"""Support for Liquipedia binary sensors."""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_GAME, DOMAIN
from .sensor import LiquipediaDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Liquipedia binary sensor platform."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    async_add_entities(
        [LiquipediaMatchRunningBinarySensor(coordinator, config_entry)],
        True,
    )


class LiquipediaMatchRunningBinarySensor(
    CoordinatorEntity[LiquipediaDataUpdateCoordinator], BinarySensorEntity
):
    """Binary sensor reporting an explicitly live Liquipedia match."""

    def __init__(
        self,
        coordinator: LiquipediaDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._game = config_entry.data[CONF_GAME]
        self._attr_name = f"{self._game.title()} Match Running"
        self._attr_unique_id = f"{config_entry.entry_id}_match_running"
        self._attr_device_class = BinarySensorDeviceClass.RUNNING

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information about this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._config_entry.entry_id)},
            name=f"Liquipedia {self._game.title()}",
            manufacturer="Liquipedia",
            model=self._game.title(),
        )

    @property
    def _current_match(self) -> dict[str, Any] | None:
        """Return the match Liquipedia explicitly marks as live."""
        for match in reversed(self.coordinator.data):
            if match.get("status") == "live":
                return match
        return None

    @property
    def is_on(self) -> bool:
        """Return whether a match is currently running."""
        return self._current_match is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the current match details."""
        match = self._current_match
        if match is None:
            return None
        return {
            "title": match["title"],
            "team1": match["team1"],
            "team2": match["team2"],
            "best_of": match.get("best_of"),
        }
