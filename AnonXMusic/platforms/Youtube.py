import asyncio
import os
import random
import re
from pathlib import Path
from typing import Union, Optional

import yt_dlp
from pyrogram import errors
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from youtubesearchpython.__future__ import VideosSearch

from AnonXMusic.logging import LOGGER
from AnonXMusic.platforms._httpx import HttpxClient
from AnonXMusic.utils.database import is_on_off
from AnonXMusic.utils.formatters import time_to_seconds
from config import API_URL, API_KEY

class YouTubeUtils:
    @staticmethod
    def get_cookie_file() -> Optional[str]:
        """Get a random cookie file from the cookies directory."""
        cookie_dir = "AnonXMusic/assets"
        try:
            if not os.path.exists(cookie_dir):
                LOGGER(__name__).warning("Cookie directory '%s' does not exist.", cookie_dir)
                return None

            files = os.listdir(cookie_dir)
            cookies_files = [f for f in files if f.endswith(".txt")]

            if not cookies_files:
                LOGGER(__name__).warning("No cookie files found in '%s'.", cookie_dir)
                return None

            random_file = random.choice(cookies_files)
            return os.path.join(cookie_dir, random_file)
        except Exception as e:
            LOGGER(__name__).warning("Error accessing cookie directory: %s", e)
            return None

    @staticmethod
    async def download_with_api(video_id: str, is_video: bool = False) -> Optional[Path]:
        """
        Download using external API (supports Telegram database + CDN fallback).
        Works with updated response structure and auto file extension.
        """
        if not API_URL or not API_KEY:
            LOGGER(__name__).warning("API URL or KEY not set")
            return None
        if not video_id:
            LOGGER(__name__).warning("Video ID is None")
            return None

        from AnonXMusic import app
        # Extract video ID if a full URL is provided
        if re.match(r"^https?://", video_id):
            match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", video_id)
            if match:
                video_id = match.group(1)
            else:
                LOGGER(__name__).warning("Could not extract video ID from URL")
                return None

        api_url = f"{API_URL}/yt?api_key={API_KEY}&id={video_id}"

        try:
            get_track = await asyncio.wait_for(HttpxClient().make_request(api_url), timeout=20)
            if not get_track:
                LOGGER(__name__).error("API response is empty")
                return None

            source = get_track.get("source")
            data = get_track.get("results")

            # ✅ Source: Telegram Database (t.me link)
            if source == "database":
                if not isinstance(data, str) or "t.me" not in data:
                    LOGGER(__name__).error("Invalid database response: %s", data)
                    return None

                try:
                    # Extract channel username and message ID from t.me URL
                    match = re.search(r"t\.me\/([^\/]+)/(\d+)", data)
                    if not match:
                        LOGGER(__name__).error("Could not parse Telegram link: %s", data)
                        return None

                    channel_username, msg_id = match.groups()
                    msg_id = int(msg_id)

                    msg = await app.get_messages(chat_id=channel_username, message_ids=msg_id)
                    if not msg:
                        LOGGER(__name__).error("Message not found in Telegram index")
                        return None

                    path = await msg.download()
                    return Path(path) if path else None

                except errors.FloodWait as e:
                    await asyncio.sleep(e.value + 5)
                    return await YouTubeUtils.download_with_api(video_id, is_video)
                except Exception as e:
                    LOGGER(__name__).error(f"Error fetching Telegram message: {e}")
                    return None

            # ✅ Source: Fallback Download API
            elif source == "download_api":
                if not isinstance(data, dict):
                    LOGGER(__name__).error("Invalid download_api data: %s", data)
                    return None

                cdn_url = data.get("downloadUrl")
                if not cdn_url:
                    LOGGER(__name__).error("Missing CDN download URL in response")
                    return None

                file_type = data.get("type", "audio")
                ext = ".mp4" if file_type == "video" or is_video else ".mp3"

                dl = await HttpxClient().download_file(cdn_url)
                if dl and dl.success:
                    final_path = Path(dl.file_path)
                    renamed_path = final_path.with_suffix(ext)
                    try:
                        os.rename(final_path, renamed_path)
                        return renamed_path
                    except Exception as e:
                        LOGGER(__name__).warning("Rename failed: %s", e)
                        return final_path
                return None
            # ❌ Unknown source
            LOGGER(__name__).warning("Unknown API source: %s", source)
            return None

        except asyncio.TimeoutError:
            LOGGER(__name__).error("API request timed out after 20 seconds")
            return None
        except Exception as e:
            LOGGER(__name__).error(f"Error during API request: {e}")
            return None


