import re
import aiohttp
import unicodedata
from langdetect import detect
from pyrogram import filters
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    InputMediaPhoto,
)

from AnonXMusic import app

# Base iTunes API
ITUNES_API = "https://itunes.apple.com/search?term={}&entity={}&limit=4&country={}"

# Regex to detect Apple Music links
APPLE_REGEX = r"^https:\/\/music\.apple\.com\/[a-z]{2}\/(album|playlist|artist|song)\/[^\s\/]+\/(\d+)"


# --------------------------
# Helpers
# --------------------------
def normalize_query(query: str) -> str:
    """Clean & normalize query (remove accents, lowercasing, deduplicate words)."""
    query = unicodedata.normalize("NFKD", query).encode("ascii", "ignore").decode("utf-8")
    query = query.lower().strip()
    # Remove special characters and extra spaces
    query = re.sub(r'[^\w\s]', ' ', query)
    query = re.sub(r'\s+', ' ', query)
    # Deduplicate words
    words = query.split()
    cleaned = []
    for w in words:
        if not cleaned or cleaned[-1] != w:
            cleaned.append(w)
    return " ".join(cleaned)


def detect_country(query: str) -> str:
    """Detect language and map to iTunes country code."""
    try:
        lang = detect(query)
    except Exception:
        return "in"

    mapping = {
        "hi": "in",  # Hindi → India
        "bn": "in",  # Bengali → India
        "ur": "in",  # Urdu → India
        "en": "us",  # English → US
        "es": "es",  # Spanish → Spain
        "fr": "fr",  # French → France
        "de": "de",  # German → Germany
        "ja": "jp",  # Japanese → Japan
        "ko": "kr",  # Korean → Korea
        "zh-cn": "cn",  # Simplified Chinese
        "zh-tw": "tw",  # Traditional Chinese
    }

    return mapping.get(lang, "in")


async def fetch_json(url: str) -> dict:
    """Fetch JSON data from a URL."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as resp:
                if resp.status != 200:
                    return {}
                return await resp.json()
    except Exception:
        return {}


async def search_itunes(query: str, entity: str, country: str) -> dict:
    """Search iTunes API for the given query and entity."""
    url = ITUNES_API.format(query.replace(" ", "+"), entity, country)
    return await fetch_json(url)


async def parse_results(data: dict, entity: str, country: str) -> list:
    """Parse iTunes API results into a list of tracks."""
    results = []
    for item in data.get("results", []):
        title = item.get("trackName") or item.get("collectionName") or item.get("artistName")
        artist = item.get("artistName")
        collection = item.get("collectionName")
        thumb = item.get("artworkUrl100")
        track_id = item.get("trackId") or item.get("collectionId") or item.get("artistId")

        if not track_id or not title:
            continue

        url = f"https://music.apple.com/{country}/{entity}/{track_id}"

        display = title
        if artist and artist not in title:
            display += f" - {artist}"
        if collection and collection != title and entity != "album":
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


# --------------------------
# Command handler
# --------------------------
@app.on_message(filters.command(["aplay"]))
async def aplay_handler(client, message):
    """Handle /aplay command to search Apple Music or process direct links."""
    if len(message.command) < 2:
        return await message.reply_text(
            "Usage: /aplay song/artist/album/playlist or paste Apple Music link",
            quote=True,
        )

    raw_query = " ".join(message.command[1:])
    query = normalize_query(raw_query)
    country = detect_country(raw_query)

    m = await message.reply_text(f"🔎 Searching Apple Music ({country.upper()})...", quote=True)

    # Direct Apple Music link
    if re.match(APPLE_REGEX, query):
        return await m.edit(f"🔗 Here’s your Apple Music link:\n{query}", disable_web_page_preview=True)

    results = []
    try:
        # Search strategy: try full query, then progressively shorter versions
        attempts = [query]
        words = query.split()
        if len(words) > 3:
            attempts.append(" ".join(words[:3]))
        if len(words) > 1:
            attempts.append(" ".join(words[:2]))
        attempts.append(words[0])

        # Try initial country
        for q in attempts:
            for entity in ["song", "album", "artist", "playlist"]:
                data = await search_itunes(q, entity, country)
                if data and data.get("resultCount", 0) > 0:
                    results = await parse_results(data, entity, country)
                    if results:
                        break
            if results:
                break

        # Fallback to US if no results
        if not results and country != "us":
            await m.edit(f"🔎 No results in {country.upper()}. Trying US...")
            for q in attempts:
                for entity in ["song", "album", "artist", "playlist"]:
                    data = await search_itunes(q, entity, "us")
                    if data and data.get("resultCount", 0) > 0:
                        results = await parse_results(data, entity, "us")
                        country = "us"  # Update country for callback
                        if results:
                            break
                if results:
                    break

    except Exception as e:
        return await m.edit(f"❌ Error while searching: {str(e)}")

    if not results:
        return await m.edit(
            "⚠️ No results found on Apple Music. Try a simpler search or check spelling."
        )

    # Build buttons
    buttons, row = [], []
    for i, track in enumerate(results[:5], start=1):
        text = track["title"]
        if len(text) > 25:
            text = text[:22] + "..."
        row.append(InlineKeyboardButton(text=text, callback_data=f"apple:{i-1}:{query}:{country}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    text = f"🎵 Results for **{raw_query}** on Apple Music ({country.upper()}):\n\n"
    for i, track in enumerate(results[:5], start=1):
        text += f"{i}. {track['title']}\n"

    await m.edit(
        text,
        reply_markup=InlineKeyboardMarkup(buttons),
        disable_web_page_preview=True,
    )


# --------------------------
# Callback handler
# --------------------------
@app.on_callback_query(filters.regex(r"^apple:(\d+):(.+):([a-z]{2})"))
async def apple_callback(client, callback_query: CallbackQuery):
    """Handle callback queries for selecting Apple Music results."""
    index = int(callback_query.matches[0].group(1))
    query = callback_query.matches[0].group(2)
    country = callback_query.matches[0].group(3)

    results = []
    for entity in ["song", "album", "artist", "playlist"]:
        data = await search_itunes(query, entity, country)
        if data and data.get("resultCount", 0) > 0:
            results = await parse_results(data, entity, country)
            break

    if not results or index >= len(results):
        return await callback_query.answer("❌ Result not found.", show_alert=True)

    track = results[index]
    caption = (
        f"🎶 {track['title']}\n"
        f"👤 Artist: {track.get('artist', 'N/A')}\n"
        f"💽 Album: {track.get('album', 'N/A')}\n\n"
        f"🍎 [Open in Apple Music]({track['url']})"
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
