from homeassistant.components.scene import Scene
from .const import DOMAIN


async def async_setup_entry(
    hass,
    entry,
    async_add_entities,
    discovery_info=None,
):
    data = hass.data[DOMAIN][entry.entry_id]
    devices = data["devices"]
    api = data["api"]

    scenes = []

    for device in devices:
        if "SCENE" in device.get("type", []):
            scenes.append(BuildTrackScene(device))

    async_add_entities(scenes)


class BuildTrackScene(Scene):

    def __init__(self, device):
        self._device = device
        self._attr_name = device.get("entityName")
        self._attr_unique_id = device.get("entityId")

    async def async_activate(self, **kwargs):
        # Later call your API here
        pass
