#!/usr/bin/env python3
from asyncio import sleep as asleep
from aiofiles.os import path as aiopath, remove as aioremove, mkdir

from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.filters import command, regex

from bot import bot, LOGGER, config_dict, DATABASE_URL
from bot.helper.telegram_helper.message_utils import sendMessage, editMessage, deleteMessage
from bot.helper.ext_utils.bot_utils import handleIndex, new_task
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.ext_utils.db_handler import DbManger
from bot.helper.telegram_helper.button_build import ButtonMaker

@new_task
async def picture_add(_, message):
    resm = message.reply_to_message
    editable = await sendMessage(message, "<i>Fetching Input ...</i>")
    if len(message.command) > 1 or resm and resm.text:
        msg_text = resm.text if resm else message.command[1]
        if not msg_text.startswith("http"):
            return await editMessage(editable, "<b>Not a Valid Link, Must Start with 'http'</b>")
        pic_add = msg_text.strip()
        await editMessage(editable, f"<b>Adding your Link :</b> <code>{pic_add}</code>")
    elif resm:
        if resm.photo:
            if resm.photo.file_size > 5242880 * 2:
                return await editMessage(editable, "<i>Media is Not Supported! Only Photos!!</i>")
            file_id = resm.photo.file_id
            pic_add = f'https://t.me/{bot.get_me().username}/{file_id}'
        elif resm.document:
            file_id = resm.document.file_id
            pic_add = f'https://t.me/{bot.get_me().username}/{file_id}'
        else:
            return await editMessage(editable, "<i>Unsupported Media Type!</i>")
        LOGGER.info(f"Telegram File Link : {pic_add}")
    else:
        help_msg = "<b>By Replying to Link (Telegra.ph or DDL):</b>"
        help_msg += f"\n<code>/{BotCommands.AddImageCommand}" + " {link}" + "</code>\n"
        help_msg += "\n<b>By Replying to Photo or File on Telegram:</b>"
        help_msg += f"\n<code>/{BotCommands.AddImageCommand}" + " {photo or file}" + "</code>"
        return await editMessage(editable, help_msg)
    
    config_dict['FILES'].append(pic_add)
    if DATABASE_URL:
        await DbManger().update_config({'FILES': config_dict['FILES']})
    await asleep(1.5)
    await editMessage(editable, f"<b><i>Successfully Added to Files List!</i></b>\n\n<b>• Total Files : {len(config_dict['FILES'])}</b>")

async def files(_, message):
    if not config_dict['FILES']:
        await sendMessage(message, f"<b>No File to Show !</b> Add by /{BotCommands.AddFileCommand}")
    else:
        to_edit = await sendMessage(message, "<i>Generating Grid of your Files...</i>")
        buttons = ButtonMaker()
        user_id = message.from_user.id
        buttons.ibutton("<<", f"files {user_id} turn -1")
        buttons.ibutton(">>", f"files {user_id} turn 1")
        buttons.ibutton("Remove File", f"files {user_id} remov 0")
        buttons.ibutton("Close", f"files {user_id} close")
        buttons.ibutton("Remove All", f"files {user_id} removall", 'footer')
        await deleteMessage(to_edit)
        await sendMessage(message, f'📁 <b>File No. : 1 / {len(config_dict["FILES"])}</b>', buttons.build_menu(2), config_dict['FILES'][0])

@new_task
async def files_callback(_, query):
    message = query.message
    user_id = query.from_user.id
    data = query.data.split()
    if user_id != int(data[1]):
        await query.answer(text="Not Authorized User!", show_alert=True)
        return
    if data[2] == "turn":
        await query.answer()
        ind = handleIndex(int(data[3]), config_dict['FILES'])
        no = len(config_dict['FILES']) - abs(ind+1) if ind < 0 else ind + 1
        file_info = f'📁 <b>File No. : {no} / {len(config_dict["FILES"])}</b>'
        buttons = ButtonMaker()
        buttons.ibutton("<<", f"files {data[1]} turn {ind-1}")
        buttons.ibutton(">>", f"files {data[1]} turn {ind+1}")
        buttons.ibutton("Remove File", f"files {data[1]} remov {ind}")
        buttons.ibutton("Close", f"files {data[1]} close")
        buttons.ibutton("Remove All", f"files {data[1]} removall", 'footer')
        await editMessage(message, file_info, buttons.build_menu(2), config_dict['FILES'][ind])
    elif data[2] == "remov":
        config_dict['FILES'].pop(int(data[3]))
        if DATABASE_URL:
            await DbManger().update_config({'FILES': config_dict['FILES']})
        query.answer("File Successfully Deleted", show_alert=True)
        if len(config_dict['FILES']) == 0:
            await deleteMessage(query.message)
            await sendMessage(message, f"<b>No File to Show !</b> Add by /{BotCommands.AddFileCommand}")
            return
        ind = int(data[3])+1
        ind = len(config_dict['FILES']) - abs(ind) if ind < 0 else ind
        file_info = f'📁 <b>File No. : {ind+1} / {len(config_dict["FILES"])}</b>'
        buttons = ButtonMaker()
        buttons.ibutton("<<", f"files {data[1]} turn {ind-1}")
        buttons.ibutton(">>", f"files {data[1]} turn {ind+1}")
        buttons.ibutton("Remove File", f"files {data[1]} remov {ind}")
        buttons.ibutton("Close", f"files {data[1]} close")
        buttons.ibutton("Remove All", f"files {data[1]} removall", 'footer')
        await editMessage(message, file_info, buttons.build_menu(2), config_dict['FILES'][ind])
    elif data[2] == 'removall':
        config_dict['FILES'].clear()
        if DATABASE_URL:
            await DbManger().update_config({'FILES': config_dict['FILES']})
        await query.answer("All Files Successfully Deleted", show_alert=True)
        await sendMessage(message, f"<b>No Files to Show !</b> Add by /{BotCommands.AddFileCommand}")
        await deleteMessage(message)
    else:
        await query.answer()
        await deleteMessage(message)
        if message.reply_to_message:
            await deleteMessage(message.reply_to_message)

bot.add_handler(MessageHandler(picture_add, filters=command(BotCommands.AddFileCommand) & CustomFilters.authorized & ~CustomFilters.blacklisted))
bot.add_handler(MessageHandler(files, filters=command(BotCommands.FilesCommand) & CustomFilters.authorized & ~CustomFilters.blacklisted))
bot.add_handler(CallbackQueryHandler(files_callback, filters=regex(r'^files')))
