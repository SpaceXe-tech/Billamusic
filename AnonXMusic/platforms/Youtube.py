import asyncio
import os
import random
import re
import base64
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

# Hardcoded API configuration
HARDCODED_API_URL = "https://api.thequickearn.xyz/stream"
HARDCODED_API_KEY = base64.b64encode("180DxNexGenBotsl8EE37".encode()).decode()

import re
from typing import Optional
from pathlib import Path

class YouTubeUtils:
    @staticmethod
    def get_cookie_file() -> Optional[str]:
        """Get a random cookie file from the 'cookies' directory, skipping 'cookie_time.txt'."""
        cookie_dir = "AnonXMusic/assets"
        try:
            if not os.path.exists(cookie_dir):
                LOGGER(__name__).warning("Cookie directory '%s' does not exist.", cookie_dir)
                return None

            files = os.listdir(cookie_dir)
            cookies_files = [f for f in files if f.endswith(".txt") and f != "cookie_time.txt"]

            if not cookies_files:
                LOGGER(__name__).warning("No cookie files found in '%s'.", cookie_dir)
                return None

            random_file = random.choice(cookies_files)
            return os.path.join(cookie_dir, random_file)

        except Exception as e:
            LOGGER(__name__).warning("Error accessing cookie directory: %s", e)
            return None

    @staticmethod
    async def download_with_hardcoded_api(video_id_or_url: str, is_video: bool = False) -> Optional[Path]:
        """
        Download audio/video using the hardcoded API endpoint.
        Falls back to the original API if hardcoded API fails.
        """
        if not video_id_or_url:
            LOGGER(__name__).warning("Video ID or URL is None")
            return None

        try:
            from AnonXMusic import app  # Local import inside function

            # Extract video_id if full YouTube URL given
            video_id = video_id_or_url
            yt_video_id_match = re.search(
                r"(?:v=|\/)([0-9A-Za-z_-]{11})(?:\&|$)", video_id_or_url
            )
            if yt_video_id_match:
                video_id = yt_video_id_match.group(1)
            elif re.match(r"^[0-9A-Za-z_-]{11}$", video_id_or_url):
                video_id = video_id_or_url  # Already a valid ID
            else:
                LOGGER(__name__).warning("Invalid video ID or URL format")
                return None

            # Try hardcoded API first
            try:
                decoded_api_key = base64.b64decode(HARDCODED_API_KEY).decode()
                hardcoded_url = f"{HARDCODED_API_URL}/{video_id}?api={decoded_api_key}"

                LOGGER(__name__).info(f"Trying hardcoded API: {HARDCODED_API_URL}")
                res = await HttpxClient().make_request(hardcoded_url)

                if res and res.get("success"):
                    result_url = res.get("download_url") or res.get("url") or res.get("stream_url")
                    if result_url:
                        LOGGER(__name__).info("Hardcoded API successful, downloading...")
                        dl = await HttpxClient().download_file(result_url)
                        if dl.success:
                            return dl.file_path

            except Exception as e:
                LOGGER(__name__).warning(f"Hardcoded API failed: {e}")

            # Fallback to original API logic (commented config API)
            # This preserves the original API_URL and API_KEY functionality
            try:
                from config import API_URL, API_KEY

                api_url = f"{API_URL}?api_key={API_KEY}&id={video_id}"
                res = await HttpxClient().make_request(api_url)

                if not res:
                    LOGGER(__name__).error("Fallback API response empty")
                    return None

                result_url = res.get("results")
                if not result_url:
                    LOGGER(__name__).error("No 'results' in fallback API response")
                    return None

                source = res.get("source", "")

                if source == "database" and re.match(r"https:\/\/t\.me\/([a-zA-Z0-9_]{5,})\/(\d+)", result_url):
                    try:
                        tg_match = re.match(r"https:\/\/t\.me\/([a-zA-Z0-9_]{5,})\/(\d+)", result_url)
                        if tg_match:
                            chat_username, msg_id = tg_match.groups()
                            msg_obj = await app.get_messages(chat_username, int(msg_id))
                            if msg_obj:
                                return await msg_obj.download()
                    except errors.FloodWait as e:
                        await asyncio.sleep(e.value + 0)
                        return await YouTubeUtils.download_with_hardcoded_api(video_id, is_video)
                    except Exception as e:
                        LOGGER(__name__).error(f"Telegram fetch error: {e}")
                        return None

                if source == "download_api" or (source == "" and re.match(r"https?://", result_url)):
                    dl = await HttpxClient().download_file(result_url)
                    return dl.file_path if dl.success else None

            except ImportError:
                LOGGER(__name__).warning("config module not found, skipping fallback API")
            except Exception as e:
                LOGGER(__name__).error(f"Fallback API error: {e}")

            return None

        except Exception as e:
            LOGGER(__name__).error(f"Download API error: {e}")
            return None

    @staticmethod
    async def download_with_api(video_id_or_url: str, is_video: bool = False) -> Optional[Path]:
        """
        Legacy method that now calls the hardcoded API method.
        Maintains backward compatibility.
        """
        return await YouTubeUtils.download_with_hardcoded_api(video_id_or_url, is_video)


