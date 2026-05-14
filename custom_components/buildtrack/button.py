from homeassistant.components.button import ButtonEntity
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN


async def async_setup_entry(
    hass,
    entry,
    async_add_entities,
):
    data = hass.data[DOMAIN][entry.entry_id]

    api = data["api"]
    devices = data["devices"]

    location = None

    for device in devices:
        if device.get("location"):
            location = device.get("location")
            break

    async_add_entities(
        [
            BuildTrackRefreshButton(
                hass,
                api,
                devices,
                location,
            )
        ]
    )


class BuildTrackRefreshButton(ButtonEntity):

    def __init__(
        self,
        hass,
        api,
        devices,
        location,
    ):
        self._hass = hass
        self._api = api
        self._devices = devices
        self._location = location

        self._attr_name = "Refresh BuildTrack"
        self._attr_unique_id = "buildtrack_refresh_button"

    @property
    def suggested_area(self):
        return self._location

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, "buildtrack_refresh")},
            "name": "BuildTrack",
            "manufacturer": "BuildTrack",
            "model": "Refresh Controller",
        }

    async def async_press(self):
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
                print(
                    f"BuildTrack refresh failed "
                    f"for {entity_id}: {err}"
                )

        entity_registry = er.async_get(self._hass)

        for entity in entity_registry.entities.values():
            if entity.platform != DOMAIN:
                continue

            self._hass.async_create_task(
                self._hass.helpers.entity_component.async_update_entity(
                    entity.entity_id
                )
            )
