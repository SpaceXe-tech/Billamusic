import os
import time
import asyncio
from AnonXMusic import app 
import requests
import yt_dlp
from collections import defaultdict
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait, MessageIdInvalid
from youtubesearchpython.__future__ import VideosSearch
from config import API_URL2, SONG_DUMP_ID

DOWNLOADS_DIR = "downloads"
COOKIES_PATH = "AnonXMusic/assets/cookies.txt"
MAX_RETRIES = 3
SPAM_LIMIT = 5
SPAM_WINDOW = 60
BLOCK_DURATION = 600

user_usage = defaultdict(list)
user_blocked = {}

if not os.path.exists(DOWNLOADS_DIR):
    os.makedirs(DOWNLOADS_DIR)

class QuietLogger:
    def debug(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): print(f"[yt-dlp error] {msg}")

def parse_duration(duration_str):
    try:
        parts = duration_str.split(":")
        return sum(int(x) * 60**i for i, x in enumerate(reversed(parts)))
    except Exception:
        return 0

def download_thumbnail(url: str, file_path: str):
    try:
        r = requests.get(url, stream=True, timeout=10)
        if r.status_code == 200:
            with open(file_path, "wb") as f:
                for chunk in r.iter_content(1024):
                    f.write(chunk)
            return file_path
    except Exception as e:
        print(f"[Thumbnail] Error: {e}")
    return None

async def cleanup_files(audio_file, thumb_path, user_msg, reply_msg):
    await asyncio.sleep(300)
    try:
        if user_msg.chat.id != SONG_DUMP_ID:
            try: await reply_msg.delete()
            except Exception as e: print(f"[Cleanup] Failed to delete reply: {e}")
            try: await user_msg.delete()
            except Exception as e: print(f"[Cleanup] Failed to delete user msg: {e}")
    except Exception as e:
        print(f"[Cleanup] Message deletion error: {e}")
    try:
        if os.path.exists(audio_file): os.remove(audio_file)
        if thumb_path and os.path.exists(thumb_path): os.remove(thumb_path)
    except Exception as e:
        print(f"[Cleanup] File deletion error: {e}")

async def download_audio(url, video_id, title, m):
    output = os.path.join(DOWNLOADS_DIR, f"{video_id}_{int(time.time())}.m4a")
    progress_msg = m

    def progress_hook(d):
        if d['status'] == 'downloading':
            percent = d.get("_percent_str", "").strip()
            eta = d.get("eta", 0)
            speed = d.get("_speed_str", "N/A").strip()
            # Calculate estimated completion time
            downloaded_bytes = d.get("downloaded_bytes", 0)
            total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
            speed_bytes = d.get("speed", 0) or 0  # Speed in bytes per second
            est_completion = "N/A"
            if total_bytes > 0 and speed_bytes > 0:
                remaining_bytes = total_bytes - downloaded_bytes
                est_seconds = remaining_bytes / speed_bytes
                completion_time = time.time() + est_seconds
                est_completion = time.strftime("%H:%M:%S", time.localtime(completion_time))
            text = (
                f"📥 Downloading...\n\n"
                f"<b>Progress:</b> {percent}\n"
                f"<b>ETA:</b> {eta}s\n"
                f"<b>Speed:</b> {speed}\n"
                f"<b>Est. Completion:</b> {est_completion}"
            )
            try:
                asyncio.create_task(throttled_edit(progress_msg, text))
            except:
                pass

    ydl_opts = {
        "format": "bestaudio[ext=m4a]/bestaudio",
        "outtmpl": output,
        "noplaylist": True,
        "quiet": True,
        "logger": QuietLogger(),
        "progress_hooks": [progress_hook],
        "cookiefile": COOKIES_PATH if os.path.exists(COOKIES_PATH) else None,
        "no_warnings": True,
        "ignoreerrors": True,
        "geo_bypass": True,
        "nocheckcertificate": True,
        "user_agent": "Mozilla/5.0",
    }

    for attempt in range(MAX_RETRIES):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            if os.path.exists(output):
                return output
        except Exception as e:
            print(f"[yt-dlp] Attempt {attempt + 1} failed: {e}")
            await asyncio.sleep(2)
    return None

async def safe_edit(message, text):
    try:
        return await message.edit(text)
    except FloodWait as e:
        await asyncio.sleep(e.value)
        try:
            return await message.edit(text)
        except MessageIdInvalid:
            pass
        except Exception:
            pass
    except MessageIdInvalid:
        pass
    except Exception:
        pass

last_edit_time = 0

async def throttled_edit(message, text, min_interval=1.2):
    global last_edit_time
    wait = max(0, min_interval - (time.time() - last_edit_time))
    if wait > 0:
        await asyncio.sleep(wait)
    last_edit_time = time.time()
    return await safe_edit(message, text)

