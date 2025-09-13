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

from AnonXMusic.platforms._httpx import HttpxClient
from AnonXMusic.utils.database import is_on_off
from AnonXMusic.utils.formatters import time_to_seconds
from config import API_URL, API_KEY

# New Hardcoded API Configuration
NEW_API_BASE = "https://ar-api-iauy.onrender.com"
MP3_ENDPOINT = "/mp3youtube"
MP4_ENDPOINT = "/mp3youtube"

class YouTubeUtils:
    @staticmethod
    def get_cookie_file() -> Optional[str]:
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
        except Exception:
            return None

    @staticmethod
    def build_youtube_url(video_id_or_url: str) -> str:
        if video_id_or_url.startswith(('http://', 'https://')):
            return video_id_or_url
        elif re.match(r"^[0-9A-Za-z_-]{11}$", video_id_or_url):
            return f"https://youtu.be/{video_id_or_url}"
        else:
            yt_video_id_match = re.search(
                r"(?:v=|/)([0-9A-Za-z_-]{11})(?:&|$)", video_id_or_url
            )
            if yt_video_id_match:
                return f"https://youtube.com/watch?v={yt_video_id_match.group(1)}"
        return video_id_or_url

    @staticmethod
    async def download_with_new_api(video_id_or_url: str, is_video: bool = False) -> Optional[Path]:
        if not video_id_or_url:
            return None
        try:
            from AnonXMusic import app
            youtube_url = YouTubeUtils.build_youtube_url(video_id_or_url)
            endpoint = MP4_ENDPOINT if is_video else MP3_ENDPOINT
            params = {
                'url': youtube_url,
                'format': 'mp4' if is_video else 'mp3',
                'videoBitrate': '720' if is_video else None,
                'audioBitrate': '128' if not is_video else None
            }
            params = {k: v for k, v in params.items() if v is not None}
            api_url = f"{NEW_API_BASE}{endpoint}"
            res = await HttpxClient().make_request(api_url, params=params)
            if res and res.get("status") == 200 and res.get("successful") == "success":
                data = res.get("data", {})
                download_info = data.get("download", {})
                download_url = download_info.get("url")
                filename = download_info.get("filename")
                if download_url:
                    dl = await HttpxClient().download_file(download_url)
                    if dl.success:
                        video_id = YouTubeUtils.extract_video_id(youtube_url)
                        ext = 'mp4' if is_video else 'mp3'
                        new_path = Path(f"downloads/{video_id}.{ext}")
                        os.makedirs("downloads", exist_ok=True)
                        dl.file_path.rename(new_path)
                        return new_path
            return None
        except Exception:
            return None

    @staticmethod
    def extract_video_id(url: str) -> Optional[str]:
        if re.match(r"^[0-9A-Za-z_-]{11}$", url):
            return url
        match = re.search(r"(?:v=|/)([0-9A-Za-z_-]{11})(?:&|$)", url)
        return match.group(1) if match else None

    @staticmethod
    async def download_with_api(video_id_or_url: str, is_video: bool = False) -> Optional[Path]:
        if not video_id_or_url:
            return None
        try:
            from AnonXMusic import app
            video_id = YouTubeUtils.extract_video_id(video_id_or_url)
            if not video_id:
                return None
            api_url = f"{API_URL}?api_key={API_KEY}&id={video_id}"
            res = await HttpxClient().make_request(api_url)
            if not res:
                return None
            result_url = res.get("results")
            if not result_url:
                return None
            source = res.get("source", "")
            if source == "database" and re.match(r"https://t\.me/([a-zA-Z0-9_]{5,})/(\d+)", result_url):
                try:
                    tg_match = re.match(r"https://t\.me/([a-zA-Z0-9_]{5,})/(\d+)", result_url)
                    if tg_match:
                        chat_username, msg_id = tg_match.groups()
                        msg_obj = await app.get_messages(chat_username, int(msg_id))
                        if msg_obj:
                            file_path = await msg_obj.download()
                            ext = 'mp4' if is_video else 'mp3'
                            new_path = Path(f"downloads/{video_id}.{ext}")
                            os.makedirs("downloads", exist_ok=True)
                            os.rename(file_path, new_path)
                            return new_path
                except errors.FloodWait as e:
                    await asyncio.sleep(e.value + 1)
                    return await YouTubeUtils.download_with_api(video_id_or_url, is_video)
                except Exception:
                    return None
            if source == "download_api" or (source == "" and re.match(r"https?://", result_url)):
                dl = await HttpxClient().download_file(result_url)
                if dl.success:
                    video_id = YouTubeUtils.extract_video_id(video_id_or_url)
                    ext = 'mp4' if is_video else 'mp3'
                    new_path = Path(f"downloads/{video_id}.{ext}")
                    os.makedirs("downloads", exist_ok=True)
                    dl.file_path.rename(new_path)
                    return new_path
                return None
        except ImportError:
            return None
        except Exception:
            return None

    @staticmethod
    async def download_with_ytdlp(video_id_or_url: str, is_video: bool = False) -> Optional[Path]:
        youtube_url = YouTubeUtils.build_youtube_url(video_id_or_url)
        video_id = YouTubeUtils.extract_video_id(youtube_url)
        if not video_id:
            return None
        cookie_file = YouTubeUtils.get_cookie_file()
        ydl_opts = {
            "format": "bestvideo[height<=?720][width<=?1280][ext=mp4]+bestaudio[ext=m4a]/best" if is_video else "bestaudio/best",
            "outtmpl": f"downloads/{video_id}.%(ext)s",
            "geo_bypass": True,
            "geo_bypass_country": "IN",
            "nocheckcertificate": True,
            "quiet": True,
            "no_warnings": True,
            "cookiefile": cookie_file,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }] if not is_video else []
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(youtube_url, download=False)
                if not info:
                    return None
                ydl.download([youtube_url])
                ext = 'mp4' if is_video else 'mp3'
                file_path = Path(f"downloads/{video_id}.{ext}")
                if file_path.exists():
                    return file_path
                return None
        except Exception:
            return None

    @staticmethod
    async def download(video_id_or_url: str, is_video: bool = False) -> Optional[Path]:
        if dl := await YouTubeUtils.download_with_new_api(video_id_or_url, is_video):
            return dl
        if dl := await YouTubeUtils.download_with_api(video_id_or_url, is_video):
            return dl
        return await YouTubeUtils.download_with_ytdlp(video_id_or_url, is_video)

