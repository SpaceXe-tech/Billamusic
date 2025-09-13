import asyncio
import os
import random
import re
import json
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
        """Get the freshest cookie file from the 'cookies' directory, skipping 'cookie_time.txt'."""
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

            # Sort by modification time to get the freshest cookies instead of random
            cookies_files.sort(key=lambda x: os.path.getmtime(os.path.join(cookie_dir, x)), reverse=True)
            selected_file = cookies_files[0]
            
            cookie_path = os.path.join(cookie_dir, selected_file)
            LOGGER(__name__).info(f"Using cookie file: {selected_file}")
            return cookie_path

        except Exception as e:
            LOGGER(__name__).warning("Error accessing cookie directory: %s", e)
            return None

    @staticmethod
    async def download_with_api(video_id_or_url: str, is_video: bool = False) -> Optional[Path]:
        """
        Download audio/video using the new API (uses API_URL + API_KEY).
        If a full YouTube URL is given, extract only video_id and pass to API.
        Handles Telegram media or direct CDN links based on API response.
        Fixed streaming response handling.
        """
        if not video_id_or_url:
            LOGGER(__name__).warning("Video ID or URL is None")
            return None

        try:
            from AnonXMusic import app  # Local import inside function

            # Extract video_id if full YouTube URL given
            video_id = video_id_or_url
            # Regex to extract video id from youtube URL parameters
            yt_video_id_match = re.search(
                r"(?:v=|\/)([0-9A-Za-z_-]{11})(?:\&|$)", video_id_or_url
            )
            if yt_video_id_match:
                video_id = yt_video_id_match.group(1)
            elif re.match(r"^[0-9A-Za-z_-]{11}$", video_id_or_url):
                video_id = video_id_or_url  # Already a valid ID
            else:
                # Could not parse valid video_id
                LOGGER(__name__).warning("Invalid video ID or URL format")
                return None

            api_url = f"{API_URL}?api_key={API_KEY}&id={video_id}"
            
            # Enhanced API request handling with proper response reading
            try:
                response = await HttpxClient().make_request(api_url, timeout=30)
                
                # Handle streaming response properly
                if hasattr(response, 'read'):
                    content = await response.read()
                    if isinstance(content, bytes):
                        content = content.decode('utf-8')
                    try:
                        res = json.loads(content) if isinstance(content, str) else response
                    except json.JSONDecodeError:
                        LOGGER(__name__).error("Failed to parse API response as JSON")
                        return None
                elif hasattr(response, 'json'):
                    res = await response.json() if asyncio.iscoroutine(response.json()) else response.json()
                else:
                    res = response if isinstance(response, dict) else None
                    
            except asyncio.TimeoutError:
                LOGGER(__name__).error("API request timeout")
                return None
            except Exception as api_error:
                LOGGER(__name__).error(f"API request failed: {api_error}")
                return None

            if not res:
                LOGGER(__name__).error("API response empty or invalid")
                return None

            msg = res.get("message", "")
            result_url = res.get("results")
            if not result_url:
                LOGGER(__name__).error("No 'results' in API response")
                return None

            source = res.get("source", "")

            # Handle Telegram source with enhanced error handling
            if source == "database" and re.match(r"https:\/\/t\.me\/([a-zA-Z0-9_]{5,})\/(\d+)", result_url):
                try:
                    tg_match = re.match(r"https:\/\/t\.me\/([a-zA-Z0-9_]{5,})\/(\d+)", result_url)
                    if tg_match:
                        chat_username, msg_id = tg_match.groups()
                        msg_obj = await app.get_messages(chat_username, int(msg_id))
                        if msg_obj and (msg_obj.audio or msg_obj.video or msg_obj.document):
                            return await msg_obj.download()
                except errors.FloodWait as e:
                    LOGGER(__name__).warning(f"FloodWait: {e.value} seconds")
                    await asyncio.sleep(e.value + 1)
                    return await YouTubeUtils.download_with_api(video_id, is_video)
                except Exception as e:
                    LOGGER(__name__).error(f"Telegram fetch error: {e}")
                    # Don't return None immediately, try other methods

            # Handle direct download source
            if source == "download_api" or (source == "" and re.match(r"https?://", result_url)):
                try:
                    dl = await HttpxClient().download_file(result_url)
                    return dl.file_path if dl.success else None
                except Exception as e:
                    LOGGER(__name__).error(f"Direct download failed: {e}")

            LOGGER(__name__).warning(f"API source not handled properly: {source}, {result_url}")
            return None

        except Exception as e:
            LOGGER(__name__).error(f"API error: {e}")
            return None


