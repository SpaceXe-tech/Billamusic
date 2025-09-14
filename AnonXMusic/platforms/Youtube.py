import asyncio
import os
import random
import re
import requests
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
from config import API_URL, API_KEY, LOGGER_ID


class YouTubeUtils:
    @staticmethod
    def get_cookie_file() -> Optional[str]:
        """Get a random cookie file from the 'AnonXMusic/assets' directory."""
        cookie_dir = "AnonXMusic/assets"
        try:
            if not os.path.exists(cookie_dir):
                return None
            files = os.listdir(cookie_dir)
            cookie_files = [f for f in files if f.endswith(".txt") and f != "cookie_time.txt"]
            if not cookie_files:
                return None
            return os.path.join(cookie_dir, random.choice(cookie_files))
        except Exception as e:
            LOGGER(__name__).error(f"Error accessing cookie files: {e}")
            return None

    @staticmethod
    async def download_with_main_api(video_id: str, is_video: bool = False) -> Optional[str]:
        """Download using the main API (video_id only)."""
        try:
            if not video_id:
                LOGGER(__name__).error("No video ID provided for main API download.")
                return None

            from AnonXMusic import app
            api_url = f"{API_URL}?api_key={API_KEY}&id={video_id}"
            res = await HttpxClient().make_request(api_url)

            if not res:
                LOGGER(__name__).error("Main API returned no response.")
                return None

            download_url = res.get("url") or res.get("results")
            if not download_url:
                LOGGER(__name__).error("Main API did not return a download URL.")
                return None

            source = res.get("source", "")

            # Handle Telegram source
            if source == "database" and re.match(r"https://t.me/([a-zA-Z0-9_]{5,})/(\d+)", download_url):
                try:
                    tg_match = re.match(r"https://t.me/([a-zA-Z0-9_]{5,})/(\d+)", download_url)
                    if tg_match:
                        chat_username, msg_id = tg_match.groups()
                        msg_obj = await app.get_messages(chat_username, int(msg_id))
                        if msg_obj:
                            return await msg_obj.download()
                except errors.FloodWait as e:
                    LOGGER(__name__).warning(f"FloodWait error, sleeping for {e.value} seconds.")
                    await asyncio.sleep(e.value)
                    return await YouTubeUtils.download_with_main_api(video_id, is_video)
                except Exception as e:
                    LOGGER(__name__).error(f"Telegram download error: {e}")
                    return None

            # Handle direct download URL
            if source == "download_api" or download_url.startswith("http"):
                download_result = await HttpxClient().download_file(download_url)
                if download_result.success:
                    return download_result.file_path

            LOGGER(__name__).error("Main API returned an invalid download URL.")
            return None

        except Exception as e:
            LOGGER(__name__).error(f"Main API download error: {e}")
            return None
    import os
    import re
    import requests
    @staticmethod
    async def download_with_fallback_api(video_id_or_url: str, is_video: bool = False) -> Optional[str]:
        """Download using the fallback API (accepts video ID or full URL without validation)."""
        try:
            # Construct full URL if input appears to be a video ID (no strict validation)
            if len(video_id_or_url) == 11:  # Assume 11-character input is a video ID
                video_url = f"https://www.youtube.com/watch?v={video_id_or_url}"
            else:
                video_url = video_id_or_url  # Use input directly if it’s not 11 characters

            api_endpoint = "https://ar-api-iauy.onrender.com/mp3youtube"
            format_param = "mp4" if is_video else "mp3"

            params = {
                "url": video_url,
                "format": format_param,
            }
            if not is_video:
                params["audioBitrate"] = "128"

            # Get JSON metadata from the API
            with requests.get(api_endpoint, params=params, timeout=30) as r:
                if r.status_code != 200:
                    LOGGER(__name__).error(f"Fallback API returned status code {r.status_code}.")
                    return None

                # Parse JSON to get download URL and filename
                try:
                    response_json = r.json()
                    download_url = response_json.get("data", {}).get("download", {}).get("url")
                    filename = response_json.get("data", {}).get("download", {}).get("filename", os.urandom(8).hex())
                except ValueError as e:
                    LOGGER(__name__).error(f"Failed to parse API response: {e}")
                    return None

                if not download_url:
                    LOGGER(__name__).error("No download URL found in API response.")
                    return None

            # Download the file from the download URL (no streaming)
            with requests.get(download_url, timeout=30) as r:
                if r.status_code != 200:
                    LOGGER(__name__).error(f"Download URL returned status code {r.status_code}.")
                    return None

                ext = "mp4" if is_video else "mp3"
                file_path = f"downloads/{filename}.{ext}"

                os.makedirs("downloads", exist_ok=True)
                # Write the entire content to file at once
                with open(file_path, "wb") as f:
                    f.write(r.content)  # Write full content instead of chunked streaming

                if os.path.exists(file_path):
                    return file_path

                LOGGER(__name__).error("Failed to save file from fallback API.")
                return None

        except Exception as e:
            LOGGER(__name__).error(f"Fallback API download error: {e}")
            return None

    @staticmethod
    async def download_with_api(video_id_or_url: str, is_video: bool = False) -> Optional[str]:
        """
        Try main API first (video_id only), if it fails → switch to fallback (video ID or URL).
        
        Args:
            video_id_or_url: Either a YouTube video ID (e.g., 'eryV8GvERnk') or a full URL.
            is_video: If True, download as video (mp4); otherwise, download as audio (mp3).
        
        Returns:
            Optional[str]: Path to the downloaded file or None if download fails.
        """
        if not video_id_or_url:
            LOGGER(__name__).error("No video ID or URL provided.")
            return None

        # Try main API with video_id (if input is likely a video ID)
        if len(video_id_or_url) == 11:  # Assume 11-character input is a video ID
            main_result = await YouTubeUtils.download_with_main_api(video_id_or_url, is_video)
            if main_result:
                return main_result
            LOGGER(__name__).warning(f"Main API failed for video ID: {video_id_or_url}. Falling back to fallback API.")
        
        # Fallback API (accepts video ID or URL)
        return await YouTubeUtils.download_with_fallback_api(video_id_or_url, is_video)

    @staticmethod
    async def shell_cmd(cmd):
        """Execute a shell command and return its output."""
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, errorz = await proc.communicate()
        if errorz:
            if "unavailable videos are hidden" in (errorz.decode("utf-8")).lower():
                return out.decode("utf-8")
            else:
                return errorz.decode("utf-8")
        return out.decode("utf-8")


