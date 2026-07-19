"""Tests for the Portainer sensor platform."""

from copy import deepcopy
from unittest.mock import AsyncMock, patch

from pyportainer.models.docker import DockerContainer
from pyportainer.models.docker_inspect import DockerInspect
import pytest
from syrupy.assertion import SnapshotAssertion

from homeassistant.const import STATE_UNKNOWN, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from . import setup_integration

from tests.common import MockConfigEntry, snapshot_platform


@pytest.fixture(autouse=True)
def enable_all_entities(entity_registry_enabled_by_default: None) -> None:
    """Make sure all entities are enabled."""


@pytest.mark.usefixtures("mock_portainer_client")
async def test_all_entities(
    hass: HomeAssistant,
    snapshot: SnapshotAssertion,
    mock_config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test all entities."""
    with patch(
        "homeassistant.components.portainer._PLATFORMS",
        [Platform.SENSOR],
    ):
        await setup_integration(hass, mock_config_entry)
        await snapshot_platform(
            hass,
            entity_registry,
            snapshot,
            mock_config_entry.entry_id,
        )


async def test_health_sensor_follows_same_name_container_replacements(
    hass: HomeAssistant,
    mock_portainer_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test health sensor support changing across same-name replacements."""
    container: DockerContainer = deepcopy(
        next(
            container
            for container in mock_portainer_client.get_containers.return_value
            if "/focused_einstein" in container.names
        )
    )
    inspect: DockerInspect = deepcopy(
        mock_portainer_client.inspect_container.return_value
    )
    inspect_without_health = deepcopy(inspect)
    assert inspect_without_health.state is not None
    inspect_without_health.state.health = None

    mock_portainer_client.get_containers.return_value = [container]
    mock_portainer_client.inspect_container.return_value = inspect_without_health

    with patch(
        "homeassistant.components.portainer._PLATFORMS",
        [Platform.SENSOR],
    ):
        await setup_integration(hass, mock_config_entry)

    entity_id = "sensor.focused_einstein_health"
    assert hass.states.get(entity_id) is None
    entity_count = len(
        er.async_entries_for_config_entry(entity_registry, mock_config_entry.entry_id)
    )

    coordinator = mock_config_entry.runtime_data

    async def _refresh_with(
        container_id: str, container_inspect: DockerInspect
    ) -> None:
        replacement = deepcopy(container)
        replacement.id = container_id
        mock_portainer_client.get_containers.return_value = [replacement]
        mock_portainer_client.inspect_container.return_value = container_inspect
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    await _refresh_with("replacement_with_health", inspect)

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "healthy"

    await _refresh_with("replacement_without_health", inspect_without_health)

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == STATE_UNKNOWN

    await _refresh_with("replacement_with_health_again", inspect)

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "healthy"
    assert (
        len(
            er.async_entries_for_config_entry(
                entity_registry, mock_config_entry.entry_id
            )
        )
        == entity_count + 1
    )