class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.status = "https://www.youtube.com/oembed?url="
        self.listbase = "https://youtube.com/playlist?list="
        self.reg = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

    async def exists(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        return bool(re.search(self.regex, link))

    async def url(self, message_1: Message) -> Union[str, None]:
        messages = [message_1]
        if message_1.reply_to_message:
            messages.append(message_1.reply_to_message)
        text = ""
        offset = None
        length = None
        for message in messages:
            if offset:
                break
            if message.entities:
                for entity in message.entities:
                    if entity.type == MessageEntityType.URL:
                        text = message.text or message.caption
                        offset, length = entity.offset, entity.length
                        break
            elif message.caption_entities:
                for entity in message.caption_entities:
                    if entity.type == MessageEntityType.TEXT_LINK:
                        return entity.url
        if offset in (None,):
            return None
        return text[offset: offset + length]

    async def details(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = VideosSearch(link, limit=1)
        for result in (await results.next())["result"]:
            title = result["title"]
            duration_min = result["duration"]
            thumbnail = result["thumbnails"][0]["url"].split("?")[0]
            vidid = result["id"]
            duration_sec = int(time_to_seconds(duration_min)) if duration_min else 0
        return title, duration_min, duration_sec, thumbnail, vidid

    async def title(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = VideosSearch(link, limit=1)
        for result in (await results.next())["result"]:
            return result["title"]

    async def duration(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = VideosSearch(link, limit=1)
        for result in (await results.next())["result"]:
            return result["duration"]

    async def thumbnail(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = VideosSearch(link, limit=1)
        for result in (await results.next())["result"]:
            return result["thumbnails"][0]["url"].split("?")[0]

    async def video(self, link: str, videoid: Union[bool, str] = None):
        if dl := await YouTubeUtils.download_with_api(link, True):
            return True, str(dl)

        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        proc = await asyncio.create_subprocess_exec(
            "yt-dlp",
            "--cookies", YouTubeUtils.get_cookie_file(),
            "-g",
            "-f",
            "best[height<=?720][width<=?1280]",
            f"{link}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if stdout:
            return 1, stdout.decode().split("\n")[0]
        else:
            return 0, stderr.decode()

    async def playlist(self, link, limit, user_id, videoid: Union[bool, str] = None):
        if videoid:
            link = self.listbase + link
        if "&" in link:
            link = link.split("&")[0]
        playlist = await shell_cmd(
            f"yt-dlp -i --get-id --flat-playlist --playlist-end {limit} --skip-download {link}"
        )
        try:
            result = playlist.split("\n")
            result = [r for r in result if r]
        except:
            result = []
        return result

    async def track(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = VideosSearch(link, limit=1)
        for result in (await results.next())["result"]:
            title = result["title"]
            duration_min = result["duration"]
            vidid = result["id"]
            yturl = result["link"]
            thumbnail = result["thumbnails"][0]["url"].split("?")[0]
        track_details = {
            "title": title,
            "link": yturl,
            "vidid": vidid,
            "duration_min": duration_min,
            "thumb": thumbnail,
        }
        return track_details, vidid

    async def formats(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        ytdl_opts = {"quiet": True}
        ydl = yt_dlp.YoutubeDL(ytdl_opts)
        with ydl:
            formats_available = []
            r = ydl.extract_info(link, download=False)
            for format in r["formats"]:
                try:
                    str(format["format"])
                except:
                    continue
                if "dash" not in str(format["format"]).lower():
                    try:
                        format["format"]
                        format["filesize"]
                        format["format_id"]
                        format["ext"]
                        format["format_note"]
                    except:
                        continue
                    formats_available.append(
                        {
                            "format": format["format"],
                            "filesize": format["filesize"],
                            "format_id": format["format_id"],
                            "ext": format["ext"],
                            "format_note": format["format_note"],
                            "yturl": link,
                        }
                    )
        return formats_available, link

    async def slider(self, link: str, query_type: int, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        a = VideosSearch(link, limit=10)
        result = (await a.next()).get("result")
        title = result[query_type]["title"]
        duration_min = result[query_type]["duration"]
        vidid = result[query_type]["id"]
        thumbnail = result[query_type]["thumbnails"][0]["url"].split("?")[0]
        return title, duration_min, thumbnail, vidid

    async def download(
        self,
        link: str,
        mystic,
        video: Union[bool, str] = None,
        videoid: Union[bool, str] = None,
        songaudio: Union[bool, str] = None,
        songvideo: Union[bool, str] = None,
        format_id: Union[bool, str] = None,
        title: Union[bool, str] = None,
    ) -> str:
        if videoid:
            link = self.base + link
        loop = asyncio.get_running_loop()

        def audio_dl():
            ydl_optssx = {
                "format": "bestaudio/best",
                "outtmpl": "downloads/%(id)s.%(ext)s",
                "geo_bypass": True,
                "nocheckcertificate": True,
                "quiet": True,
                "cookiefile": YouTubeUtils.get_cookie_file(),
                "no_warnings": True,
            }
            x = yt_dlp.YoutubeDL(ydl_optssx)
            info = x.extract_info(link, False)
            xyz = os.path.join("downloads", f"{info['id']}.{info['ext']}")
            if os.path.exists(xyz):
                return xyz
            x.download([link])
            return xyz

        def video_dl():
            ydl_optssx = {
                "format": "(bestvideo[height<=?720][width<=?1280][ext=mp4])+(bestaudio[ext=m4a])",
                "outtmpl": "downloads/%(id)s.%(ext)s",
                "geo_bypass": True,
                "cookiefile": YouTubeUtils.get_cookie_file(),
                "nocheckcertificate": True,
                "quiet": True,
                "no_warnings": True,
            }
            x = yt_dlp.YoutubeDL(ydl_optssx)
            info = x.extract_info(link, False)
            xyz = os.path.join("downloads", f"{info['id']}.{info['ext']}")
            if os.path.exists(xyz):
                return xyz
            x.download([link])
            return xyz

        def song_video_dl():
            formats = f"{format_id}+140"
            fpath = f"downloads/{title}"
            ydl_optssx = {
                "format": formats,
                "outtmpl": fpath,
                "geo_bypass": True,
                "nocheckcertificate": True,
                "cookiefile": YouTubeUtils.get_cookie_file(),
                "quiet": True,
                "no_warnings": True,
                "prefer_ffmpeg": True,
                "merge_output_format": "mp4",
            }
            x = yt_dlp.YoutubeDL(ydl_optssx)
            x.download([link])

        def song_audio_dl():
            fpath = f"downloads/{title}.%(ext)s"
            ydl_optssx = {
                "format": format_id,
                "outtmpl": fpath,
                "geo_bypass": True,
                "nocheckcertificate": True,
                "quiet": True,
                "no_warnings": True,
                "cookiefile": YouTubeUtils.get_cookie_file(),
                "prefer_ffmpeg": True,
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }
                ],
            }
            x = yt_dlp.YoutubeDL(ydl_optssx)
            x.download([link])

        if songvideo:
            if dl := await YouTubeUtils.download_with_api(link, True):
                return str(dl)
            await loop.run_in_executor(None, song_video_dl)
            fpath = f"downloads/{title}.mp4"
            return fpath
        elif songaudio:
            if dl := await YouTubeUtils.download_with_api(link):
                return str(dl)
            await loop.run_in_executor(None, song_audio_dl)
            fpath = f"downloads/{title}.mp3"
            return fpath
        elif video:
            if await is_on_off(1):
                direct = True
                downloaded_file = await loop.run_in_executor(None, video_dl)
            else:
                if dl := await YouTubeUtils.download_with_api(link, True):
                    return str(dl), None
                proc = await asyncio.create_subprocess_exec(
                    "yt-dlp",
                    "--cookies", YouTubeUtils.get_cookie_file(),
                    "-g",
                    "-f",
                    "best[height<=?720][width<=?1280]",
                    f"{link}",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                if stdout:
                    downloaded_file = stdout.decode().split("\n")[0]
                    direct = None
                else:
                    return
        else:
            direct = True
            if dl := await YouTubeUtils.download_with_api(link):
                return str(dl), direct
            downloaded_file = await loop.run_in_executor(None, audio_dl)
        return downloaded_file, direct
