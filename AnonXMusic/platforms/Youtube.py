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
                return None

            files = os.listdir(cookie_dir)
            cookies_files = [f for f in files if f.endswith(".txt") and f != "cookie_time.txt"]

            if not cookies_files:
                return None

            random_file = random.choice(cookies_files)
            return os.path.join(cookie_dir, random_file)

        except Exception as e:
            return None

    @staticmethod
    def extract_video_id(url: str) -> Optional[str]:
        """
        Extract YouTube video ID from various URL formats.
        Supports youtube.com, youtu.be, and embed URLs.
        """
        if not url:
            return None
            
        # Regex pattern to extract video ID from various YouTube URL formats
        patterns = [
            r'(?:v=|/)([0-9A-Za-z_-]{11})(?:S+|$)',  # Standard and embed URLs
            r'(?:youtu.be/)([0-9A-Za-z_-]{11})(?:S+|$)',  # Shortened URLs
            r'^([0-9A-Za-z_-]{11})$',  # Direct video ID
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match and len(match.group(1)) == 11:
                return match.group(1)
        
        return None

    @staticmethod
    def create_filename_with_video_id(original_path: Path, video_id: str) -> Path:
        """
        Create a new filename using video_id while preserving extension.
        """
        if not video_id:
            return original_path
            
        # Get the file extension
        extension = original_path.suffix
        # Create new filename with video_id
        new_filename = f"{video_id}{extension}"
        # Return new path with same parent directory
        return original_path.parent / new_filename

    @staticmethod
    async def download_and_rename_file(download_url: str, video_id: str) -> Optional[Path]:
        """
        Download file and rename it with video_id.
        """
        try:
            # Download the file
            download_result = await HttpxClient().download_file(download_url)
            
            if not download_result.success:
                return None
                
            original_path = Path(download_result.file_path)
            
            # Create new filename with video_id
            new_path = YouTubeUtils.create_filename_with_video_id(original_path, video_id)
            
            # Rename the file if the new name is different
            if original_path != new_path:
                try:
                    original_path.rename(new_path)
                    return new_path
                except Exception as e:
                    return original_path
            
            return original_path
            
        except Exception as e:
            return None

    @staticmethod
    async def download_with_new_api(
        video_url: str, 
        is_video: bool = False, 
        bitrate: str = "128", 
        quality: str = "720p"
    ) -> Optional[Path]:
        """
        Download audio/video using the new GET API and rename with video_id.
        """
        if not video_url:
            return None

        try:
            # Extract video ID for naming
            video_id = YouTubeUtils.extract_video_id(video_url)
            if not video_id:
                return None

            # Determine API endpoint based on format
            api_endpoint = "https://ar-api-iauy.onrender.com/mp3youtube"
            format_param = "mp4" if is_video else "mp3"
            
            # Prepare query parameters for GET request
            params = {
                "url": video_url,
                "format": format_param,
            }
            
            # Add audioBitrate for audio downloads
            if not is_video:
                params["audioBitrate"] = bitrate
            
            # Make GET request to the API
            response = await HttpxClient().make_request(
                url=api_endpoint,
                method="GET",
                params=params
            )
            
            if not response:
                LOGGER(__name__).error("API response is empty")
                return None
                
            # Check if download was successful
            if response.get("status") != 200 or response.get("successful") != "success":
                LOGGER(__name__).error(f"API returned failure: {response.get('status')}")
                return None
                
            # Extract download link from the new API response structure
            data = response.get("data", {})
            download_info = data.get("download", {})
            download_link = download_info.get("url")
            
            if not download_link:
                LOGGER(__name__).error("No download link in API response")
                return None
            
            # Download and rename the file with video_id
            result_path = await YouTubeUtils.download_and_rename_file(download_link, video_id)
            
            if result_path:
                return result_path
            else:
                LOGGER(__name__).error("Failed to download file")
                return None
                
        except Exception as e:
            LOGGER(__name__).error(f"New API download error: {e}")
            return None

    @staticmethod
    async def download_with_api(video_id_or_url: str, is_video: bool = False) -> Optional[Path]:
        """
        Download audio/video using the new GET API first, then fallback to old API.
        All files are renamed with video_id.
        """
        if not video_id_or_url:
            return None

        try:
            # Extract video ID for consistent naming
            video_id = YouTubeUtils.extract_video_id(video_id_or_url)
            if not video_id:
                return None

            # Try new GET API first
            bitrate = "128" if not is_video else "192"
            quality = "720p" if is_video else "480p"
            
            result = await YouTubeUtils.download_with_new_api(
                video_id_or_url, is_video, bitrate, quality
            )
            
            if result:
                return result
            
            # Fallback to old API logic with video_id naming
            from AnonXMusic import app  # Local import inside function

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

            if source == "database" and re.match(r"https://t.me/([a-zA-Z0-9_]{5,})/(d+)", result_url):
                try:
                    tg_match = re.match(r"https://t.me/([a-zA-Z0-9_]{5,})/(d+)", result_url)
                    if tg_match:
                        chat_username, msg_id = tg_match.groups()
                        msg_obj = await app.get_messages(chat_username, int(msg_id))
                        if msg_obj:
                            # Download from Telegram and rename with video_id
                            downloaded_path = await msg_obj.download()
                            if downloaded_path:
                                original_path = Path(downloaded_path)
                                new_path = YouTubeUtils.create_filename_with_video_id(original_path, video_id)
                                if original_path != new_path:
                                    original_path.rename(new_path)
                                    return new_path
                                return original_path
                except errors.FloodWait as e:
                    await asyncio.sleep(e.value + 0)
                    return await YouTubeUtils.download_with_api(video_id, is_video)
                except Exception as e:
                    return None

            if source == "download_api" or (source == "" and re.match(r"https?://", result_url)):
                # Download and rename with video_id
                result_path = await YouTubeUtils.download_and_rename_file(result_url, video_id)
                return result_path

            return None

        except Exception as e:
            LOGGER(__name__).error(f"Download error: {e}")
            return None


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
        self.regex = r"(?:youtube.com|youtu.be)"
        self.status = "https://www.youtube.com/oembed?url="
        self.listbase = "https://youtube.com/playlist?list="
        self.reg = re.compile(r"\u001B(?:[@-Z\\-_]|[[0-?]*[ -/]*[@-~])")

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
            return 1, stdout.decode().split("")[0]
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
            result = playlist.split("")
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

        # Extract video ID for consistent naming
        video_id = YouTubeUtils.extract_video_id(link)

        def audio_dl():
            ydl_optssx = {
                "format": "bestaudio/best",
                "outtmpl": f"downloads/{video_id}.%(ext)s" if video_id else "downloads/%(id)s.%(ext)s",
                "geo_bypass": True,
                "nocheckcertificate": True,
                "quiet": True,
                "cookiefile": YouTubeUtils.get_cookie_file(),
                "no_warnings": True,
            }
            x = yt_dlp.YoutubeDL(ydl_optssx)
            info = x.extract_info(link, False)
            filename = f"{video_id}.{info['ext']}" if video_id else f"{info['id']}.{info['ext']}"
            xyz = os.path.join("downloads", filename)
            if os.path.exists(xyz):
                return xyz
            x.download([link])
            return xyz

        def video_dl():
            ydl_optssx = {
                "format": "(bestvideo[height<=?720][width<=?1280][ext=mp4])+(bestaudio[ext=m4a])",
                "outtmpl": f"downloads/{video_id}.%(ext)s" if video_id else "downloads/%(id)s.%(ext)s",
                "geo_bypass": True,
                "cookiefile": YouTubeUtils.get_cookie_file(),
                "nocheckcertificate": True,
                "quiet": True,
                "no_warnings": True,
            }
            x = yt_dlp.YoutubeDL(ydl_optssx)
            info = x.extract_info(link, False)
            filename = f"{video_id}.{info['ext']}" if video_id else f"{info['id']}.{info['ext']}"
            xyz = os.path.join("downloads", filename)
            if os.path.exists(xyz):
                return xyz
            x.download([link])
            return xyz

        def song_video_dl():
            formats = f"{format_id}+140"
            filename = f"{video_id}" if video_id else title
            fpath = f"downloads/{filename}"
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
            filename = f"{video_id}" if video_id else title
            fpath = f"downloads/{filename}.%(ext)s"
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
            filename = f"{video_id}" if video_id else title
            fpath = f"downloads/{filename}.mp4"
            return fpath
        elif songaudio:
            if dl := await YouTubeUtils.download_with_api(link):
                return str(dl)
            await loop.run_in_executor(None, song_audio_dl)
            filename = f"{video_id}" if video_id else title
            fpath = f"downloads/{filename}.mp3"
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
                    downloaded_file = stdout.decode().split("")[0]
                    direct = None
                else:
                    return
        else:
            direct = True
            if dl := await YouTubeUtils.download_with_api(link):
                return str(dl), direct
            downloaded_file = await loop.run_in_executor(None, audio_dl)
        return downloaded_file, direct
