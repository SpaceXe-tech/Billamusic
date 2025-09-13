
import re
import aiohttp
from typing import Union
from bs4 import BeautifulSoup
from youtubesearchpython.__future__ import VideosSearch


class AppleAPI:
    def __init__(self):
        self.regex = r"^(https:\/\/music\.apple\.com\/)(.*)$"
        self.base = "https://music.apple.com/in/playlist/"
        self.itunes_api = "https://itunes.apple.com/lookup?id={}"
        self.itunes_search_api = "https://itunes.apple.com/search?term={}&media=music&entity=song&limit=1"

    async def valid(self, link: str):
        return bool(re.search(self.regex, link))

    def _extract_track_id(self, url: str):
        """
        Extract track ID from Apple Music URL
        Examples:
        - https://music.apple.com/us/album/song-name/1234567890?i=0987654321
        - https://music.apple.com/us/song/song-name/0987654321
        """
        try:
            # For URLs with ?i= parameter (album tracks)
            if "?i=" in url:
                track_id = url.split("?i=")[1].split("&")[0]
                return track_id
            # For direct song URLs
            elif "/song/" in url:
                track_id = url.split("/")[-1].split("?")[0]
                return track_id
            # For album URLs, extract album ID
            elif "/album/" in url:
                album_id = url.split("/album/")[1].split("?")[0].split("/")[-1]
                return album_id
            # For playlist URLs
            elif "/playlist/" in url:
                playlist_id = url.split("/playlist/")[1].split("?")[0].split("/")[-1]
                return playlist_id
            else:
                return None
        except Exception:
            return None

    async def _itunes_lookup(self, track_id: str):
        """
        Look up track info from iTunes API using track ID
        Fixed to handle text/javascript MIME type
        """
        url = self.itunes_api.format(track_id)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        return None

                    # Fix: Override content_type to None to bypass MIME type check
                    # iTunes API returns text/javascript instead of application/json
                    data = await resp.json(content_type=None)

                    if not data.get("results"):
                        return None
                    return data["results"][0]  # first track
        except Exception as e:
            print(f"iTunes API Error: {str(e)}")
            return None

    async def _youtube_search(self, query: str):
        """
        Search YouTube for the given query
        """
        try:
            results = VideosSearch(query, limit=1)
            yt_results = await results.next()
            if not yt_results.get("result"):
                return None
            return yt_results["result"][0]
        except Exception:
            return None

    def _calculate_duration_min(self, duration_ms: int):
        """
        Convert milliseconds to MM:SS format
        """
        try:
            seconds = duration_ms // 1000
            minutes = seconds // 60
            remaining_seconds = seconds % 60
            return f"{minutes}:{remaining_seconds:02d}"
        except Exception:
            return "0:00"

    async def track(self, url: str, playid: Union[bool, str] = None):
        """
        Extract track information from Apple Music URL and find corresponding YouTube video
        """
        if playid:
            url = self.base + url

        track_id = self._extract_track_id(url)
        if not track_id:
            return False

        # Get track info from iTunes API
        itunes_data = await self._itunes_lookup(track_id)
        if not itunes_data:
            return False

        # Extract track metadata
        track_name = itunes_data.get("trackName") or itunes_data.get("collectionName")
        artist_name = itunes_data.get("artistName", "")
        album_name = itunes_data.get("collectionName", "")
        preview_url = itunes_data.get("previewUrl", "")
        artwork_url = itunes_data.get("artworkUrl100", "")
        duration_ms = itunes_data.get("trackTimeMillis", 0)
        genre = itunes_data.get("primaryGenreName", "")
        release_date = itunes_data.get("releaseDate", "")

        if not track_name:
            return False

        # Create search query for YouTube
        search_query = f"{track_name} {artist_name}".strip()

        # Search YouTube for the track
        yt_data = await self._youtube_search(search_query)
        if not yt_data:
            return False

        # Calculate duration in MM:SS format
        duration_min = self._calculate_duration_min(duration_ms)

        # Prepare track details
        track_details = {
            # YouTube details (for streaming)
            "title": yt_data["title"],
            "link": yt_data["link"],
            "vidid": yt_data["id"],
            "duration_min": yt_data.get("duration", duration_min),
            "thumb": yt_data["thumbnails"][0]["url"].split("?")[0] if yt_data.get("thumbnails") else artwork_url,

            # Apple Music metadata
            "apple_title": track_name,
            "apple_artist": artist_name,
            "apple_album": album_name,
            "apple_preview": preview_url,
            "apple_artwork": artwork_url,
            "apple_genre": genre,
            "apple_release_date": release_date,
            "apple_duration_ms": duration_ms,
        }

        return track_details, yt_data["id"]

    async def playlist(self, url: str, playid: Union[bool, str] = None):
        """
        Extract playlist information from Apple Music URL
        """
        if playid:
            url = self.base + url

        playlist_id = self._extract_track_id(url)
        if not playlist_id:
            return False

        try:
            # Fetch the playlist page
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as response:
                    if response.status != 200:
                        return False
                    html = await response.text()

            # Parse HTML to extract track URLs
            soup = BeautifulSoup(html, "html.parser")
            track_links = soup.find_all("meta", attrs={"property": "music:song"})

            results = []
            for item in track_links[:50]:  # Limit to 50 tracks to avoid timeouts
                song_url = item.get("content")
                if not song_url:
                    continue

                try:
                    # Extract track ID from the song URL
                    track_id = self._extract_track_id(song_url)
                    if not track_id:
                        continue

                    # Get track info from iTunes API
                    itunes_data = await self._itunes_lookup(track_id)
                    if not itunes_data:
                        continue

                    # Extract track metadata
                    track_name = itunes_data.get("trackName", "")
                    artist_name = itunes_data.get("artistName", "")
                    album_name = itunes_data.get("collectionName", "")
                    preview_url = itunes_data.get("previewUrl", "")
                    artwork_url = itunes_data.get("artworkUrl100", "")
                    duration_ms = itunes_data.get("trackTimeMillis", 0)
                    genre = itunes_data.get("primaryGenreName", "")

                    if not track_name:
                        continue

                    # Create search query for YouTube
                    search_query = f"{track_name} {artist_name}".strip()

                    # Search YouTube for the track
                    yt_data = await self._youtube_search(search_query)
                    if not yt_data:
                        continue

                    # Calculate duration in MM:SS format
                    duration_min = self._calculate_duration_min(duration_ms)

                    # Add to results
                    results.append({
                        # YouTube details (for streaming)
                        "title": yt_data["title"],
                        "link": yt_data["link"],
                        "vidid": yt_data["id"],
                        "duration_min": yt_data.get("duration", duration_min),
                        "thumb": yt_data["thumbnails"][0]["url"].split("?")[0] if yt_data.get("thumbnails") else artwork_url,

                        # Apple Music metadata
                        "apple_title": track_name,
                        "apple_artist": artist_name,
                        "apple_album": album_name,
                        "apple_preview": preview_url,
                        "apple_artwork": artwork_url,
                        "apple_genre": genre,
                        "apple_duration_ms": duration_ms,
                    })

                except Exception:
                    continue

            return results, playlist_id

        except Exception:
            return False

    async def album(self, url: str, playid: Union[bool, str] = None):
        """
        Extract album information from Apple Music URL
        """
        if playid:
            url = self.base + url

        album_id = self._extract_track_id(url)
        if not album_id:
            return False

        try:
            # Get album info and tracks from iTunes API
            lookup_url = f"https://itunes.apple.com/lookup?id={album_id}&entity=song"
            async with aiohttp.ClientSession() as session:
                async with session.get(lookup_url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        return False

                    # Fix: Override content_type to None to bypass MIME type check
                    data = await resp.json(content_type=None)

                    if not data.get("results"):
                        return False

            results = []
            # Skip the first result (album info) and process tracks
            for track_data in data["results"][1:]:
                try:
                    track_name = track_data.get("trackName", "")
                    artist_name = track_data.get("artistName", "")
                    album_name = track_data.get("collectionName", "")
                    preview_url = track_data.get("previewUrl", "")
                    artwork_url = track_data.get("artworkUrl100", "")
                    duration_ms = track_data.get("trackTimeMillis", 0)
                    genre = track_data.get("primaryGenreName", "")

                    if not track_name:
                        continue

                    # Create search query for YouTube
                    search_query = f"{track_name} {artist_name}".strip()

                    # Search YouTube for the track
                    yt_data = await self._youtube_search(search_query)
                    if not yt_data:
                        continue

                    # Calculate duration in MM:SS format
                    duration_min = self._calculate_duration_min(duration_ms)

                    # Add to results
                    results.append({
                        # YouTube details (for streaming)
                        "title": yt_data["title"],
                        "link": yt_data["link"],
                        "vidid": yt_data["id"],
                        "duration_min": yt_data.get("duration", duration_min),
                        "thumb": yt_data["thumbnails"][0]["url"].split("?")[0] if yt_data.get("thumbnails") else artwork_url,

                        # Apple Music metadata
                        "apple_title": track_name,
                        "apple_artist": artist_name,
                        "apple_album": album_name,
                        "apple_preview": preview_url,
                        "apple_artwork": artwork_url,
                        "apple_genre": genre,
                        "apple_duration_ms": duration_ms,
                    })

                except Exception:
                    continue

            return results, album_id

        except Exception:
            return False
