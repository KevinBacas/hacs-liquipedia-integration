"""Exercise the Liquipedia entry lifecycle through Home Assistant."""

from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from homeassistant import config_entries, loader
from homeassistant.const import STATE_OFF, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry, entity_registry

from custom_components.liquipedia.const import DOMAIN

UPCOMING_MATCH = "sensor.valorant_upcoming_match"
MATCH_RUNNING = "binary_sensor.valorant_match_running"


@pytest_asyncio.fixture
async def hass(tmp_path):
    """Provide a local Home Assistant instance with an empty config directory."""
    hass = HomeAssistant(str(tmp_path))
    loader.async_setup(hass)
    hass.config_entries = config_entries.ConfigEntries(hass, {})
    await hass.config_entries.async_initialize()
    await device_registry.async_load(hass)
    await entity_registry.async_load(hass)
    try:
        with (
            patch("custom_components.liquipedia.config_flow.async_get_clientsession"),
            patch("custom_components.liquipedia.coordinator.async_get_clientsession"),
        ):
            yield hass
    finally:
        await hass.async_stop(force=True)


@pytest.fixture
def legacy_entry():
    """Represent an existing tournament entry from before tracking modes."""
    return config_entries.ConfigEntry(
        data={
            "game": "valorant",
            "name": "My tournament",
            "tournament": "cup/Match_Schedule",
        },
        discovery_keys=MappingProxyType({}),
        domain=DOMAIN,
        minor_version=1,
        options=None,
        source=config_entries.SOURCE_USER,
        subentries_data=None,
        title="My tournament",
        unique_id="valorant_cup/Match_Schedule",
        version=1,
    )


@pytest.mark.asyncio
async def test_legacy_setup_and_options_reload_poll_once_per_load(hass, legacy_entry):
    """Reload filters through options while preserving both legacy entity IDs."""
    date = datetime.now(UTC).replace(microsecond=0) + timedelta(days=1)
    match = {"date": date, "title": "One vs Two", "team1": "One", "team2": "Two"}
    get_matches = AsyncMock(return_value=[match])
    with patch("custom_components.liquipedia.coordinator.LiquipediaAPI") as api:
        api.return_value.get_matches = get_matches
        await hass.config_entries.async_add(legacy_entry)
        await hass.async_block_till_done()

        assert legacy_entry.state is config_entries.ConfigEntryState.LOADED
        get_matches.assert_awaited_once_with("cup/Match_Schedule")
        assert hass.states.get(UPCOMING_MATCH).state == date.isoformat()
        assert hass.states.get(MATCH_RUNNING).state == STATE_OFF

        flow = await hass.config_entries.options.async_init(legacy_entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            flow["flow_id"], {"team_filter": "Other"}
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        await hass.async_block_till_done()

    assert legacy_entry.state is config_entries.ConfigEntryState.LOADED
    assert legacy_entry.title == "My tournament"
    assert legacy_entry.unique_id == "valorant_cup/Match_Schedule"
    assert get_matches.await_count == 2
    assert hass.states.get(UPCOMING_MATCH).state == STATE_UNKNOWN
    assert hass.states.get(MATCH_RUNNING).state == STATE_OFF

    assert await hass.config_entries.async_unload(legacy_entry.entry_id)
    assert legacy_entry.state is config_entries.ConfigEntryState.NOT_LOADED
    assert not hasattr(legacy_entry, "runtime_data")


@pytest.mark.asyncio
async def test_setup_retries_source_error_and_recovers_with_empty_schedule(hass, legacy_entry):
    """A fetch failure and an empty schedule produce different Home Assistant states."""
    get_matches = AsyncMock(side_effect=[TimeoutError(), [], TimeoutError(), []])
    with patch("custom_components.liquipedia.coordinator.LiquipediaAPI") as api:
        api.return_value.get_matches = get_matches
        await hass.config_entries.async_add(legacy_entry)

    assert legacy_entry.state is config_entries.ConfigEntryState.SETUP_RETRY
    assert hass.states.get(MATCH_RUNNING) is None
    assert not hasattr(legacy_entry, "runtime_data")

    with patch("custom_components.liquipedia.coordinator.LiquipediaAPI") as api:
        api.return_value.get_matches = get_matches
        assert await hass.config_entries.async_reload(legacy_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(UPCOMING_MATCH).state == STATE_UNKNOWN
    assert hass.states.get(MATCH_RUNNING).state == STATE_OFF

    await legacy_entry.runtime_data.async_refresh()
    assert hass.states.get(UPCOMING_MATCH).state == STATE_UNAVAILABLE
    assert hass.states.get(MATCH_RUNNING).state == STATE_UNAVAILABLE
    await legacy_entry.runtime_data.async_refresh()
    assert hass.states.get(UPCOMING_MATCH).state == STATE_UNKNOWN
    assert hass.states.get(MATCH_RUNNING).state == STATE_OFF
    assert await hass.config_entries.async_unload(legacy_entry.entry_id)


@pytest.mark.asyncio
async def test_manual_schedule_alias_aborts_against_legacy_entry(hass, legacy_entry):
    """The canonical title cannot create a second copy of a stored legacy entry."""
    with patch("custom_components.liquipedia.coordinator.LiquipediaAPI") as api:
        api.return_value.get_matches = AsyncMock(return_value=[])
        await hass.config_entries.async_add(legacy_entry)
    await hass.async_block_till_done()

    flow = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    flow_id = flow["flow_id"]
    await hass.config_entries.flow.async_configure(flow_id, {"mode": "tournament"})
    with patch("custom_components.liquipedia.config_flow.LiquipediaAPI") as api:
        api.return_value.get_tournaments = AsyncMock(return_value={})
        api.return_value.get_schedule_page = AsyncMock(return_value="Cup/Match Schedule")
        await hass.config_entries.flow.async_configure(flow_id, {"game": "valorant"})
        await hass.config_entries.flow.async_configure(flow_id, {"tournament": "manual-entry"})
        result = await hass.config_entries.flow.async_configure(flow_id, {"tournament": "Alias"})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert hass.config_entries.async_entries(DOMAIN) == [legacy_entry]
    assert await hass.config_entries.async_unload(legacy_entry.entry_id)
