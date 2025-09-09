from pyrogram import filters
from pyrogram.enums import ChatType
from pyrogram.errors import MessageNotModified
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from AnonXMusic import app
from AnonXMusic.utils.database import (
    add_nonadmin_chat,
    get_authuser,
    get_authuser_names,
    get_playmode,
    get_playtype,
    get_upvote_count,
    is_nonadmin_chat,
    is_skipmode,
    remove_nonadmin_chat,
    set_playmode,
    set_playtype,
    set_upvotes,
    skip_off,
    skip_on,
)
from AnonXMusic.utils.decorators.admins import ActualAdminCB
from AnonXMusic.utils.decorators.language import language, languageCB
from AnonXMusic.utils.inline.settings import (
    auth_users_markup,
    playmode_users_markup,
    setting_markup,
    vote_mode_markup,
)
from AnonXMusic.utils.inline.start import private_panel
from config import BANNED_USERS, OWNER_ID


@app.on_message(
    filters.command(["settings", "setting"]) & filters.group & ~BANNED_USERS
)
@language
async def settings_mar(client, message: Message, _):
    buttons = setting_markup(_)
    await message.reply_text(
        _["setting_1"].format(app.mention, message.chat.id, message.chat.title),
        reply_markup=InlineKeyboardMarkup(buttons),
    )


@app.on_callback_query(filters.regex("settings_helper") & ~BANNED_USERS)
@languageCB
async def settings_cb(client, callback_query, _):
    try:
        await callback_query.answer(_["set_cb_5"])
    except:
        pass
    buttons = setting_markup(_)
    return await callback_query.edit_message_text(
        _["setting_1"].format(
            app.mention,
            callback_query.message.chat.id,
            callback_query.message.chat.title,
        ),
        reply_markup=InlineKeyboardMarkup(buttons),
    )


@app.on_callback_query(filters.regex("settingsback_helper") & ~BANNED_USERS)
@languageCB
async def settings_back_markup(client, callback_query: CallbackQuery, _):
    try:
        await callback_query.answer()
    except:
        pass
    if callback_query.message.chat.type == ChatType.PRIVATE:
        await app.resolve_peer(OWNER_ID)
        OWNER = OWNER_ID
        buttons = private_panel(_)
        return await callback_query.edit_message_text(
            _["start_2"].format(callback_query.from_user.mention, app.mention),
            reply_markup=InlineKeyboardMarkup(buttons),
        )
    else:
        buttons = setting_markup(_)
        return await callback_query.edit_message_reply_markup(
            reply_markup=InlineKeyboardMarkup(buttons)
        )


