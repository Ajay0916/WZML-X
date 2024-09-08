#!/usr/bin/env python3
from asyncio import sleep as asleep
from aiofiles.os import path as aiopath, remove as aioremove, mkdir
import aiohttp  # Required for making HTTP requests to imghippo.com
from telegraph import upload_file

from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.filters import command, regex

from bot import bot, LOGGER, config_dict, DATABASE_URL
from bot.helper.telegram_helper.message_utils import sendMessage, editMessage, deleteMessage
from bot.helper.ext_utils.bot_utils import handleIndex, new_task
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.ext_utils.db_handler import DbManger
from bot.helper.telegram_helper.button_build import ButtonMaker

# Helper function to upload images to imghippo.com
async def upload_to_imghippo(image_path):
    upload_url = "https://www.imghippo.com/v1/upload"
    headers = {
        "Authorization": "Bearer JcYoJMRK4N92hzg4VIUjbKlOm9xC9CzS",  # Replace with your API key
    }

    async with aiohttp.ClientSession() as session:
        data = aiohttp.FormData()
        data.add_field('file', open(image_path, 'rb'), filename=image_path)

        async with session.post(upload_url, headers=headers, data=data) as resp:
            response_text = await resp.text()  # Capture the raw response text
            LOGGER.info(f"Imghippo Response: {response_text}")  # Log the response for debugging

            if resp.status == 200:
                response_json = await resp.json()
                if response_json.get("status") == "success":
                    return response_json["data"]["url"]  # Return the uploaded image URL
            return None
            

@new_task
async def picture_add(_, message):
    resm = message.reply_to_message
    editable = await sendMessage(message, "<i>Fetching Input ...</i>")
    pic_add = None  # Initialize pic_add to ensure it has a value

    if len(message.command) > 1 or resm and resm.text:
        msg_text = resm.text if resm else message.command[1]
        if not msg_text.startswith("http"):
            return await editMessage(editable, "<b>Not a Valid Link, Must Start with 'http'</b>")
        pic_add = msg_text.strip()
        await editMessage(editable, f"<b>Adding your Link :</b> <code>{pic_add}</code>")

    elif resm and resm.photo:
        if resm.photo.file_size > 5242880 * 2:
            return await editMessage(editable, "<i>Media is Not Supported! Only Photos!!</i>")
        try:
            photo_dir = await resm.download()
            await editMessage(editable, "<b>Now, Uploading to <code>imghippo.com</code>, Please Wait...</b>")
            await asleep(1)

            # Upload the photo to imghippo.com
            pic_add = await upload_to_imghippo(photo_dir)
            if pic_add:
                LOGGER.info(f"Imghippo Link : {pic_add}")
            else:
                raise Exception("Failed to get a valid URL from imghippo.")

        except Exception as e:
            LOGGER.error(f"Images Error: {str(e)}")
            await editMessage(editable, f"<b>Upload Failed:</b> {str(e)}")
        finally:
            await aioremove(photo_dir)

    # Check if pic_add is still None, which means there was an issue
    if not pic_add:
        return await editMessage(editable, "<b>Image upload failed or no valid image/link provided!</b>")

    config_dict['IMAGES'].append(pic_add)
    if DATABASE_URL:
        await DbManger().update_config({'IMAGES': config_dict['IMAGES']})
    await asleep(1.5)
    await editMessage(editable, f"<b><i>Successfully Added to Images List!</i></b>\n\n<b>• Total Images : {len(config_dict['IMAGES'])}</b>")

