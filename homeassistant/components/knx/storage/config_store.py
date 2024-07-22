"""KNX entity configuration store."""

from collections.abc import Callable
import logging
from typing import TYPE_CHECKING, Any, Final, TypedDict

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PLATFORM, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store
from homeassistant.util.ulid import ulid_now

from ..const import DOMAIN
from .const import CONF_DATA

if TYPE_CHECKING:
    from ..knx_entity import KnxEntity

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION: Final = 1
STORAGE_KEY: Final = f"{DOMAIN}/config_store.json"

KNXPlatformStoreModel = dict[str, dict[str, Any]]  # unique_id: configuration
KNXEntityStoreModel = dict[
    str, KNXPlatformStoreModel
]  # platform: KNXPlatformStoreModel


class KNXConfigStoreModel(TypedDict):
    """Represent KNX configuration store data."""

    entities: KNXEntityStoreModel


class KNXConfigStore:
    """Manage KNX config store data."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
    ) -> None:
        """Initialize config store."""
        self.hass = hass
        self._store = Store[KNXConfigStoreModel](hass, STORAGE_VERSION, STORAGE_KEY)
        self.data = KNXConfigStoreModel(entities={})

        # entities and async_add_entity are filled by platform setups
        self.entities: dict[str, KnxEntity] = {}  # unique_id as key
        self.async_add_entity: dict[
            Platform, Callable[[str, dict[str, Any]], None]
        ] = {}

    async def load_data(self) -> None:
        """Load config store data from storage."""
        if data := await self._store.async_load():
            self.data = KNXConfigStoreModel(**data)
            _LOGGER.debug(
                "Loaded KNX config data from storage. %s entity platforms",
                len(self.data["entities"]),
            )

    async def create_entity(
        self, platform: Platform, data: dict[str, Any]
    ) -> str | None:
        """Create a new entity."""
        if platform not in self.async_add_entity:
            raise ConfigStoreException(f"Entity platform not ready: {platform}")
        unique_id = f"knx_es_{ulid_now()}"
        self.async_add_entity[platform](unique_id, data)
        # store data after entity was added to be sure config didn't raise exceptions
        self.data["entities"].setdefault(platform, {})[unique_id] = data
        await self._store.async_save(self.data)

        entity_registry = er.async_get(self.hass)
        return entity_registry.async_get_entity_id(platform, DOMAIN, unique_id)

    @callback
    def get_entity_config(self, entity_id: str) -> dict[str, Any]:
        """Return KNX entity configuration."""
        entity_registry = er.async_get(self.hass)
        if (entry := entity_registry.async_get(entity_id)) is None:
            raise ConfigStoreException(f"Entity not found: {entity_id}")
        try:
            return {
                CONF_PLATFORM: entry.domain,
                CONF_DATA: self.data["entities"][entry.domain][entry.unique_id],
            }
        except KeyError as err:
            raise ConfigStoreException(f"Entity data not found: {entity_id}") from err

    async def update_entity(
        self, platform: Platform, entity_id: str, data: dict[str, Any]
    ) -> None:
        """Update an existing entity."""
        if platform not in self.async_add_entity:
            raise ConfigStoreException(f"Entity platform not ready: {platform}")
        entity_registry = er.async_get(self.hass)
        if (entry := entity_registry.async_get(entity_id)) is None:
            raise ConfigStoreException(f"Entity not found: {entity_id}")
        unique_id = entry.unique_id
        if (
            platform not in self.data["entities"]
            or unique_id not in self.data["entities"][platform]
        ):
            raise ConfigStoreException(
                f"Entity not found in storage: {entity_id} - {unique_id}"
            )
        await self.entities.pop(unique_id).async_remove()
        self.async_add_entity[platform](unique_id, data)
        # store data after entity is added to make sure config doesn't raise exceptions
        self.data["entities"][platform][unique_id] = data
        await self._store.async_save(self.data)

    async def delete_entity(self, entity_id: str) -> None:
        """Delete an existing entity."""
        entity_registry = er.async_get(self.hass)
        if (entry := entity_registry.async_get(entity_id)) is None:
            raise ConfigStoreException(f"Entity not found: {entity_id}")
        try:
            del self.data["entities"][entry.domain][entry.unique_id]
        except KeyError as err:
            raise ConfigStoreException(
                f"Entity not found in {entry.domain}: {entry.unique_id}"
            ) from err
        try:
            del self.entities[entry.unique_id]
        except KeyError:
            _LOGGER.warning("Entity not initialized when deleted: %s", entity_id)
        entity_registry.async_remove(entity_id)
        await self._store.async_save(self.data)

    def get_entity_entries(self) -> list[er.RegistryEntry]:
        """Get entity_ids of all configured entities by platform."""
        return [
            entity.registry_entry
            for entity in self.entities.values()
            if entity.registry_entry is not None
        ]


class ConfigStoreException(Exception):
    """KNX config store exception."""
