# plugins/aplay.py

import re
import aiohttp
from pyrogram import filters
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    InputMediaPhoto,
)

from AnonXMusic import app

# Base iTunes API
ITUNES_API = "https://itunes.apple.com/search?term={}&entity={}&limit=5"

# Regex to detect Apple Music links
APPLE_REGEX = r"^https:\/\/music\.apple\.com\/[a-z]{2}\/(album|playlist|artist|song)\/[^\s\/]+\/(\d+)"


async def fetch_json(url: str) -> dict:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as resp:
                if resp.status != 200:
                    return {}
                return await resp.json()
    except Exception:
        return {}


async def search_itunes(query: str, entity: str):
    url = ITUNES_API.format(query.replace(" ", "+"), entity)
    return await fetch_json(url)


async def parse_results(data: dict, entity: str):
    results = []
    for item in data.get("results", []):
        title = item.get("trackName") or item.get("collectionName") or item.get("artistName")
        artist = item.get("artistName")
        collection = item.get("collectionName")
        thumb = item.get("artworkUrl100")
        track_id = item.get("trackId") or item.get("collectionId") or item.get("artistId")
        country = item.get("country", "us").lower()

        if not track_id or not title:
            continue

        url = f"https://music.apple.com/{country}/{entity}/{track_id}"

        display = title
        if artist and artist not in title:
            display += f" - {artist}"
        if collection and collection != title:
            display += f" ({collection})"

        results.append(
            {
                "title": display,
                "artist": artist,
                "album": collection,
                "url": url,
                "thumb": thumb,
            }
        )
    return results


@app.on_message(filters.command(["aplay"]))
async def aplay_handler(client, message):
    if len(message.command) < 2:
        return await message.reply_text(
            "Usage: /aplay song/artist/album/playlist or paste Apple Music link",
            quote=True,
        )

    query = " ".join(message.command[1:])
    m = await message.reply_text("🔎 Searching Apple Music...", quote=True)

    # Direct Apple Music link
    if re.match(APPLE_REGEX, query):
        return await m.edit(f"🔗 Here’s your Apple Music link:\n{query}", disable_web_page_preview=True)

    results = []
    try:
        for entity in ["song", "album", "artist", "playlist"]:
            data = await search_itunes(query, entity)
            if data and data.get("resultCount", 0) > 0:
                results = await parse_results(data, entity)
                break
    except Exception as e:
        return await m.edit(f"❌ Error while searching: {e}")

    if not results:
        return await m.edit("⚠️ No results found on Apple Music.")

    # Build buttons with callback_data
    buttons, row = [], []
    for i, track in enumerate(results[:5], start=1):
        text = track["title"]
        if len(text) > 25:
            text = text[:22] + "..."
        row.append(InlineKeyboardButton(text=text, callback_data=f"apple:{i-1}:{query}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    text = f"🎵 Results for {query} on Apple Music:\n\n"
    for i, track in enumerate(results[:5], start=1):
        text += f"{i}. {track['title']}\n"

    await m.edit(
        text,
        reply_markup=InlineKeyboardMarkup(buttons),
        disable_web_page_preview=True,
    )


@app.on_callback_query(filters.regex(r"^apple:(\d+):(.+)"))
async def apple_callback(client, callback_query: CallbackQuery):
    index = int(callback_query.matches[0].group(1))
    query = callback_query.matches[0].group(2)

    results = []
    for entity in ["song", "album", "artist", "playlist"]:
        data = await search_itunes(query, entity)
        if data and data.get("resultCount", 0) > 0:
            results = await parse_results(data, entity)
            break

    if not results or index >= len(results):
        return await callback_query.answer("❌ Result not found.", show_alert=True)

    track = results[index]
    caption = (
        f"🎶 {track['title']}\n"
        f"👤 Artist: {track.get('artist','N/A')}\n"
        f"💽 Album: {track.get('album','N/A')}\n\n"
        f"🔗 [Open in Apple Music]({track['url']})"
    )

    if track.get("thumb"):
        await callback_query.message.edit_media(
            InputMediaPhoto(media=track["thumb"], caption=caption)
        )
        await callback_query.message.edit_reply_markup(
            InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Open in Apple Music", url=track["url"])]])
        )
    else:
        await callback_query.message.edit(
            caption,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔗 Open in Apple Music", url=track["url"])]]
            ),
            disable_web_page_preview=True,
)
