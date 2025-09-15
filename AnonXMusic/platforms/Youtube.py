import asyncio
import os
import random
import re
from pathlib import Path
from typing import Optional, Union

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
    async def download_with_api(video_id: str, is_video: bool = False) -> Optional[Path]:
        """
        Download audio/video using the API.
        Handles both public and private Telegram channel links.
        Waits 3–6 seconds if file isn't in database before attempting direct download.
        """
        if not API_URL or not API_KEY:
            LOGGER(__name__).warning("API_URL or API_KEY is None")
            return None
        if not video_id:
            LOGGER(__name__).warning("Video ID is None")
            return None

        try:
            from AnonXMusic import app  # Local import to avoid circular dependency

            api_url = f"{API_URL}?api_key={API_KEY}&id={video_id}"
            res = await HttpxClient().make_request(api_url)

            if not res:
                LOGGER(__name__).error("API response empty")
                return None

            source = res.get("source", "")
            result_url = res.get("results")
            msg_text = res.get("message", "")

            if not result_url:
                LOGGER(__name__).error(f"No 'results' in API response. Message: {msg_text}")
                return None

            # Case 1: Video exists in database (Telegram message) - Handle public/private links
            if source == "database" and re.match(r"https:\/\/t\.me\/(?:c\/)?([a-zA-Z0-9_-]+)\/(\d+)", result_url):
                match = re.match(r"https:\/\/t\.me\/(?:c\/)?([a-zA-Z0-9_-]+)\/(\d+)", result_url)
                chat_part, msg_id = match.groups()
                try:
                    if chat_part.startswith("c/"):  # Private channel: Convert to numeric chat_id
                        channel_id = chat_part.split('/')[-1]  # Extract the numeric part after 'c/'
                        chat_id = int(f"-100{channel_id}")
                    else:  # Public channel: Use username
                        chat_id = chat_part
                    
                    msg_obj = await app.get_messages(chat_id, int(msg_id))
                    if msg_obj:
                        return await msg_obj.download()
                except errors.FloodWait as e:
                    await asyncio.sleep(e.value + 0)
                    return await YouTubeUtils.download_with_api(video_id, is_video)
                except Exception as e:
                    LOGGER(__name__).error(f"Telegram fetch error: {e}")
                    return None

            # Case 2: File isn't in database → direct download
            if source == "download_api" or result_url.startswith("https://"):
                # Wait 3–6 seconds before downloading
                wait_time = random.randint(1, 3)
                LOGGER(__name__).info(f"File not in database, waiting {wait_time}s before downloading from API...")
                await asyncio.sleep(wait_time)

                dl = await HttpxClient().download_file(result_url)
                if dl.success:
                    return dl.file_path
                else:
                    LOGGER(__name__).error(f"Download failed for URL: {result_url}")
                    return None

            LOGGER(__name__).error(f"Unsupported API source or invalid URL: {source}, {result_url}")
            return None

        except Exception as e:
            LOGGER(__name__).error(f"API error: {e}")
            return None


async def shell_cmd(cmd: str) -> str:
    """
    Execute a shell command asynchronously and return its output.
    Args:
        cmd (str): The shell command to execute.
    Returns:
        str: The decoded stdout or stderr output of the command.
    """
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, errorz = await proc.communicate()
    if errorz:
        error_str = errorz.decode("utf-8").lower()
        if "unavailable videos are hidden" in error_str:
            return out.decode("utf-8")
        return error_str
    return out.decode("utf-8")



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

        def is_restricted() -> bool:
            cookie_file = YouTubeUtils.get_cookie_file()
            return bool(cookie_file and os.path.exists(cookie_file))

        common_opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": False,
            "geo_bypass": True,
            "geo_bypass_country": "IN",
            "concurrent_fragment_downloads": 8,
            "cookiefile": YouTubeUtils.get_cookie_file() if is_restricted() else None,
        }

        def audio_dl():
            opts = {
                **common_opts,
                "format": "bestaudio[ext=m4a]/bestaudio/best",
                "outtmpl": "downloads/%(id)s.%(ext)s",
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }],
            }
            x = yt_dlp.YoutubeDL(opts)
            info = x.extract_info(link, download=False)
            xyz = os.path.join("downloads", f"{info['id']}.mp3")
            if os.path.exists(xyz):
                return xyz
            x.download([link])
            return xyz

        def video_dl():
            format_str = "best[height<=720]/bestvideo[height<=720]+bestaudio/best[height<=720]"
            if format_id:
                format_str = format_id
            opts = {
                **common_opts,
                "format": format_str,
                "outtmpl": "downloads/%(id)s.%(ext)s",
                "merge_output_format": "mp4",
                "prefer_ffmpeg": True,
            }
            x = yt_dlp.YoutubeDL(opts)
            info = x.extract_info(link, download=False)
            xyz = os.path.join("downloads", f"{info['id']}.mp4")
            if os.path.exists(xyz):
                return xyz
            x.download([link])
            return xyz

        def song_video_dl():
            formats = f"{format_id}+140"
            fpath = f"downloads/{title}"
            opts = {
                **common_opts,
                "format": formats,
                "outtmpl": fpath,
                "merge_output_format": "mp4",
                "prefer_ffmpeg": True,
            }
            x = yt_dlp.YoutubeDL(opts)
            x.download([link])
            return f"{fpath}.mp4"

        def song_audio_dl():
            fpath = f"downloads/{title}.%(ext)s"
            opts = {
                **common_opts,
                "format": format_id,
                "outtmpl": fpath,
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }],
                "prefer_ffmpeg": True,
            }
            x = yt_dlp.YoutubeDL(opts)
            x.download([link])
            return f"{fpath.split('%(ext)s')[0]}.mp3"

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
            direct = True
            if dl := await YouTubeUtils.download_with_api(link):
                return str(dl), direct
            downloaded_file = await loop.run_in_executor(None, audio_dl)
        return downloaded_file, direct
