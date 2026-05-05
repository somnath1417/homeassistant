import asyncio
import logging

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    HVACMode,
    HVACAction,
    ClimateEntityFeature,
)
from homeassistant.const import UnitOfTemperature

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities, discovery_info=None):
    """Set up BuildTrack Climate platform."""
    data = hass.data[DOMAIN][entry.entry_id]
    devices = data["devices"]
    api = data["api"]

    climates = []

    for device in devices:
        if "THERMOSTAT" in device.get("type", []):
            climates.append(BuildTrackClimate(hass, api, device))

    async_add_entities(climates)


class BuildTrackClimate(ClimateEntity):
    """BuildTrack Thermostat Entity."""

    def __init__(self, hass, api, device):
        self._hass = hass
        self._api = api
        self._device = device

        self._entity_id = device.get("entityId")
        self._entity_key = device.get("entityKey")

        self._attr_name = device.get("entityName")
        self._attr_unique_id = self._entity_id

        self._temp_task = None  # For delay handling

        # -----------------------------
        # Temperature Settings
        # -----------------------------
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_current_temperature = 24
        self._attr_target_temperature = 26
        self._attr_min_temp = 18
        self._attr_max_temp = 32
        self._attr_target_temperature_step = 1

        # -----------------------------
        # HVAC Modes
        # -----------------------------
        self._attr_hvac_modes = [
            HVACMode.COOL,
            HVACMode.HEAT,
            HVACMode.OFF,
        ]
        self._attr_hvac_mode = HVACMode.OFF
        self._attr_hvac_action = HVACAction.OFF

        # -----------------------------
        # Fan Modes
        # -----------------------------
        self._attr_fan_modes = ["low", "medium", "high"]
        self._attr_fan_mode = "low"

        # -----------------------------
        # Supported Features
        # -----------------------------
        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.FAN_MODE
        )

    # -------------------------------------------------
    # TEMPERATURE (API ENABLED WITH DELAY)
    # -------------------------------------------------

    async def async_set_temperature(self, **kwargs):
        """Handle temperature change from UI."""
        temperature = kwargs.get("temperature")

        if temperature is None:
            _LOGGER.warning(
                "Temperature not provided | Entity: %s",
                self.entity_id,
            )
            return

        # Update UI immediately
        self._attr_target_temperature = temperature
        self.async_write_ha_state()

        # Cancel previous delayed task
        if self._temp_task:
            self._temp_task.cancel()

        # Create delayed task
        self._temp_task = asyncio.create_task(
            self._delayed_temperature_call(temperature)
        )

    async def _delayed_temperature_call(self, temperature):
        """Delay API call to avoid rapid requests."""
        try:
            await asyncio.sleep(0.5)

            _LOGGER.info(
                "START: Setting temperature | Entity: %s | Requested: %s",
                self.entity_id,
                temperature,
            )

            response = await self._api.call(
                endpoint=f"/setTemperature/{self._entity_id}",
                method="POST",
                payload={
                    "entityId": self._entity_id,
                    "entityKey": self._entity_key,
                    "temperature": temperature,
                },
            )

            _LOGGER.warning("🔥 RAW API RESPONSE: %s", response)

            if response:
                _LOGGER.info(
                    "SUCCESS: Temperature updated | Entity: %s | Target: %s",
                    self.entity_id,
                    temperature,
                )
            else:
                _LOGGER.error(
                    "FAILED: Temperature API failure | Entity: %s",
                    self.entity_id,
                )

        except asyncio.CancelledError:
            pass

        except Exception as err:
            _LOGGER.exception(
                "ERROR: Exception while setting temperature | Entity: %s | Error: %s",
                self.entity_id,
                err,
            )

    # -------------------------------------------------
    # HVAC MODE (API ENABLED)
    # -------------------------------------------------

    async def async_set_hvac_mode(self, hvac_mode):
        _LOGGER.info(
            "START: Setting HVAC mode | Entity: %s | Mode: %s",
            self.entity_id,
            hvac_mode,
        )

        if hvac_mode not in self._attr_hvac_modes:
            _LOGGER.warning(
                "Invalid HVAC mode | Entity: %s | Mode: %s",
                self.entity_id,
                hvac_mode,
            )
            return

        command_map = {
            HVACMode.COOL: "COOL",
            HVACMode.HEAT: "HEAT",
            HVACMode.OFF: "OFF",
        }

        command = command_map.get(hvac_mode)

        try:
            response = await self._api.call(
                endpoint=f"/controlDevice/{self._entity_id}",
                method="POST",
                payload={
                    "entityId": self._entity_id,
                    "entityKey": self._entity_key,
                    "state": command,
                },
            )

            _LOGGER.warning("🔥 HVAC RAW RESPONSE: %s", response)

            if response:
                self._attr_hvac_mode = hvac_mode

                if hvac_mode == HVACMode.COOL:
                    self._attr_hvac_action = HVACAction.COOLING
                elif hvac_mode == HVACMode.HEAT:
                    self._attr_hvac_action = HVACAction.HEATING
                else:
                    self._attr_hvac_action = HVACAction.OFF

                self.async_write_ha_state()
            else:
                _LOGGER.error(
                    "FAILED: HVAC API failure | Entity: %s",
                    self.entity_id,
                )

        except Exception as err:
            _LOGGER.exception(
                "ERROR: HVAC exception | Entity: %s | Error: %s",
                self.entity_id,
                err,
            )

    # -------------------------------------------------
    # FAN MODE (API ENABLED)
    # -------------------------------------------------

    async def async_set_fan_mode(self, fan_mode):
        _LOGGER.info(
            "START: Setting Fan Mode | Entity: %s | Mode: %s",
            self.entity_id,
            fan_mode,
        )

        if fan_mode not in self._attr_fan_modes:
            _LOGGER.warning(
                "Invalid fan mode | Entity: %s | Mode: %s",
                self.entity_id,
                fan_mode,
            )
            return

        fan_command_map = {
            "low": "FAN_LOW",
            "medium": "FAN_MEDIUM",
            "high": "FAN_HIGH",
        }

        command = fan_command_map.get(fan_mode)

        try:
            response = await self._api.call(
                endpoint=f"/controlDevice/{self._entity_id}",
                method="POST",
                payload={
                    "entityId": self._entity_id,
                    "entityKey": self._entity_key,
                    "state": command,
                    "speed": self._attr_target_temperature,
                },
            )

            _LOGGER.warning("🔥 FAN RAW RESPONSE: %s", response)

            if response:
                self._attr_fan_mode = fan_mode
                self.async_write_ha_state()
            else:
                _LOGGER.error(
                    "FAILED: Fan API failure | Entity: %s",
                    self.entity_id,
                )

        except Exception as err:
            _LOGGER.exception(
                "ERROR: Fan exception | Entity: %s | Error: %s",
                self.entity_id,
                err,
            )