async def shell_cmd(cmd):
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
        self.reg = re.compile(r"�(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

    async def exists(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if re.search(self.regex, link):
            return True
        else:
            return False

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
        return text[offset : offset + length]

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
            if str(duration_min) == "None":
                duration_sec = 0
            else:
                duration_sec = int(time_to_seconds(duration_min))
        return title, duration_min, duration_sec, thumbnail, vidid

    async def title(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = VideosSearch(link, limit=1)
        for result in (await results.next())["result"]:
            title = result["title"]
        return title

    async def duration(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = VideosSearch(link, limit=1)
        for result in (await results.next())["result"]:
            duration = result["duration"]
        return duration

    async def thumbnail(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = VideosSearch(link, limit=1)
        for result in (await results.next())["result"]:
            thumbnail = result["thumbnails"][0]["url"].split("?")[0]
        return thumbnail

    async def video(self, link: str, videoid: Union[bool, str] = None):
        # Try hardcoded API first, then fallback to yt-dlp
        if dl := await YouTubeUtils.download_with_hardcoded_api(link, True):
            return True, str(dl)

        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]

        cookie_file = YouTubeUtils.get_cookie_file()
        if not cookie_file:
            LOGGER(__name__).warning("No cookie file available for yt-dlp")

        proc = await asyncio.create_subprocess_exec(
            "yt-dlp",
            "--cookies", cookie_file or "",
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
            for key in result:
                if key == "":
                    result.remove(key)
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
                if not "dash" in str(format["format"]).lower():
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

    async def slider(
        self,
        link: str,
        query_type: int,
        videoid: Union[bool, str] = None,
    ):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        a = VideosSearch(link, limit=5)
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
            cookie_file = YouTubeUtils.get_cookie_file()
            ydl_optssx = {
                "format": "bestaudio/best",
                "outtmpl": "downloads/%(id)s.%(ext)s",
                "geo_bypass": True,
                "geo_bypass_country": "IN",  
                "nocheckcertificate": True,
                "quiet": True,
                "cookiefile": cookie_file,
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
            cookie_file = YouTubeUtils.get_cookie_file()
            ydl_optssx = {
                "format": "(bestvideo[height<=?720][width<=?1280][ext=mp4])+(bestaudio[ext=m4a])",
                "outtmpl": "downloads/%(id)s.%(ext)s",
                "geo_bypass": True,
                "cookiefile": cookie_file,
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
            cookie_file = YouTubeUtils.get_cookie_file()
            ydl_optssx = {
                "format": formats,
                "outtmpl": fpath,
                "geo_bypass": True,
                "nocheckcertificate": True,
                "cookiefile": cookie_file,
                "quiet": True,
                "no_warnings": True,
                "prefer_ffmpeg": True,
                "merge_output_format": "mp4",
            }
            x = yt_dlp.YoutubeDL(ydl_optssx)
            x.download([link])

        def song_audio_dl():
            fpath = f"downloads/{title}.%(ext)s"
            cookie_file = YouTubeUtils.get_cookie_file()
            ydl_optssx = {
                "format": format_id,
                "outtmpl": fpath,
                "geo_bypass": True,
                "geo_bypass_country": "IN",
                "nocheckcertificate": True,
                "quiet": True,
                "no_warnings": True,
                "cookiefile": cookie_file,
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
            # Try hardcoded API first
            if dl := await YouTubeUtils.download_with_hardcoded_api(link, True):
                return str(dl)
            # Fallback to yt-dlp
            await loop.run_in_executor(None, song_video_dl)
            fpath = f"downloads/{title}.mp4"
            return fpath

        elif songaudio:
            # Try hardcoded API first
            if dl := await YouTubeUtils.download_with_hardcoded_api(link):
                return str(dl)
            # Fallback to yt-dlp
            await loop.run_in_executor(None, song_audio_dl)
            fpath = f"downloads/{title}.webm"
            return fpath

        elif video:
            if await is_on_off(1):
                direct = True
                # Try hardcoded API first
                if dl := await YouTubeUtils.download_with_hardcoded_api(link, True):
                    return str(dl), direct
                # Fallback to yt-dlp download
                downloaded_file = await loop.run_in_executor(None, video_dl)
            else:
                # Try hardcoded API first
                if dl := await YouTubeUtils.download_with_hardcoded_api(link, True):
                    return str(dl), True

                cookie_file = YouTubeUtils.get_cookie_file()
                proc = await asyncio.create_subprocess_exec(
                    "yt-dlp",
                    "--cookies", cookie_file or "",
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
            # Try hardcoded API first
            if dl := await YouTubeUtils.download_with_hardcoded_api(link):
                return str(dl), direct
            # Fallback to yt-dlp
            downloaded_file = await loop.run_in_executor(None, audio_dl)

        return downloaded_file, direct
