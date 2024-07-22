"""Test configuration for DoorBird tests."""

from collections.abc import Callable, Coroutine, Generator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock, patch

from doorbirdpy import DoorBird, DoorBirdScheduleEntry
import pytest

from homeassistant.components.doorbird.const import CONF_EVENTS, DOMAIN
from homeassistant.core import HomeAssistant

from . import VALID_CONFIG, get_mock_doorbird_api

from tests.common import MockConfigEntry, load_json_value_fixture

type DoorbirdMockerType = Callable[[], Coroutine[Any, Any, MockDoorbirdEntry]]


@dataclass
class MockDoorbirdEntry:
    """Mock DoorBird config entry."""

    entry: MockConfigEntry
    api: MagicMock


@pytest.fixture(scope="session")
def doorbird_info() -> dict[str, Any]:
    """Return a loaded DoorBird info fixture."""
    return load_json_value_fixture("info.json", "doorbird")["BHA"]["VERSION"][0]


@pytest.fixture(scope="session")
def doorbird_schedule() -> list[DoorBirdScheduleEntry]:
    """Return a loaded DoorBird schedule fixture."""
    return DoorBirdScheduleEntry.parse_all(
        load_json_value_fixture("schedule.json", "doorbird")
    )


@pytest.fixture
def doorbird_api(
    doorbird_info: dict[str, Any], doorbird_schedule: dict[str, Any]
) -> Generator[DoorBird]:
    """Mock the DoorBirdAPI."""
    api = get_mock_doorbird_api(info=doorbird_info, schedule=doorbird_schedule)
    with patch_doorbird_api_entry_points(api):
        yield api


@contextmanager
def patch_doorbird_api_entry_points(api: MagicMock) -> Generator[DoorBird]:
    """Mock the DoorBirdAPI."""
    with (
        patch(
            "homeassistant.components.doorbird.DoorBird",
            return_value=api,
        ),
        patch(
            "homeassistant.components.doorbird.config_flow.DoorBird",
            return_value=api,
        ),
    ):
        yield api


@pytest.fixture
async def doorbird_mocker(
    hass: HomeAssistant,
    doorbird_info: dict[str, Any],
    doorbird_schedule: dict[str, Any],
) -> DoorbirdMockerType:
    """Create a MockDoorbirdEntry."""

    async def _async_mock(
        entry: MockConfigEntry | None = None,
        api: DoorBird | None = None,
        info: dict[str, Any] | None = None,
        info_side_effect: Exception | None = None,
        schedule: list[DoorBirdScheduleEntry] | None = None,
        favorites_side_effect: Exception | None = None,
    ) -> MockDoorbirdEntry:
        """Create a MockDoorbirdEntry from defaults or specific values."""
        entry = entry or MockConfigEntry(
            domain=DOMAIN,
            unique_id="1CCAE3AAAAAA",
            data=VALID_CONFIG,
            options={CONF_EVENTS: ["event1", "event2", "event3"]},
        )
        api = api or get_mock_doorbird_api(
            info=info or doorbird_info,
            info_side_effect=info_side_effect,
            schedule=schedule or doorbird_schedule,
            favorites_side_effect=favorites_side_effect,
        )
        entry.add_to_hass(hass)
        with patch_doorbird_api_entry_points(api):
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()
        return MockDoorbirdEntry(entry=entry, api=api)

    return _async_mock
