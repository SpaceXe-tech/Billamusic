
from pyrogram import filters
from pyrogram.types import Message

from AnonXMusic import YouTube, app
from AnonXMusic.core.call import Anony
from AnonXMusic.misc import db
from AnonXMusic.utils import AdminRightsCheck, seconds_to_min, time_to_seconds
from AnonXMusic.utils.inline import close_markup
from config import BANNED_USERS


@app.on_message(
    filters.command(["seek", "cseek", "seekback", "cseekback"])
    & filters.group
    & ~BANNED_USERS
)
@AdminRightsCheck
async def seek_comm(cli, message: Message, _, chat_id):
    if len(message.command) == 1:
        return await message.reply_text(_["admin_20"])
    query = message.text.split(None, 1)[1].strip()
    if not query.isnumeric():
        return await message.reply_text(_["admin_21"])
    playing = db.get(chat_id)
    if not playing:
        return await message.reply_text(_["queue_2"])

    # Enhanced error handling for missing 'seconds' field
    try:
        duration_seconds = int(playing[0]["seconds"])
    except KeyError:
        # If 'seconds' field is missing, try to calculate from duration
        duration_str = playing[0].get("dur", "0:00")
        try:
            duration_seconds = time_to_seconds(duration_str)
            # Update the queue item with the calculated seconds
            db[chat_id][0]["seconds"] = duration_seconds
        except:
            # If duration calculation fails, try to get from Apple Music metadata
            apple_metadata = playing[0].get("apple_metadata", {})
            apple_duration_ms = apple_metadata.get("apple_duration_ms", 0)
            if apple_duration_ms > 0:
                duration_seconds = apple_duration_ms // 1000
                db[chat_id][0]["seconds"] = duration_seconds
            else:
                return await message.reply_text(_["admin_22"])

    if duration_seconds == 0:
        return await message.reply_text(_["admin_22"])

    file_path = playing[0]["file"]
    duration_played = int(playing[0].get("played", 0))
    duration_to_skip = int(query)
    duration = playing[0]["dur"]

    if message.command[0][-2] == "c":
        if (duration_played - duration_to_skip) <= 10:
            return await message.reply_text(
                text=_["admin_23"].format(seconds_to_min(duration_played), duration),
                reply_markup=close_markup(_),
            )
        to_seek = duration_played - duration_to_skip + 1
    else:
        if (duration_seconds - (duration_played + duration_to_skip)) <= 10:
            return await message.reply_text(
                text=_["admin_23"].format(seconds_to_min(duration_played), duration),
                reply_markup=close_markup(_),
            )
        to_seek = duration_played + duration_to_skip + 1

    mystic = await message.reply_text(_["admin_24"])

    if "vid_" in file_path:
        n, file_path = await YouTube.video(playing[0]["vidid"], True)
        if n == 0:
            return await message.reply_text(_["admin_22"])

    check = (playing[0]).get("speed_path")
    if check:
        file_path = check
    if "index_" in file_path:
        file_path = playing[0]["vidid"]

    try:
        await Anony.seek_stream(
            chat_id,
            file_path,
            seconds_to_min(to_seek),
            duration,
            playing[0]["streamtype"],
        )
    except:
        return await mystic.edit_text(_["admin_26"], reply_markup=close_markup(_))

    if message.command[0][-2] == "c":
        db[chat_id][0]["played"] -= duration_to_skip
    else:
        db[chat_id][0]["played"] += duration_to_skip

    await mystic.edit_text(
        text=_["admin_25"].format(seconds_to_min(to_seek), message.from_user.mention),
        reply_markup=close_markup(_),
    )
