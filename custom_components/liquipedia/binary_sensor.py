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

from .const import DOMAIN
from .coordinator import LiquipediaDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Liquipedia binary sensor platform."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    async_add_entities(
        [LiquipediaMatchRunningBinarySensor(coordinator, config_entry)],
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
        self._attr_name = f"{coordinator.label} Match Running"
        self._attr_unique_id = f"{config_entry.entry_id}_match_running"
        self._attr_device_class = BinarySensorDeviceClass.RUNNING
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry.entry_id)},
            name=f"Liquipedia {coordinator.label}",
            manufacturer="Liquipedia",
            model=coordinator.label,
        )

    @property
    def _current_match(self) -> dict[str, Any] | None:
        """Return the match Liquipedia explicitly marks as live."""
        if self.coordinator.data is None:
            return None
        for match in reversed(self.coordinator.data.matches):
            if match.get("status") == "live":
                return match
        return None

    @property
    def is_on(self) -> bool | None:
        """Return whether a match is currently running."""
        if self._current_match is not None:
            return True
        if self.coordinator.data is None or self.coordinator.data.unavailable_games:
            return None
        return False

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the current match details."""
        match = self._current_match
        attributes = self.coordinator.match_attributes(match)
        if match is None:
            return attributes or None
        attributes.update(
            title=match["title"],
            team1=match["team1"],
            team2=match["team2"],
            best_of=match.get("best_of"),
        )
        return attributes