async def shell_cmd(cmd):
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
        else:
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
        if offset is None:
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
            duration_sec = int(time_to_seconds(duration_min)) if duration_min != "None" else 0
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
        if dl := await YouTubeUtils.download(link, is_video=True):
            return True, str(dl)
        return False, "Download failed"

    async def playlist(self, link, limit, user_id, videoid: Union[bool, str] = None):
        if videoid:
            link = self.listbase + link
        if "&" in link:
            link = link.split("&")[0]
        playlist = await shell_cmd(
            f"yt-dlp -i --get-id --flat-playlist --playlist-end {limit} --skip-download {link}"
        )
        result = [key for key in playlist.split("\n") if key]
        return result

    async def track(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = VideosSearch(link, limit=1)
        for result in (await results.next())["result"]:
            track_details = {
                "title": result["title"],
                "link": result["link"],
                "vidid": result["id"],
                "duration_min": result["duration"],
                "thumb": result["thumbnails"][0]["url"].split("?")[0]
            }
        return track_details, result["id"]

    async def formats(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        ytdl_opts = {"quiet": True}
        with yt_dlp.YoutubeDL(ytdl_opts) as ydl:
            formats_available = []
            r = ydl.extract_info(link, download=False)
            for format in r["formats"]:
                if "dash" in str(format.get("format", "")).lower():
                    continue
                if all(key in format for key in ["format", "filesize", "format_id", "ext", "format_note"]):
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
        video_id = YouTubeUtils.extract_video_id(link)
        if not video_id:
            return None

        loop = asyncio.get_running_loop()

        def audio_dl():
            ydl_optssx = {
                "format": "bestaudio/best",
                "outtmpl": f"downloads/{video_id}.%(ext)s",
                "geo_bypass": True,
                "nocheckcertificate": True,
                "quiet": True,
                "cookiefile": YouTubeUtils.get_cookie_file(),
                "no_warnings": True,
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }]
            }
            with yt_dlp.YoutubeDL(ydl_optssx) as x:
                info = x.extract_info(link, download=False)
                xyz = os.path.join("downloads", f"{video_id}.{info['ext']}")
                if os.path.exists(xyz):
                    return xyz
                x.download([link])
                return xyz

        def video_dl():
            ydl_optssx = {
                "format": "bestvideo[height<=?720][width<=?1280][ext=mp4]+bestaudio[ext=m4a]/best",
                "outtmpl": f"downloads/{video_id}.%(ext)s",
                "geo_bypass": True,
                "cookiefile": YouTubeUtils.get_cookie_file(),
                "nocheckcertificate": True,
                "quiet": True,
                "no_warnings": True,
            }
            with yt_dlp.YoutubeDL(ydl_optssx) as x:
                info = x.extract_info(link, download=False)
                xyz = os.path.join("downloads", f"{video_id}.{info['ext']}")
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
            with yt_dlp.YoutubeDL(ydl_optssx) as x:
                x.download([link])
            return f"{fpath}.mp4"

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
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }],
            }
            with yt_dlp.YoutubeDL(ydl_optssx) as x:
                x.download([link])
            return f"{fpath[:-7]}.mp3"

        if songvideo:
            if dl := await YouTubeUtils.download_with_new_api(link, is_video=True):
                return str(dl)
            if dl := await YouTubeUtils.download_with_api(link, is_video=True):
                return str(dl)
            return await loop.run_in_executor(None, song_video_dl)
        elif songaudio:
            if dl := await YouTubeUtils.download_with_new_api(link, is_video=False):
                return str(dl)
            if dl := await YouTubeUtils.download_with_api(link, is_video=False):
                return str(dl)
            return await loop.run_in_executor(None, song_audio_dl)
        elif video:
            if await is_on_off(1):
                direct = True
                downloaded_file = await loop.run_in_executor(None, video_dl)
            else:
                if dl := await YouTubeUtils.download_with_new_api(link, is_video=True):
                    return str(dl), direct
                if dl := await YouTubeUtils.download_with_api(link, is_video=True):
                    return str(dl), direct
                downloaded_file = await loop.run_in_executor(None, video_dl)
                direct = None
        else:
            direct = True
            if dl := await YouTubeUtils.download_with_new_api(link, is_video=False):
                return str(dl), direct
            if dl := await YouTubeUtils.download_with_api(link, is_video=False):
                return str(dl), direct
            downloaded_file = await loop.run_in_executor(None, audio_dl)
        return downloaded_file, direct
