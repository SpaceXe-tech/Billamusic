import asyncio
from typing import Union

from AnonXMusic.misc import db
from AnonXMusic.utils.formatters import check_duration, seconds_to_min
from config import autoclean, time_to_seconds


async def put_queue(
    chat_id,
    original_chat_id,
    file,
    title,
    duration,
    user,
    vidid,
    user_id,
    stream,
    forceplay: Union[bool, str] = None,
    apple_metadata: Union[dict, None] = None,  # New parameter for Apple Music metadata
):
    put = {
        "file": file,
        "title": title,
        "dur": duration,
        "by": user,
        "chat_id": original_chat_id,
        "user_id": user_id,
        "vidid": vidid,
        "streamtype": stream,
        "played": 0,
    }

    # Add Apple Music metadata if provided
    if apple_metadata:
        put["apple_metadata"] = apple_metadata

    if not db.get(chat_id):
        db[chat_id] = []
    if forceplay:
        db[chat_id].insert(0, put)
    else:
        db[chat_id].append(put)


async def put_queue_index(
    chat_id,
    original_chat_id,
    file,
    title,
    duration,
    user,
    vidid,
    stream,
    forceplay: Union[bool, str] = None,
):
    put = {
        "file": file,
        "title": title,
        "dur": duration,
        "by": user,
        "chat_id": original_chat_id,
        "vidid": vidid,
        "streamtype": stream,
        "played": 0,
    }
    if not db.get(chat_id):
        db[chat_id] = []
    if forceplay:
        db[chat_id].insert(0, put)
    else:
        db[chat_id].append(put)