@app.on_message(filters.command(["song", "music"]) & filters.text)
async def song_handler(client: Client, message: Message):
    user_id = message.from_user.id
    user_name = message.from_user.first_name
    query = " ".join(message.command[1:])
    now = time.time()

    if user_id in user_blocked and now < user_blocked[user_id]:
        wait = int(user_blocked[user_id] - now)
        return await message.reply(f"<b>You're temporarily blocked for spamming on my functions.\nTry again in {wait} seconds.</b>")

    usage_list = user_usage[user_id]
    usage_list = [t for t in usage_list if now - t < SPAM_WINDOW]
    usage_list.append(now)
    user_usage[user_id] = usage_list

    if len(usage_list) > SPAM_LIMIT:
        user_blocked[user_id] = now + BLOCK_DURATION
        try:
            await app.send_message(
                SONG_DUMP_ID,
                f"🚫 <b>Blocked:</b> {user_name} ({user_id}) for spamming /song ({SPAM_LIMIT}+ uses in {SPAM_WINDOW}s)."
            )
        except: pass
        return await message.reply("<b>You're blocked for 10 minutes due to spamming.</b>")

    try:
        await app.send_message(
            SONG_DUMP_ID,
            f"🎵 <b>{user_name}</b> (ID: <code>{user_id}</code>) used /song command.\n🔍 <b>Query:</b> <code>{query}</code>",
        )
    except: pass

    if not query:
        return await message.reply("<b>Give me a Song name or YouTube URL ,YT Music URL to download.</b>")

    if "music.youtube.com" in query:
        query = query.replace("music.youtube.com", "www.youtube.com")
    if "playlist?" in query or "list=" in query:
        return await message.reply("<b>Playlists are not allowed. Only single Audio Are.</b>")

    m = await message.reply("<b>🔎 Searching Your Requested High Quality Song or Audio...</b>")

    try:
        search = VideosSearch(query, limit=MAX_RETRIES)
        search_results = await search.next()
        if not search_results.get("result"):
            return await throttled_edit(m, "<b>No results found for your query.</b>")
    except Exception as e:
        print(f"[Search] Error: {e}")
        return await throttled_edit(m, "<b>Search error occurred. Please try again.</b>")

    result = search_results["result"][0]
    video_id = result.get("id")
    if not video_id:
        return await throttled_edit(m, "<b>Invalid video found. Try another query.</b>")

    link = f"https://www.youtube.com/watch?v={video_id}"
    title = result.get("title", "Unknown")[:60]
    thumbnail = result.get("thumbnails", [{}])[0].get("即将")
    duration = result.get("duration", "0:00")
    channel_name = result.get("channel", {}).get("name", "Unknown")

    thumb_name = f"{DOWNLOADS_DIR}/{title.replace('/', '_')}.jpg"
    thumb_path = await asyncio.to_thread(download_thumbnail, thumbnail, thumb_name)
    audio_file = await download_audio(link, video_id, title, m)

    if not audio_file and API_URL2 and video_id:
        api_url = f"{API_URL2}?direct&id={video_id}"
        try:
            r = requests.get(api_url, stream=True, timeout=10)
            if r.ok and "audio" in r.headers.get("content-type", ""):
                audio_file = f"{DOWNLOADS_DIR}/{video_id}.mp3"
                with open(audio_file, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
        except Exception as e:
            print(f"[API] Download failed: {e}")

    if not audio_file:
        try:
            await app.send_message(
                SONG_DUMP_ID,
                f"❌ <b>Download failed for:</b> {query}\n👤 <b>User:</b> {user_name} ({user_id})",
            )
        except: pass
        return await throttled_edit(m, "<b>Failed to download song. Try a different one.</b>")

    dur = parse_duration(duration)
    performer_name = app.name or "BillaMusic"
    caption = (
        f"📻 <b><a href=\"{link}\">{title}</a></b>\n"
        f"🕒 Duration: {duration}\n"
        f"🎙️ By: {channel_name}\n\n"
        f"<i>Powered by Space-X Ashlyn API</i>"
    )

    await throttled_edit(m, "🎧 Uploading your High Quality Loseless Song [48hz 16bits]...")

    try:
        reply_msg = await message.reply_audio(
            audio=audio_file,
            title=title,
            performer=performer_name,
            duration=dur,
            caption=caption,
            thumb=thumb_path if thumb_path and os.path.exists(thumb_path) else None,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎧😄 More Songs", url="https://t.me/BillaSpace")]
            ])
        )

        await app.send_audio(
            chat_id=SONG_DUMP_ID,
            audio=audio_file,
            title=title,
            performer=performer_name,
            duration=dur,
            caption=caption,
            thumb=thumb_path if thumb_path and os.path.exists(thumb_path) else None,
        )

        await m.delete()
        asyncio.create_task(cleanup_files(audio_file, thumb_path, message, reply_msg))

    except FloodWait as fw:
        print(f"[Upload FloodWait] Waiting {fw.value}s  Waiting Timer initiated Due To Floodwait,Please Wait.., When The Timer Ends I'll automatically Share Your Loseless High Quality Song🎵.....")
        await asyncio.sleep(fw.value)
        try:
            reply_msg = await message.reply_audio(
                audio=audio_file,
                title=title,
                performer=performer_name,
                duration=dur,
                caption=caption,
                thumb=thumb_path if thumb_path and os.path.exists(thumb_path) else None,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🎧😄 More Songs", url="https://t.me/BillaSpace")]
                ])
            )
            await m.delete()
            asyncio.create_task(cleanup_files(audio_file, thumb_path, message, reply_msg))
        except Exception as retry_err:
            print(f"[Retry Upload] Failed again: {retry_err}")
            await throttled_edit(m, "<b>Failed to upload the song. Please try again.</b>")

    except Exception as e:
        print(f"[Upload Error] {e}")
        await throttled_edit(m, "<b>Failed to upload the song. Please try again.</b>")
