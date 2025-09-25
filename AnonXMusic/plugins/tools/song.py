from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
import requests
import logging
from AnonXMusic import app
import asyncio
import io
import urllib.parse
from pyrogram.errors import FloodWait


song_storage = {}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@app.on_message(filters.command("song"))
async def search_song(client, message):
    query = " ".join(message.command[1:])
    if not query:
        await message.reply_text("ᴘʟᴇᴀꜱᴇ ᴘʀᴏᴠɪᴅᴇ ᴀ ꜱᴏɴɢ ɴᴀᴍᴇ, ᴇ.ɢ., /ꜱᴏɴɢ Kᴀᴊᴀʟɪʏᴏ")
        return

    url = f"https://jiosavan-azure.vercel.app/api/search/songs?query={urllib.parse.quote(query)}"
    try:
        res = requests.get(url, timeout=10).json()
        print(f"DEBUG: API Response for '{query}': success={res.get('success')}, total={res.get('data', {}).get('total', 'N/A')}")
        print(f"DEBUG: First result keys: {list(res.get('data', {}).get('results', [{}])[0].keys()) if res.get('data', {}).get('results') else 'No results'}")
    except requests.exceptions.Timeout:
        await message.reply_text("ᴀᴘɪ ʀᴇQᴜᴇꜱᴛ ᴛɪᴍᴇᴅ ᴏᴜᴛ. Tʀʏ ᴀɢᴀɪɴ ʟᴀᴛᴇʀ.")
        return
    except requests.exceptions.RequestException as e:
        print(f"DEBUG: Network error: {str(e)}")
        await message.reply_text(f"ɴᴇᴛᴡᴏʀᴋ ᴇʀʀᴏʀ ꜰᴇᴛᴄʜɪɴɢ ʀᴇꜱᴜʟᴛꜱ: {str(e)}")
        return
    except Exception as e:
        print(f"DEBUG: JSON parse error: {str(e)}")
        await message.reply_text(f"ᴇʀʀᴏʀ ꜰᴇᴛᴄʜɪɴɢ ʀᴇꜱᴜʟᴛꜱ: {str(e)}")
        return


    if not res.get("success", False):
        await message.reply_text("<blockquote><b>ᴀᴘɪ ʀᴇQᴜᴇꜱᴛ ꜰᴀɪʟᴇᴅ! Tʀʏ ᴀɢᴀɪɴ ʟᴀᴛᴇʀ.</b></blockquote>")
        return

    results = res.get("data", {}).get("results", [])
    print(f"DEBUG: Extracted {len(results)} results")

    if not results:
        await message.reply_text("<blockquote><b>ɴᴏ ꜱᴏɴɢꜱ ꜰᴏᴜɴᴅ! Tʀʏ ᴀ ᴅɪꜰꜰᴇʀᴇɴᴛ Qᴜᴇʀʏ.</b></blockquote>")
        return

    buttons = []
    for i, song in enumerate(results[:5]):

        artists_data = song.get("artists", {}).get("primary", [])
        artist_names = ", ".join([a.get("name", "Uɴᴋɴᴏᴡɴ") for a in artists_data])
        song_name = song.get("name", "Uɴᴋɴᴏᴡɴ Sᴏɴɢ")
        callback_data = f"song_{i}_{message.from_user.id}"
        buttons.append([InlineKeyboardButton(f"{song_name} - {artist_names}", callback_data=callback_data)])

        song_storage[callback_data] = song

    await message.reply_text(
        "**🎵 ꜱᴇʟᴇᴄᴛ ᴀ ꜱᴏɴɢ ᴛᴏ ᴅᴏᴡɴʟᴏᴀᴅ:**",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

@app.on_callback_query(filters.regex(r"^song_\d+_\d+$"))
async def download_song(client, callback_query):
    callback_data = callback_query.data
    if not callback_data.startswith("song_"):
        await callback_query.answer("Iɴᴠᴀʟɪᴅ ᴄᴀʟʟʙᴀᴄᴋ ᴅᴀᴛᴀ!")
        return

    try:
        parts = callback_data.split("_")
        index = int(parts[1])
        user_id = int(parts[2])
        if callback_query.from_user.id != user_id:
            await callback_query.answer("Tʜɪꜱ ꜱᴏɴɢ ꜱᴇʟᴇᴄᴛɪᴏɴ ɪꜱ ɴᴏᴛ ꜰᴏʀ ʏᴏᴜ!")
            return
    except ValueError:
        await callback_query.answer("Iɴᴠᴀʟɪᴅ ꜱᴇʟᴇᴄᴛɪᴏɴ!")
        return

    song_key = callback_data
    song = song_storage.get(song_key)
    if not song:
        await callback_query.answer("Sᴏɴɢ ᴅᴀᴛᴀ ɴᴏᴛ ꜰᴏᴜɴᴅ! Pʟᴇᴀꜱᴇ ꜱᴇᴀʀᴄʜ ᴀɢᴀɪɴ.")
        return

    download_urls = song.get("downloadUrl", [])
    if not download_urls:
        await callback_query.answer("ɴᴏ ᴅᴏᴡɴʟᴏᴀᴅ ᴜʀʟ ᴀᴠᴀɪʟᴀʙʟᴇ ꜰᴏʀ ᴛʜɪꜱ ꜱᴏɴɢ!")
        return

    def get_quality(x):
        q = x.get("quality", "120")
        cleaned = str(q).replace("kbps", "").strip()
        try:
            return int(cleaned)
        except ValueError:
            return 120 

    download_urls.sort(key=get_quality, reverse=True)
    audio_url = download_urls[0].get("url", "")
    if not audio_url:
        await callback_query.answer("Iɴᴠᴀʟɪᴅ ᴅᴏᴡɴʟᴏᴀᴅ ᴜʀʟ!")
        return

    name = song.get("name", "Uɴᴋɴᴏᴡɴ Sᴏɴɢ")
    artists_data = song.get("artists", {}).get("primary", [])
    artists = ", ".join([a.get("name", "Uɴᴋɴᴏᴡɴ") for a in artists_data])
    album = song.get("album", {}).get("name", "Uɴᴋɴᴏᴡɴ Aʟʙᴜᴍ")
    duration = int(song.get("duration", 0))
    minutes, seconds = divmod(duration, 60)
    duration_str = f"{minutes}:{seconds:02d}"
    song_link = song.get("url", "Nᴏ ʟɪɴᴋ ᴀᴠᴀɪʟᴀʙʟᴇ")
    image_urls = song.get("image", [])
    thumb_url = next((img.get("url") for img in image_urls if img.get("quality") == "500x500"), None)

    await callback_query.answer("Dᴏᴡɴʟᴏᴀᴅɪɴɢ ꜱᴏɴɢ... 🎵")

    try:

        response = requests.get(audio_url, stream=True, timeout=30)
        response.raise_for_status()  
        audio_data = io.BytesIO(response.content)
        audio_data.name = f"{name} - {artists}.m4a"


        thumb_data = None
        if thumb_url:
            try:
                thumb_response = requests.get(thumb_url, timeout=10)
                thumb_response.raise_for_status()
                thumb_data = io.BytesIO(thumb_response.content)
                thumb_data.name = "thumb.jpg"
            except Exception as e:
                print(f"DEBUG: Thumbnail download error: {str(e)}")
                thumb_data = None


        caption = (
            "<blockquote><b>[ <a href=\"{song_link}\">{name}</a> ]</b>\n"
            "<b>ᴀʟʙᴜᴍ: {album}</b>\n"
            "<b>ᴅᴜʀᴀᴛɪᴏɴ: {duration}</b>\n"
            "<b>ꜱᴏᴜʀᴄᴇ: ᴊɪᴏ ꜱᴀᴀᴠɴ</b></blockquote>"
        ).format(
            song_link=song_link,
            name=name,
            album=album,
            duration=duration_str
        )



        await callback_query.message.reply_audio(
            audio_data,
            title=name,
            performer=artists,
            caption=caption,
            thumb=thumb_data
        )   
        await callback_query.message.delete() 


        song_storage.pop(song_key, None)
    except FloodWait as e:

        await asyncio.sleep(e.value)
        await callback_query.answer("ʀᴀᴛᴇ ʟɪᴍɪᴛᴇᴅ ʙʏ Tᴇʟᴇɢʀᴀᴍ. Pʟᴇᴀꜱᴇ ᴡᴀɪᴛ ᴀ ᴍᴏᴍᴇɴᴛ ᴀɴᴅ ᴛʀʏ ᴀɢᴀɪɴ.")
    except requests.exceptions.Timeout:
        await callback_query.answer("Dᴏᴡɴʟᴏᴀᴅ ᴛɪᴍᴇᴅ ᴏᴜᴛ. Tʀʏ ᴀɢᴀɪɴ.")
    except Exception as e:
        print(f"DEBUG: Download error: {str(e)}")
        try:
            await callback_query.answer(f"Dᴏᴡɴʟᴏᴀᴅ ꜰᴀɪʟᴇᴅ: {str(e)}")
        except:

            print(f"Callback query failed, but download error was: {str(e)}")
