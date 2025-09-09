from AnonXMusic import app
from pyrogram.types import InlineKeyboardButton

def start_panel(_):
    buttons = [
        [
            InlineKeyboardButton(
                text="ᴡᴇʙ ᴘʟᴀʏᴇʀ",
                url=f"https://t.me/{app.username.lstrip('@')}?startapp"
            ),
        ],
        [
            InlineKeyboardButton(
                text="ʟᴀɴɢᴜᴀɢᴇ",
                callback_data="LG"
            ),
        ],
    ]
    return buttons

def private_panel(_):
    buttons = [
        [
            InlineKeyboardButton(
                text=_["S_B_4"],
                callback_data="settings_back_helper"
            ),
        ],
        [
            InlineKeyboardButton(
                text="ʟᴀɴɢᴜᴀɢᴇ",
                callback_data="LG"
            ),
            InlineKeyboardButton(
                text=_["S_B_6"],
                url=config.SUPPORT_CHANNEL
            ),
        ],
    ]
    return buttons
