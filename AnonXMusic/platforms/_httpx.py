#  Copyright (c) 2025 AshokShau
#  Licensed under the GNU AGPL v3.0: https://www.gnu.org/licenses/agpl-3.0.html
#  Part of the TgMusicBot project. All rights reserved where applicable.

import asyncio
from typing import Any, Optional

import httpx

import config
from AnonXMusic.logging import LOGGER


class HttpxClient:
    DEFAULT_TIMEOUT = 10
    MAX_RETRIES = 2
    BACKOFF_FACTOR = 1.0

    def __init__(
        self,
        timeout: int = DEFAULT_TIMEOUT,
        max_redirects: int = 0,
    ) -> None:
        self._timeout = timeout
        self._max_redirects = max_redirects
        self._session = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=max_redirects > 0,
            max_redirects=max_redirects,
        )

    async def make_request(
            self,
            url: str,
            max_retries: int = MAX_RETRIES,
            backoff_factor: float = BACKOFF_FACTOR,
            **kwargs: Any,
    ) -> Optional[dict[str, Any]]:
        if not url:
            LOGGER(__name__).warning("Empty URL provided")
            return None

        headers = kwargs.pop("headers", {})
        if config.API_URL and url.startswith(config.API_URL):
            headers["X-API-Key"] = config.API_KEY

        for attempt in range(max_retries):
            try:
                response = await self._session.get(url, headers=headers, **kwargs)
                response.raise_for_status()
                return response.json()

            except httpx.TooManyRedirects:
                error_msg = f"Redirect loop for {url}"
                if attempt == max_retries - 1:
                    LOGGER(__name__).error(error_msg)
                    return None
                LOGGER(__name__).warning(error_msg)

            except httpx.HTTPStatusError as e:
                error_msg = f"HTTP error {e.response.status_code} for {url}"
                if attempt == max_retries - 1:
                    LOGGER(__name__).error(error_msg)
                    return None
                LOGGER(__name__).warning(error_msg)

            except httpx.RequestError as e:
                error_msg = f"Request failed for {url}: {str(e)}"
                if attempt == max_retries - 1:
                    LOGGER(__name__).error(error_msg)
                    return None
                LOGGER(__name__).warning(error_msg)

            except ValueError as e:
                LOGGER(__name__).error("Invalid JSON response from %s: %s", url, str(e))
                return None

            except Exception as e:
                LOGGER(__name__).error("Unexpected error for %s: %s", url, str(e))
                return None
            await asyncio.sleep(backoff_factor * (2 ** attempt))

        return None
