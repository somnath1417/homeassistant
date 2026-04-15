import logging
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .const import API_BASE_URL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class BuildTrackAPI:

    def __init__(self, hass, client_id=None, client_secret=None, access_token=None, refresh_token=None):
        self._hass = hass
        self._client_id = client_id
        self._client_secret = client_secret
        self._base_url = API_BASE_URL

        self._access_token = access_token
        self._refresh_token = refresh_token

        _LOGGER.warning(
            "BuildTrack API initialized | client_id=%s | access_token_exists=%s",
            self._client_id,
            bool(self._access_token),
        )
    async def call(
        self,
        endpoint,
        method="GET",
        payload=None,
        params=None,
        headers=None,
        response_key=None,
        success_status=200,
    ):

        url = f"{self._base_url}{endpoint}"

        default_headers = {
            "Accept": "application/json",
            "Authorization": self._access_token,
            "Content-Type": "application/json",
        }

        if headers:
            default_headers.update(headers)

        session = async_get_clientsession(self._hass)

        try:
            async with session.request(
                method=method,
                url=url,
                json=payload,
                params=params,
                headers=default_headers,
            ) as response:

                _LOGGER.debug(
                    "API CALL → %s %s | Status: %s",
                    method,
                    url,
                    response.status,
                )

                text = await response.text()

                if response.status != success_status:
                    _LOGGER.error(
                        "API ERROR → %s | Body: %s",
                        response.status,
                        text,
                    )
                    return None

                try:
                    data = await response.json()
                except Exception:
                    return text

                if response_key:
                    return data.get(response_key)

                return data

        except Exception as err:
            _LOGGER.error("API Exception: %s", err)
            return None