async def pictures(_, message):
    if not config_dict['IMAGES']:
        await sendMessage(message, f"<b>No Photo to Show !</b> Add by /{BotCommands.AddImageCommand}")
    else:
        to_edit = await sendMessage(message, "<i>Generating Grid of your Images...</i>")
        buttons = ButtonMaker()
        user_id = message.from_user.id
        buttons.ibutton("<<", f"images {user_id} turn -1")
        buttons.ibutton(">>", f"images {user_id} turn 1")
        buttons.ibutton("Remove Image", f"images {user_id} remov 0")
        buttons.ibutton("Close", f"images {user_id} close")
        buttons.ibutton("Remove All", f"images {user_id} removall", 'footer')
        await deleteMessage(to_edit)
        await sendMessage(message, f'🌄 <b>Image No. : 1 / {len(config_dict["IMAGES"])}</b>', buttons.build_menu(2), config_dict['IMAGES'][0])

@new_task
async def pics_callback(_, query):
    message = query.message
    user_id = query.from_user.id
    data = query.data.split()
    if user_id != int(data[1]):
        await query.answer(text="Not Authorized User!", show_alert=True)
        return
    if data[2] == "turn":
        await query.answer()
        ind = handleIndex(int(data[3]), config_dict['IMAGES'])
        no = len(config_dict['IMAGES']) - abs(ind+1) if ind < 0 else ind + 1
        pic_info = f'🌄 <b>Image No. : {no} / {len(config_dict["IMAGES"])}</b>'
        buttons = ButtonMaker()
        buttons.ibutton("<<", f"images {data[1]} turn {ind-1}")
        buttons.ibutton(">>", f"images {data[1]} turn {ind+1}")
        buttons.ibutton("Remove Image", f"images {data[1]} remov {ind}")
        buttons.ibutton("Close", f"images {data[1]} close")
        buttons.ibutton("Remove All", f"images {data[1]} removall", 'footer')
        await editMessage(message, pic_info, buttons.build_menu(2), config_dict['IMAGES'][ind])
    elif data[2] == "remov":
        config_dict['IMAGES'].pop(int(data[3]))
        if DATABASE_URL:
            await DbManger().update_config({'IMAGES': config_dict['IMAGES']})
        query.answer("Image Successfully Deleted", show_alert=True)
        if len(config_dict['IMAGES']) == 0:
            await deleteMessage(query.message)
            await sendMessage(message, f"<b>No Photo to Show !</b> Add by /{BotCommands.AddImageCommand}")
            return
        ind = int(data[3])+1
        ind = len(config_dict['IMAGES']) - abs(ind) if ind < 0 else ind
        pic_info = f'🌄 <b>Image No. : {ind+1} / {len(config_dict["IMAGES"])}</b>'
        buttons = ButtonMaker()
        buttons.ibutton("<<", f"images {data[1]} turn {ind-1}")
        buttons.ibutton(">>", f"images {data[1]} turn {ind+1}")
        buttons.ibutton("Remove Image", f"images {data[1]} remov {ind}")
        buttons.ibutton("Close", f"images {data[1]} close")
        buttons.ibutton("Remove All", f"images {data[1]} removall", 'footer')
        await editMessage(message, pic_info, buttons.build_menu(2), config_dict['IMAGES'][ind])
    elif data[2] == 'removall':
        config_dict['IMAGES'].clear()
        if DATABASE_URL:
            await DbManger().update_config({'IMAGES': config_dict['IMAGES']})
        await query.answer("All Images Successfully Deleted", show_alert=True)
        await sendMessage(message, f"<b>No Images to Show !</b> Add by /{BotCommands.AddImageCommand}")
        await deleteMessage(message)
    else:
        await query.answer()
        await deleteMessage(message)
        if message.reply_to_message:
            await deleteMessage(message.reply_to_message)

bot.add_handler(MessageHandler(picture_add, filters=command(BotCommands.AddImageCommand) & CustomFilters.authorized & ~CustomFilters.blacklisted))
bot.add_handler(MessageHandler(pictures, filters=command(BotCommands.ImagesCommand) & CustomFilters.authorized & ~CustomFilters.blacklisted))
bot.add_handler(CallbackQueryHandler(pics_callback, filters=regex(r'^images')))
        