class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.status = "https://www.youtube.com/oembed?url="
        self.listbase = "https://youtube.com/playlist?list="
        self.reg = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
        
    async def exists(self, link: str, videoid: Union[bool, str] = None):
        """Check if YouTube link is valid."""
        if videoid:
            link = self.base + link
        return bool(re.search(self.regex, link))

    async def url(self, message_1: Message) -> Union[str, None]:
        """Extract URL from message."""
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
        
        if offset is None:
            return None
        return text[offset:offset + length]

    async def details(self, link: str, videoid: Union[bool, str] = None):
        """Get video details."""
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
            if str(duration_min) == "None":
                duration_sec = 0
            else:
                duration_sec = int(time_to_seconds(duration_min))
        return title, duration_min, duration_sec, thumbnail, vidid

    async def title(self, link: str, videoid: Union[bool, str] = None):
        """Get video title."""
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
            
        results = VideosSearch(link, limit=1)
        for result in (await results.next())["result"]:
            title = result["title"]
        return title

    async def duration(self, link: str, videoid: Union[bool, str] = None):
        """Get video duration."""
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
            
        results = VideosSearch(link, limit=1)
        for result in (await results.next())["result"]:
            duration = result["duration"]
        return duration

    async def thumbnail(self, link: str, videoid: Union[bool, str] = None):
        """Get video thumbnail."""
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
            
        results = VideosSearch(link, limit=1)
        for result in (await results.next())["result"]:
            thumbnail = result["thumbnails"][0]["url"].split("?")[0]
        return thumbnail

    async def video(self, link: str, videoid: Union[bool, str] = None):
        """Get video stream URL or download."""
        # Try API download first
        if dl := await YouTubeUtils.download_with_api(link, True):
            return True, str(dl)
        # Fallback to yt-dlp stream URL
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
        """Get playlist video IDs."""
        if videoid:
            link = self.listbase + link
        if "&" in link:
            link = link.split("&")[0]
            
        playlist = await YouTubeUtils.shell_cmd(
            f"yt-dlp -i --get-id --flat-playlist --playlist-end {limit} --skip-download {link}"
        )
        
        try:
            result = playlist.split("\n")
            result = [key for key in result if key]
        except:
            result = []
        return result

    async def track(self, link: str, videoid: Union[bool, str] = None):
        """Get track details."""
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
        """Get available formats."""
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
                if not "dash" in str(format["format"]).lower():
                    try:
                        format["format"]
                        format["filesize"]
                        format["format_id"]
                        format["ext"]
                        format["format_note"]
                    except:
                        continue
                    formats_available.append({
                        "format": format["format"],
                        "filesize": format["filesize"],
                        "format_id": format["format_id"],
                        "ext": format["ext"],
                        "format_note": format["format_note"],
                        "yturl": link,
                    })
                    
        return formats_available, link

    async def slider(self, link: str, query_type: int, videoid: Union[bool, str] = None):
        """Get video from search results."""
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
        """Download video/audio."""
        if videoid:
            link = self.base + link
            
        loop = asyncio.get_running_loop()

        def audio_dl():
            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": "downloads/%(id)s.%(ext)s",
                "geo_bypass": True,
                "nocheckcertificate": True,
                "quiet": True,
                "cookiefile": YouTubeUtils.get_cookie_file(),
                "no_warnings": True,
            }
            x = yt_dlp.YoutubeDL(ydl_opts)
            info = x.extract_info(link, False)
            xyz = os.path.join("downloads", f"{info['id']}.{info['ext']}")
            if os.path.exists(xyz):
                return xyz
            x.download([link])
            return xyz

        def video_dl():
            ydl_opts = {
                "format": "(bestvideo[height<=?720][width<=?1280][ext=mp4])+(bestaudio[ext=webm])",
                "outtmpl": "downloads/%(id)s.%(ext)s",
                "geo_bypass": True,
                "cookiefile": YouTubeUtils.get_cookie_file(),
                "nocheckcertificate": True,
                "quiet": True,
                "no_warnings": True,
            }
            x = yt_dlp.YoutubeDL(ydl_opts)
            info = x.extract_info(link, False)
            xyz = os.path.join("downloads", f"{info['id']}.{info['ext']}")
            if os.path.exists(xyz):
                return xyz
            x.download([link])
            return xyz

        def song_audio_dl():
            filename = title or "audio"
            fpath = f"downloads/{filename}.%(ext)s"
            ydl_opts = {
                "format": format_id,
                "outtmpl": fpath,
                "geo_bypass": True,
                "nocheckcertificate": True,
                "quiet": True,
                "no_warnings": True,
                "cookiefile": YouTubeUtils.get_cookie_file(),
                "prefer_ffmpeg": True,
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }],
            }
            x = yt_dlp.YoutubeDL(ydl_opts)
            x.download([link])

        def song_video_dl():
            filename = title or "video"
            fpath = f"downloads/{filename}.%(ext)s"
            ydl_opts = {
                "format": format_id,
                "outtmpl": fpath,
                "geo_bypass": True,
                "nocheckcertificate": True,
                "quiet": True,
                "no_warnings": True,
                "cookiefile": YouTubeUtils.get_cookie_file(),
            }
            x = yt_dlp.YoutubeDL(ydl_opts)
            x.download([link])

        direct = True

        if songvideo:
            if dl := await YouTubeUtils.download_with_api(link, True):
                return str(dl)
            await loop.run_in_executor(None, song_video_dl)
            filename = title or "video"
            fpath = f"downloads/{filename}.mp4"
            return fpath
            
        elif songaudio:
            if dl := await YouTubeUtils.download_with_api(link):
                return str(dl)
            await loop.run_in_executor(None, song_audio_dl)
            filename = title or "audio"
            fpath = f"downloads/{filename}.mp3"
            return fpath
            
        elif video:
            if await is_on_off(1):
                downloaded_file = await loop.run_in_executor(None, video_dl)
            else:
                if dl := await YouTubeUtils.download_with_api(link, True):
                    return str(dl), direct

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
            if dl := await YouTubeUtils.download_with_api(link):
                return str(dl), direct
            downloaded_file = await loop.run_in_executor(None, audio_dl)
            
        return downloaded_file, direct
