import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def get_location(device):
    location = device.get("location")

    if location and str(location).strip():
        return str(location).strip()

    return None


async def ensure_area(hass, location):
    area_registry = ar.async_get(hass)

    area = area_registry.async_get_area_by_name(location)

    if area is None:
        area = area_registry.async_create(location)

    return area


async def assign_device_to_area(hass, device_identifier, location):
    if not location:
        return

    area = await ensure_area(hass, location)
    device_registry = dr.async_get(hass)

    device = device_registry.async_get_device(
        identifiers={(DOMAIN, device_identifier)}
    )

    if device and device.area_id != area.id:
        device_registry.async_update_device(
            device.id,
            area_id=area.id,
        )

        _LOGGER.warning(
            "BuildTrack button assigned to area %s",
            location,
        )


async def async_setup_entry(
    hass,
    entry,
    async_add_entities,
):
    data = hass.data[DOMAIN][entry.entry_id]

    api = data["api"]
    devices = data["devices"]

    devices_by_location = {}

    for device in devices:
        location = get_location(device)

        if not location:
            continue

        devices_by_location.setdefault(location, []).append(device)

    buttons = []

    for location, location_devices in devices_by_location.items():
        buttons.append(
            BuildTrackRefreshButton(
                hass=hass,
                api=api,
                location=location,
                devices=location_devices,
            )
        )

    async_add_entities(buttons)


class BuildTrackRefreshButton(ButtonEntity):

    def __init__(self, hass, api, location, devices):
        self._hass = hass
        self._api = api
        self._location = location
        self._devices = devices

        safe_location = location.lower().replace(" ", "_")

        self._device_identifier = f"buildtrack_refresh_{safe_location}"

        self._attr_name = f"BuildTrack Refresh - {location}"
        self._attr_unique_id = self._device_identifier

    @property
    def suggested_area(self):
        return self._location

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._device_identifier)},
            "name": f"BuildTrack Refresh - {self._location}",
            "manufacturer": "BuildTrack",
            "model": "Refresh Button",
        }

    async def async_added_to_hass(self):
        await assign_device_to_area(
            self._hass,
            self._device_identifier,
            self._location,
        )

    async def async_press(self):
        _LOGGER.warning(
            "BuildTrack refresh started for location %s",
            self._location,
        )

        for device in self._devices:
            entity_id = device.get("entityId")
            entity_key = device.get("entityKey")

            if not entity_id or not entity_key:
                continue

            try:
                await self._api.call(
                    endpoint="/readDeviceData",
                    method="POST",
                    payload={
                        "entityId": entity_id,
                        "entityKey": entity_key,
                    },
                )

            except Exception as err:
                _LOGGER.warning(
                    "BuildTrack refresh failed for %s | %s",
                    entity_id,
                    err,
                )