@app.on_callback_query(
    filters.regex(
        pattern=r"^(SEARCHANSWER|PLAYMODEANSWER|PLAYTYPEANSWER|AUTHANSWER|ANSWERVOMODE|VOTEANSWER|PM|AU|VM)$"
    )
    & ~BANNED_USERS
)
@languageCB
async def without_Admin_rights(client, callback_query, _):
    command = callback_query.matches[0].group(1)
    if command == "SEARCHANSWER":
        try:
            return await callback_query.answer(_["setting_2"], show_alert=True)
        except:
            return
    if command == "PLAYMODEANSWER":
        try:
            return await callback_query.answer(_["setting_5"], show_alert=True)
        except:
            return
    if command == "PLAYTYPEANSWER":
        try:
            return await callback_query.answer(_["setting_6"], show_alert=True)
        except:
            return
    if command == "AUTHANSWER":
        try:
            return await callback_query.answer(_["setting_3"], show_alert=True)
        except:
            return
    if command == "VOTEANSWER":
        try:
            return await callback_query.answer(
                _["setting_8"],
                show_alert=True,
            )
        except:
            return
    if command == "ANSWERVOMODE":
        current = await get_upvote_count(callback_query.message.chat.id)
        try:
            return await callback_query.answer(
                _["setting_9"].format(current),
                show_alert=True,
            )
        except:
            return
    if command == "PM":
        try:
            await callback_query.answer(_["set_cb_2"], show_alert=True)
        except:
            pass
        playmode = await get_playmode(callback_query.message.chat.id)
        Direct = playmode == "Direct"
        is_non_admin = await is_nonadmin_chat(callback_query.message.chat.id)
        Group = not is_non_admin
        playty = await get_playtype(callback_query.message.chat.id)
        Playtype = playty != "Everyone"
        buttons = playmode_users_markup(_, Direct, Group, Playtype)
    if command == "AU":
        try:
            await callback_query.answer(_["set_cb_1"], show_alert=True)
        except:
            pass
        is_non_admin = await is_nonadmin_chat(callback_query.message.chat.id)
        if not is_non_admin:
            buttons = auth_users_markup(_, True)
        else:
            buttons = auth_users_markup(_)
    if command == "VM":
        mode = await is_skipmode(callback_query.message.chat.id)
        current = await get_upvote_count(callback_query.message.chat.id)
        buttons = vote_mode_markup(_, current, mode)
    try:
        return await callback_query.edit_message_reply_markup(
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except MessageNotModified:
        return


@app.on_callback_query(filters.regex("FERRARIUDTI") & ~BANNED_USERS)
@ActualAdminCB
async def addition(client, callback_query, _):
    callback_data = callback_query.data.strip()
    mode = callback_data.split(None, 1)[1]
    if not await is_skipmode(callback_query.message.chat.id):
        return await callback_query.answer(_["setting_10"], show_alert=True)
    current = await get_upvote_count(callback_query.message.chat.id)
    if mode == "M":
        final = current - 2
        print(final)
        if final == 0:
            return await callback_query.answer(
                _["setting_11"],
                show_alert=True,
            )
        if final <= 2:
            final = 2
        await set_upvotes(callback_query.message.chat.id, final)
    else:
        final = current + 2
        print(final)
        if final == 17:
            return await callback_query.answer(
                _["setting_12"],
                show_alert=True,
            )
        if final >= 15:
            final = 15
        await set_upvotes(callback_query.message.chat.id, final)
    buttons = vote_mode_markup(_, final, True)
    try:
        return await callback_query.edit_message_reply_markup(
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except MessageNotModified:
        return


@app.on_callback_query(
    filters.regex(pattern=r"^(MODECHANGE|CHANNELMODECHANGE|PLAYTYPECHANGE)$")
    & ~BANNED_USERS
)
@ActualAdminCB
async def playmode_ans(client, callback_query, _):
    command = callback_query.matches[0].group(1)
    if command == "CHANNELMODECHANGE":
        is_non_admin = await is_nonadmin_chat(callback_query.message.chat.id)
        if not is_non_admin:
            await add_nonadmin_chat(callback_query.message.chat.id)
            Group = None
        else:
            await remove_nonadmin_chat(callback_query.message.chat.id)
            Group = True
        playmode = await get_playmode(callback_query.message.chat.id)
        Direct = playmode == "Direct"
        playty = await get_playtype(callback_query.message.chat.id)
        Playtype = playty != "Everyone"
        buttons = playmode_users_markup(_, Direct, Group, Playtype)
    if command == "MODECHANGE":
        try:
            await callback_query.answer(_["set_cb_3"], show_alert=True)
        except:
            pass
        playmode = await get_playmode(callback_query.message.chat.id)
        if playmode == "Direct":
            await set_playmode(callback_query.message.chat.id, "Inline")
            Direct = None
        else:
            await set_playmode(callback_query.message.chat.id, "Direct")
            Direct = True
        is_non_admin = await is_nonadmin_chat(callback_query.message.chat.id)
        Group = not is_non_admin
        playty = await get_playtype(callback_query.message.chat.id)
        Playtype = playty != "Everyone"
        buttons = playmode_users_markup(_, Direct, Group, Playtype)
    if command == "PLAYTYPECHANGE":
        try:
            await callback_query.answer(_["set_cb_3"], show_alert=True)
        except:
            pass
        playty = await get_playtype(callback_query.message.chat.id)
        if playty == "Everyone":
            await set_playtype(callback_query.message.chat.id, "Admin")
            Playtype = False
        else:
            await set_playtype(callback_query.message.chat.id, "Everyone")
            Playtype = True
        playmode = await get_playmode(callback_query.message.chat.id)
        Direct = playmode == "Direct"
        is_non_admin = await is_nonadmin_chat(callback_query.message.chat.id)
        Group = not is_non_admin
        buttons = playmode_users_markup(_, Direct, Group, Playtype)
    try:
        return await callback_query.edit_message_reply_markup(
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except MessageNotModified:
        return


@app.on_callback_query(filters.regex(pattern=r"^(AUTH|AUTHLIST)$") & ~BANNED_USERS)
@ActualAdminCB
async def authusers_mar(client, callback_query, _):
    command = callback_query.matches[0].group(1)
    if command == "AUTHLIST":
        _authusers = await get_authuser_names(callback_query.message.chat.id)
        if not _authusers:
            try:
                return await callback_query.answer(_["setting_4"], show_alert=True)
            except:
                return
        else:
            try:
                await callback_query.answer(_["set_cb_4"], show_alert=True)
            except:
                pass
            j = 0
            await callback_query.edit_message_text(_["auth_6"])
            msg = _["auth_7"].format(callback_query.message.chat.title)
            for note in _authusers:
                _note = await get_authuser(callback_query.message.chat.id, note)
                user_id = _note["auth_user_id"]
                admin_id = _note["admin_id"]
                admin_name = _note["admin_name"]
                try:
                    user = await app.get_users(user_id)
                    user = user.first_name
                    j += 1
                except:
                    continue
                msg += f"{j}➤ {user}[<code>{user_id}</code>]\n"
                msg += f"   {_['auth_8']} {admin_name}[<code>{admin_id}</code>]\n\n"
            upl = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            text=_["BACK_BUTTON"], callback_data=f"AU"
                        ),
                        InlineKeyboardButton(
                            text=_["CLOSE_BUTTON"],
                            callback_data=f"close",
                        ),
                    ]
                ]
            )
            try:
                return await callback_query.edit_message_text(msg, reply_markup=upl)
            except MessageNotModified:
                return
    try:
        await callback_query.answer(_["set_cb_3"], show_alert=True)
    except:
        pass
    if command == "AUTH":
        is_non_admin = await is_nonadmin_chat(callback_query.message.chat.id)
        if not is_non_admin:
            await add_nonadmin_chat(callback_query.message.chat.id)
            buttons = auth_users_markup(_)
        else:
            await remove_nonadmin_chat(callback_query.message.chat.id)
            buttons = auth_users_markup(_, True)
    try:
        return await callback_query.edit_message_reply_markup(
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except MessageNotModified:
        return


@app.on_callback_query(filters.regex("VOMODECHANGE") & ~BANNED_USERS)
@ActualAdminCB
async def vote_change(client, callback_query, _):
    try:
        await callback_query.answer(_["set_cb_3"], show_alert=True)
    except:
        pass

    mod = None
    if await is_skipmode(callback_query.message.chat.id):
        await skip_off(callback_query.message.chat.id)
    else:
        mod = True
        await skip_on(callback_query.message.chat.id)

    current = await get_upvote_count(callback_query.message.chat.id)
    buttons = vote_mode_markup(_, current, mod)

    try:
        return await callback_query.edit_message_reply_markup(
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except MessageNotModified:
        return
