import logging

from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)


class BuildTrackAPI:
    def __init__(
        self,
        hass,
        api_url,
        client_id=None,
        client_secret=None,
        access_token=None,
        refresh_token=None,
    ):
        self._hass = hass
        self._base_url = api_url.strip().rstrip("/")
        self._client_id = client_id
        self._client_secret = client_secret
        self._access_token = access_token
        self._refresh_token = refresh_token

        _LOGGER.warning(
            "BuildTrack API initialized | base_url=%s | client_id=%s | access_token_exists=%s",
            self._base_url,
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
        endpoint = endpoint if endpoint.startswith("/") else f"/{endpoint}"
        url = f"{self._base_url}{endpoint}"

        default_headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        if self._access_token:
            default_headers["Authorization"] = self._access_token

            # If your API needs Bearer token, use this instead:
            # default_headers["Authorization"] = f"Bearer {self._access_token}"

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
                text = await response.text()

                _LOGGER.debug(
                    "BuildTrack API CALL → %s %s | Status: %s",
                    method,
                    url,
                    response.status,
                )

                if response.status != success_status:
                    _LOGGER.error(
                        "BuildTrack API ERROR → %s %s | Status: %s | Body: %s",
                        method,
                        url,
                        response.status,
                        text[:1000],
                    )
                    return None

                try:
                    data = await response.json(content_type=None)
                except Exception:
                    return text

                if response_key:
                    return data.get(response_key)

                return data

        except Exception as err:
            _LOGGER.exception("BuildTrack API Exception: %s", err)
            return None

    async def get_devices(self):
        return await self.call(
            endpoint="/getDevices",
            method="GET",
        )

    async def control_device(self, entity_id, payload):
        return await self.call(
            endpoint=f"/controlDevice/{entity_id}",
            method="POST",
            payload=payload,
        )
