"""Support for Liquipedia sensors."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import LiquipediaConfigEntry
from .const import DOMAIN
from .coordinator import LiquipediaDataUpdateCoordinator

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: LiquipediaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Liquipedia sensor platform."""
    # The integration already performed the coordinator's first refresh.
    # Updating again here can wait for the API rate limit and exceed the
    # entity platform's startup timeout.
    async_add_entities(
        [LiquipediaUpcomingMatchSensor(config_entry.runtime_data, config_entry)]
    )


class LiquipediaUpcomingMatchSensor(
    CoordinatorEntity[LiquipediaDataUpdateCoordinator], SensorEntity
):
    """Sensor showing the next upcoming match."""

    def __init__(
        self,
        coordinator: LiquipediaDataUpdateCoordinator,
        config_entry: LiquipediaConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_name = f"{coordinator.label} Upcoming Match"
        self._attr_unique_id = f"{config_entry.entry_id}_upcoming_match"
        self._attr_device_class = SensorDeviceClass.TIMESTAMP
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry.entry_id)},
            name=f"Liquipedia {coordinator.label}",
            manufacturer="Liquipedia",
            model=coordinator.label,
        )

    @property
    def native_value(self) -> datetime | None:
        """Return the state of the sensor."""
        match = self._upcoming_match
        if match is None:
            return None
        return match["date"]

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the state attributes."""
        match = self._upcoming_match
        attributes = self.coordinator.match_attributes(match)
        if match is None:
            return attributes or None
        attributes.update(
            title=match["title"],
            team1=match["team1"],
            team2=match["team2"],
            tournament=match.get("tournament") or self.coordinator.tournament,
            best_of=match.get("best_of"),
            last_updated=self.coordinator.data.updated_at.isoformat(),
        )
        return attributes

    @property
    def _upcoming_match(self) -> dict[str, Any] | None:
        """Return the next match that has not started."""
        if self.coordinator.data is None:
            return None
        now = dt_util.utcnow()
        return next(
            (
                match
                for match in self.coordinator.data.matches
                if match["date"] >= now
                and match.get("status") not in {"live", "finished"}
            ),
            None,
        )
