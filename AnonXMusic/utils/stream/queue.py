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
    apple_metadata: Union[dict, None] = None,
):
    """
    Enhanced queue function that ensures 'seconds' field is always present
    """
    # Calculate duration in seconds
    try:
        if isinstance(duration, str) and ":" in duration:
            duration_seconds = time_to_seconds(duration)
        elif isinstance(duration, int):
            duration_seconds = duration
        else:
            duration_seconds = 0
    except:
        duration_seconds = 0

    # If duration_seconds is still 0, try to get from Apple Music metadata
    if duration_seconds == 0 and apple_metadata:
        apple_duration_ms = apple_metadata.get("apple_duration_ms", 0)
        if apple_duration_ms > 0:
            duration_seconds = apple_duration_ms // 1000

    put = {
        "file": file,
        "title": title,
        "dur": duration,
        "seconds": duration_seconds,  # Always include seconds field
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
    """
    Enhanced index queue function that ensures 'seconds' field is always present
    """
    # Calculate duration in seconds
    try:
        if isinstance(duration, str) and ":" in duration:
            duration_seconds = time_to_seconds(duration)
        elif isinstance(duration, int):
            duration_seconds = duration
        else:
            duration_seconds = 0
    except:
        duration_seconds = 0

    put = {
        "file": file,
        "title": title,
        "dur": duration,
        "seconds": duration_seconds,  # Always include seconds field
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


async def fix_existing_queue_items():
    """
    Utility function to fix existing queue items that may be missing 'seconds' field
    Call this once during bot startup to fix any existing queue data
    """
    for chat_id in db:
        if isinstance(db[chat_id], list):
            for i, item in enumerate(db[chat_id]):
                if "seconds" not in item:
                    # Try to calculate seconds from duration
                    duration = item.get("dur", "0:00")
                    try:
                        if isinstance(duration, str) and ":" in duration:
                            duration_seconds = time_to_seconds(duration)
                        else:
                            duration_seconds = 0
                    except:
                        duration_seconds = 0

                    # If still 0, try Apple Music metadata
                    if duration_seconds == 0:
                        apple_metadata = item.get("apple_metadata", {})
                        apple_duration_ms = apple_metadata.get("apple_duration_ms", 0)
                        if apple_duration_ms > 0:
                            duration_seconds = apple_duration_ms // 1000

                    # Add seconds field to existing item
                    db[chat_id][i]["seconds"] = duration_seconds
                    print(f"Fixed queue item in chat {chat_id}: added seconds={duration_seconds}")
