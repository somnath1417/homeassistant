import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .api import BuildTrackAPI

PLATFORMS = ["light", "scene", "climate"]

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Load BuildTrack YAML config."""
    hass.data.setdefault(DOMAIN, {})

    conf = config.get(DOMAIN)
    if conf is None:
        _LOGGER.warning("BuildTrack YAML config not found")
        return True

    client_id = conf.get("client_id")
    client_secret = conf.get("client_secret")

    if not client_id or not client_secret:
        _LOGGER.error("BuildTrack client_id/client_secret missing in configuration.yaml")
        return False

    hass.data[DOMAIN]["client_id"] = client_id
    hass.data[DOMAIN]["client_secret"] = client_secret

    _LOGGER.warning("BuildTrack YAML credentials loaded successfully")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up BuildTrack from config entry."""
    hass.data.setdefault(DOMAIN, {})

    client_id = hass.data[DOMAIN].get("client_id")
    client_secret = hass.data[DOMAIN].get("client_secret")
    access_token = entry.data.get("access_token")
    _LOGGER.info("Somnath ==========================> :%s", access_token)

    refresh_token = entry.data.get("refresh_token")

    if not client_id or not client_secret:
        _LOGGER.error("BuildTrack client_id/client_secret missing in hass.data")
        return False

    if not access_token:
        _LOGGER.error("BuildTrack access_token missing in config entry")
        return False

    api = BuildTrackAPI(
        hass=hass,
        client_id=client_id,
        client_secret=client_secret,
        access_token=access_token,
        refresh_token=refresh_token,
    )

    try:
        devices = await api.call(
            endpoint="/getDevices",
            method="GET",
            response_key="devices",
        )
    except Exception as err:
        _LOGGER.exception("Failed to fetch BuildTrack devices during setup: %s", err)
        return False

    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "devices": devices or [],
        "client_id": client_id,
        "client_secret": client_secret,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": entry.data.get("token_type"),
        "expires_in": entry.data.get("expires_in"),
        "redirect_uri": entry.data.get("redirect_uri"),
        "scope": entry.data.get("scope"),
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _LOGGER.warning("BuildTrack entry setup completed: %s", entry.entry_id)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload BuildTrack config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok and DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
        hass.data[DOMAIN].pop(entry.entry_id)

    _LOGGER.warning("BuildTrack entry unloaded: %s", entry.entry_id)
    return unload_ok



"""
from homeassistant.helpers.discovery import async_load_platform
from .const import DOMAIN
from .api import BuildTrackAPI

PLATFORMS = ["light", "scene", "climate"]


async def async_setup(hass, config):

    conf = config.get(DOMAIN)

    if conf is None:
        return True
    hass.data["client_id"] = conf.get("client_id")
    hass.data["client_secret"] = conf.get("client_secret")
    client_id = conf.get("client_id")
    client_secret = conf.get("client_secret")

    api = BuildTrackAPI(hass, client_id, client_secret)

    devices = await api.call(
        endpoint="/getDevices",
        method="GET",
        response_key="devices",
    )

    hass.data[DOMAIN] = {
        "api": api,
        "devices": devices or [],
    }

    for platform in PLATFORMS:
        hass.async_create_task(
            async_load_platform(hass, platform, DOMAIN, {}, config)
        )

    return True

"""
