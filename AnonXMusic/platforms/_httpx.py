#  Copyright (c) 2025 AshokShau
#  Licensed under the GNU AGPL v3.0: https://www.gnu.org/licenses/agpl-3.0.html
#  Part of the TgMusicBot project. All rights reserved where applicable.

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Union

import aiofiles
import httpx

import config
from AnonXMusic.logging import LOGGER


@dataclass
class DownloadResult:
    success: bool
    file_path: Optional[Path] = None
    error: Optional[str] = None


class HttpxClient:
    DEFAULT_TIMEOUT = 10
    DEFAULT_DOWNLOAD_TIMEOUT = 60
    CHUNK_SIZE = 8192  # 8KB chunks for streaming downloads
    MAX_RETRIES = 2
    BACKOFF_FACTOR = 1.0

    def __init__(
        self,
        timeout: int = DEFAULT_TIMEOUT,
        download_timeout: int = DEFAULT_DOWNLOAD_TIMEOUT,
        max_redirects: int = 0,
    ) -> None:
        """
        Initialize the HTTP client with configurable settings.

        Args:
            timeout: Timeout for general HTTP requests in seconds
            download_timeout: Timeout for file downloads in seconds
            max_redirects: Maximum number of redirects to follow (0 to disable)
        """
        self._timeout = timeout
        self._download_timeout = download_timeout
        self._max_redirects = max_redirects
        self._session = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=max_redirects > 0,
            max_redirects=max_redirects,
        )

    async def download_file(
        self,
        url: str,
        file_path: Union[str, Path],
        overwrite: bool = False,
        **kwargs: Any,
    ) -> DownloadResult:
        """
        Download a file asynchronously with proper error handling.

        Args:
            url: URL of the file to download
            file_path: Path to save the downloaded file
            overwrite: Whether to overwrite an existing file

        Returns:
            DownloadResult: Contains success status and file path or error message
        """
        if not url:
            return DownloadResult(success=False, error="Empty URL provided")

        path = Path(file_path) if isinstance(file_path, str) else file_path
        if path.exists() and not overwrite:
            return DownloadResult(success=True, file_path=path)

        headers = kwargs.pop("headers", {})
        if config.API_URL and url.startswith(config.API_URL):
            headers["X-API-Key"] = config.API_KEY

        try:
            async with self._session.stream(
                "GET", url, timeout=self._download_timeout, headers=headers
            ) as response:
                response.raise_for_status()
                path.parent.mkdir(parents=True, exist_ok=True)
                async with aiofiles.open(path, "wb") as f:
                    async for chunk in response.aiter_bytes(self.CHUNK_SIZE):
                        await f.write(chunk)
            LOGGER(__name__).debug("Successfully downloaded file to %s", path)
            return DownloadResult(success=True, file_path=path)
        except Exception as e:
            error_msg = self._handle_http_error(e, url)
            LOGGER(__name__).error(error_msg)
            return DownloadResult(success=False, error=error_msg)

    @staticmethod
    def _handle_http_error(e: Exception, url: str) -> str:
        if isinstance(e, httpx.TooManyRedirects):
            return f"Too many redirects for {url}: {e}"
        elif isinstance(e, httpx.HTTPStatusError):
            return f"HTTP error {e.response.status_code} for {url}"
        elif isinstance(e, httpx.RequestError):
            return f"Request failed for {url}: {e}"
        return f"Unexpected error for {url}: {e}"
