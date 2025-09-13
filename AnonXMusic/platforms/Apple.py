import re
from typing import Union

import aiohttp
from bs4 import BeautifulSoup
from youtubesearchpython.__future__ import VideosSearch


class AppleAPI:
    def __init__(self):
        self.regex = r"^(https:\/\/music.apple.com\/)(.*)$"
        self.base = "https://music.apple.com/in/playlist/"
        self.itunes_api = "https://itunes.apple.com/lookup?id={}"  # by track id

    async def valid(self, link: str):
        return bool(re.search(self.regex, link))

    async def _itunes_lookup(self, track_id: str):
        """
        Look up track info from iTunes API using track ID
        """
        url = self.itunes_api.format(track_id)
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                if not data.get("results"):
                    return None
                return data["results"][0]  # first track

    async def track(self, url, playid: Union[bool, str] = None):
        if playid:
            url = self.base + url

        try:
            track_id = url.split("/")[-1].split("?")[0]
        except Exception:
            return False

        itunes_data = await self._itunes_lookup(track_id)
        if not itunes_data:
            return False

        track_name = itunes_data.get("trackName")
        artist_name = itunes_data.get("artistName")
        album_name = itunes_data.get("collectionName")
        preview = itunes_data.get("previewUrl")
        artwork = itunes_data.get("artworkUrl100")

        if not track_name:
            return False

        query = f"{track_name} {artist_name}" if artist_name else track_name

        # YouTube search
        results = VideosSearch(query, limit=1)
        yt_results = await results.next()
        if not yt_results.get("result"):
            return False

        data = yt_results["result"][0]
        track_details = {
            # YouTube details
            "title": data["title"],
            "link": data["link"],
            "vidid": data["id"],
            "duration_min": data["duration"],
            "thumb": data["thumbnails"][0]["url"].split("?")[0],
            # Apple Music details
            "apple_title": track_name,
            "apple_artist": artist_name,
            "apple_album": album_name,
            "apple_preview": preview,
            "apple_artwork": artwork,
        }
        return track_details, data["id"]

    async def playlist(self, url, playid: Union[bool, str] = None):
        if playid:
            url = self.base + url

        playlist_id = url.split("playlist/")[1]

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    return False
                html = await response.text()

        soup = BeautifulSoup(html, "html.parser")
        applelinks = soup.find_all("meta", attrs={"property": "music:song"})

        results = []
        for item in applelinks:
            song_url = item.get("content")
            if not song_url:
                continue

            try:
                track_id = song_url.split("/")[-1].split("?")[0]
                itunes_data = await self._itunes_lookup(track_id)
                if not itunes_data:
                    continue

                track_name = itunes_data.get("trackName")
                artist_name = itunes_data.get("artistName")
                album_name = itunes_data.get("collectionName")
                preview = itunes_data.get("previewUrl")
                artwork = itunes_data.get("artworkUrl100")

                query = f"{track_name} {artist_name}" if artist_name else track_name

                yt = VideosSearch(query, limit=1)
                yt_res = await yt.next()
                if not yt_res.get("result"):
                    continue

                data = yt_res["result"][0]
                results.append({
                    # YouTube details
                    "title": data["title"],
                    "link": data["link"],
                    "vidid": data["id"],
                    "duration_min": data["duration"],
                    "thumb": data["thumbnails"][0]["url"].split("?")[0],
                    # Apple Music details
                    "apple_title": track_name,
                    "apple_artist": artist_name,
                    "apple_album": album_name,
                    "apple_preview": preview,
                    "apple_artwork": artwork,
                })
            except Exception:
                continue

        return results, playlist_id
