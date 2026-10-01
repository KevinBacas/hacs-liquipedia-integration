"""Regression tests for rate-limited entity setup."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.liquipedia import async_setup_entry
from custom_components.liquipedia import binary_sensor, sensor
from custom_components.liquipedia.const import DOMAIN


@pytest.mark.asyncio
async def test_setup_reuses_first_refresh_for_both_entity_platforms():
    """Adding entities must not make another rate-limited API request.

    Model Home Assistant's update_before_add handling: requesting a second
    refresh during entity creation would fail this test, just as it can time
    out in Home Assistant while waiting for the 30-second API limit.
    """
    hass = MagicMock()
    hass.data = {}
    entry = MagicMock()
    entry.entry_id = "champions"
    entry.data = {"game": "valorant", "tournament": "VCT/2026/Champions"}
    coordinator = MagicMock()
    coordinator.data = [{"team1": "One", "team2": "Two"}]
    coordinator.async_config_entry_first_refresh = AsyncMock()
    coordinator.async_request_refresh = AsyncMock(
        side_effect=AssertionError("Redundant refresh during entity startup")
    )
    entities = []

    async def forward_entry_setups(config_entry, platforms):
        assert coordinator.async_config_entry_first_refresh.await_count == 1
        assert hass.data[DOMAIN][entry.entry_id]["coordinator"] is coordinator
        for platform in (sensor, binary_sensor):
            def add_entities(new_entities, update_before_add=False):
                assert update_before_add is False
                entities.extend(new_entities)
            await platform.async_setup_entry(hass, config_entry, add_entities)

    hass.config_entries.async_forward_entry_setups = AsyncMock(
        side_effect=forward_entry_setups
    )
    with patch(
        "custom_components.liquipedia.LiquipediaDataUpdateCoordinator",
        return_value=coordinator,
    ):
        assert await async_setup_entry(hass, entry) is True

    coordinator.async_config_entry_first_refresh.assert_awaited_once()
    coordinator.async_request_refresh.assert_not_awaited()
    assert len(entities) == 2
    assert all(entity.coordinator is coordinator for entity in entities)