async def shell_cmd(cmd):
    """Enhanced shell command execution with better error handling."""
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
        elif "sign in to confirm" in error_str or "this helps protect our community" in error_str:
            LOGGER(__name__).warning("YouTube bot detection triggered")
            return ""
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
        
        try:
            results = VideosSearch(link, limit=1)
            search_result = await results.next()
            
            if not search_result.get("result"):
                raise Exception("No search results found")
                
            result = search_result["result"][0]
            title = result["title"]
            duration_min = result["duration"]
            thumbnail = result["thumbnails"][0]["url"].split("?")[0]
            vidid = result["id"]
            if str(duration_min) == "None":
                duration_sec = 0
            else:
                duration_sec = int(time_to_seconds(duration_min))
            return title, duration_min, duration_sec, thumbnail, vidid
        except Exception as e:
            LOGGER(__name__).error(f"Error getting video details: {e}")
            return None, None, 0, None, None

    async def title(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        try:
            results = VideosSearch(link, limit=1)
            search_result = await results.next()
            if search_result.get("result"):
                title = search_result["result"][0]["title"]
                return title
        except Exception as e:
            LOGGER(__name__).error(f"Error getting video title: {e}")
        return "Unknown Title"

    async def duration(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        try:
            results = VideosSearch(link, limit=1)
            search_result = await results.next()
            if search_result.get("result"):
                duration = search_result["result"][0]["duration"]
                return duration
        except Exception as e:
            LOGGER(__name__).error(f"Error getting video duration: {e}")
        return "Unknown"

    async def thumbnail(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        try:
            results = VideosSearch(link, limit=1)
            search_result = await results.next()
            if search_result.get("result"):
                thumbnail = search_result["result"][0]["thumbnails"][0]["url"].split("?")[0]
                return thumbnail
        except Exception as e:
            LOGGER(__name__).error(f"Error getting video thumbnail: {e}")
        return None

    async def video(self, link: str, videoid: Union[bool, str] = None):
        # Try API first
        if dl := await YouTubeUtils.download_with_api(link, True):
            return True, str(dl)

        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
            
        # Add delay to avoid bot detection
        await asyncio.sleep(random.uniform(1, 1))
        
        cookie_file = YouTubeUtils.get_cookie_file()
        if not cookie_file:
            LOGGER(__name__).warning("No cookie file available, proceeding without cookies")
            
        try:
            cmd_args = ["yt-dlp", "-g", "-f", "best[height<=?720][width<=?1280]"]
            if cookie_file:
                cmd_args.extend(["--cookies", cookie_file])
            cmd_args.append(link)
            
            proc = await asyncio.create_subprocess_exec(
                *cmd_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if stdout:
                return 1, stdout.decode().split("\n")[0]
            else:
                error_msg = stderr.decode()
                if "unavailable" in error_msg.lower():
                    LOGGER(__name__).warning(f"Video unavailable: {link}")
                return 0, error_msg
        except Exception as e:
            LOGGER(__name__).error(f"Error in video extraction: {e}")
            return 0, str(e)

    async def playlist(self, link, limit, user_id, videoid: Union[bool, str] = None):
        if videoid:
            link = self.listbase + link
        if "&" in link:
            link = link.split("&")[0]
        
        cookie_file = YouTubeUtils.get_cookie_file()
        cookie_arg = f"--cookies {cookie_file}" if cookie_file else ""
        
        playlist = await shell_cmd(
            f"yt-dlp -i --get-id --flat-playlist --playlist-end {limit} {cookie_arg} --skip-download {link}"
        )
        try:
            result = [item.strip() for item in playlist.split("\n") if item.strip()]
            return result
        except Exception as e:
            LOGGER(__name__).error(f"Error processing playlist: {e}")
            return []

    async def track(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        try:
            results = VideosSearch(link, limit=1)
            search_result = await results.next()
            if not search_result.get("result"):
                return None, None
                
            result = search_result["result"][0]
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
        except Exception as e:
            LOGGER(__name__).error(f"Error getting track details: {e}")
            return None, None

    async def formats(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        
        cookie_file = YouTubeUtils.get_cookie_file()
        ytdl_opts = {
            "quiet": True,
            "no_warnings": True
        }
        if cookie_file:
            ytdl_opts["cookiefile"] = cookie_file
            
        ydl = yt_dlp.YoutubeDL(ytdl_opts)
        try:
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
        except Exception as e:
            LOGGER(__name__).error(f"Error getting formats: {e}")
            return [], link

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
        try:
            a = VideosSearch(link, limit=10)
            search_result = await a.next()
            result = search_result.get("result", [])
            
            if not result or len(result) <= query_type:
                return None, None, None, None
                
            item = result[query_type]
            title = item["title"]
            duration_min = item["duration"]
            vidid = item["id"]
            thumbnail = item["thumbnails"][0]["url"].split("?")[0]
            return title, duration_min, thumbnail, vidid
        except Exception as e:
            LOGGER(__name__).error(f"Error in slider: {e}")
            return None, None, None, None

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

        def get_enhanced_ydl_opts(base_opts: dict) -> dict:
            """Get enhanced yt-dlp options with bot detection avoidance."""
            cookie_file = YouTubeUtils.get_cookie_file()
            enhanced_opts = {
                **base_opts,
                "geo_bypass": True,
                "nocheckcertificate": True,
                "quiet": True,
                "no_warnings": True,
                "sleep_interval": 1,
                "max_sleep_interval": 3,
                "extractor_retries": 3,
                "http_headers": {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                }
            }
            if cookie_file:
                enhanced_opts["cookiefile"] = cookie_file
            return enhanced_opts

        def audio_dl():
            ydl_optssx = get_enhanced_ydl_opts({
                "format": "bestaudio/best",
                "outtmpl": "downloads/%(id)s.%(ext)s",
            })
            x = yt_dlp.YoutubeDL(ydl_optssx)
            try:
                info = x.extract_info(link, False)
                xyz = os.path.join("downloads", f"{info['id']}.{info['ext']}")
                if os.path.exists(xyz):
                    return xyz
                x.download([link])
                return xyz
            except Exception as e:
                LOGGER(__name__).error(f"Audio download error: {e}")
                raise

        def video_dl():
            ydl_optssx = get_enhanced_ydl_opts({
                "format": "(bestvideo[height<=?720][width<=?1280][ext=mp4])+(bestaudio[ext=m4a])",
                "outtmpl": "downloads/%(id)s.%(ext)s",
            })
            x = yt_dlp.YoutubeDL(ydl_optssx)
            try:
                info = x.extract_info(link, False)
                xyz = os.path.join("downloads", f"{info['id']}.{info['ext']}")
                if os.path.exists(xyz):
                    return xyz
                x.download([link])
                return xyz
            except Exception as e:
                LOGGER(__name__).error(f"Video download error: {e}")
                raise
        
        def song_video_dl():
            formats = f"{format_id}+140"
            fpath = f"downloads/{title}"
            ydl_optssx = get_enhanced_ydl_opts({
                "format": formats,
                "outtmpl": fpath,
                "prefer_ffmpeg": True,
                "merge_output_format": "mp4",
            })
            x = yt_dlp.YoutubeDL(ydl_optssx)
            x.download([link])

        def song_audio_dl():
            fpath = f"downloads/{title}.%(ext)s"
            ydl_optssx = get_enhanced_ydl_opts({
                "format": format_id,
                "outtmpl": fpath,
                "prefer_ffmpeg": True,
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }
                ],
            })
            x = yt_dlp.YoutubeDL(ydl_optssx)
            x.download([link])

        # Add random delay to avoid bot detection
        await asyncio.sleep(random.uniform(0.5, 2.0))

        if songvideo:
            if dl := await YouTubeUtils.download_with_api(link, True):
                return str(dl)

            try:
                await loop.run_in_executor(None, song_video_dl)
                fpath = f"downloads/{title}.mp4"
                return fpath
            except Exception as e:
                LOGGER(__name__).error(f"Song video download failed: {e}")
                raise
                
        elif songaudio:
            if dl := await YouTubeUtils.download_with_api(link):
                return str(dl)
            try:
                await loop.run_in_executor(None, song_audio_dl)
                fpath = f"downloads/{title}.mp3"
                return fpath
            except Exception as e:
                LOGGER(__name__).error(f"Song audio download failed: {e}")
                raise
                
        elif video:
            if await is_on_off(1):
                direct = True
                try:
                    downloaded_file = await loop.run_in_executor(None, video_dl)
                except Exception as e:
                    LOGGER(__name__).error(f"Direct video download failed: {e}")
                    return None
            else:
                if dl := await YouTubeUtils.download_with_api(link, True):
                    return str(dl), True

                cookie_file = YouTubeUtils.get_cookie_file()
                cmd_args = ["yt-dlp", "-g", "-f", "best[height<=?720][width<=?1280]"]
                if cookie_file:
                    cmd_args.extend(["--cookies", cookie_file])
                cmd_args.append(link)
                
                proc = await asyncio.create_subprocess_exec(
                    *cmd_args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                if stdout:
                    downloaded_file = stdout.decode().split("\n")[0]
                    direct = None
                else:
                    error_msg = stderr.decode()
                    if "unavailable" in error_msg.lower():
                        LOGGER(__name__).warning(f"Video unavailable for streaming: {link}")
                    return None
        else:
            direct = True
            if dl := await YouTubeUtils.download_with_api(link):
                return str(dl), direct
            try:
                downloaded_file = await loop.run_in_executor(None, audio_dl)
            except Exception as e:
                LOGGER(__name__).error(f"Audio download failed: {e}")
                return None
                
        return downloaded_file, direct
