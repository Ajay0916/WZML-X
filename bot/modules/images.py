import logging
import aiohttp
import asyncio
from aiofiles.os import remove as aioremove
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.filters import command, regex

from bot import bot, config_dict, DATABASE_URL
from bot.helper.telegram_helper.message_utils import sendMessage, editMessage, deleteMessage
from bot.helper.ext_utils.bot_utils import handleIndex, new_task, arg_parser
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.ext_utils.db_handler import DbManger
from bot.helper.telegram_helper.button_build import ButtonMaker

# Configure the logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
LOGGER = logging.getLogger(__name__)

async def upload_to_imghippo(image_path):
    upload_url = "https://www.imghippo.com/v1/upload"
    data = aiohttp.FormData()
    data.add_field('file', open(image_path, 'rb'), filename=image_path)
    data.add_field('api_key', f'{config_dict["IMGAPI"]}')  # API key as form data

    async with aiohttp.ClientSession() as session:
        async with session.post(upload_url, data=data) as resp:
            response_json = await resp.json()
            if resp.status == 200 and response_json.get("success"):
                return response_json.get("data", {}).get("url")
            return None

@new_task
async def picture_add(_, message):
    editable = await sendMessage(message, "<i>Fetching Input ...</i>")
    
    # Parse arguments using arg_parser from bot_utils
    args = arg_parser(message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else "")
    
    pic_add = None

    if args:
        # Check for the -i argument and get the number of next messages to process
        if args.i:
            num_messages = int(args.i)
            if num_messages <= 0:
                return await editMessage(editable, "<b>Invalid number of messages to process!</b>")
            
            # Fetch the next messages after the current message
            next_messages = await bot.get_chat_history(message.chat.id, limit=num_messages, offset_id=message.message_id)
            
            for resm in next_messages:
                if resm.photo:
                    # Handle the photo
                    if resm.photo.file_size > 5242880 * 2:
                        await editMessage(editable, "<i>Media is Not Supported! Only Photos!!</i>")
                        continue
                    try:
                        photo_dir = await resm.download()
                        await editMessage(editable, "<b>Now, Uploading to <code>Imghippo</code>, Please Wait...</b>")
                        await asyncio.sleep(1)
                        pic_add = await upload_to_imghippo(photo_dir)
                        if pic_add:
                            LOGGER.info(f"Imghippo Link : {pic_add}")
                        else:
                            raise Exception("Failed to get a valid URL from Imghippo.")
                    except Exception as e:
                        await editMessage(editable, str(e))
                    finally:
                        await aioremove(photo_dir)

                elif resm.text:
                    # Handle the text message link
                    msg_text = resm.text.strip()
                    if not msg_text.startswith("http"):
                        await editMessage(editable, "<b>Not a Valid Link, Must Start with 'http'</b>")
                        continue
                    pic_add = msg_text
                    await editMessage(editable, f"<b>Adding your Link :</b> <code>{pic_add}</code>")

            if pic_add:
                config_dict['IMAGES'].append(pic_add)
                if DATABASE_URL:
                    await DbManger().update_config({'IMAGES': config_dict['IMAGES']})
                await asyncio.sleep(1.5)
                await editMessage(editable, f"<b><i>Successfully Added to Images List!</i></b>\n\n<b>• Total Images : {len(config_dict['IMAGES'])}</b>")
            else:
                await editMessage(editable, "<b>Failed to upload image.</b>")
            
            # Recursively call the bot to process the next messages if num_messages > 1
            if num_messages > 1:
                await bot.send_message(
                    chat_id=message.chat.id,
                    text=f"/{BotCommands.AddImageCommand} -i {num_messages - 1}",
                    reply_to_message_id=message.message_id
                )

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
        no = len(config_dict['IMAGES']) - abs(ind + 1) if ind < 0 else ind + 1
        pic_info = f'🌄 <b>Image No. : {no} / {len(config_dict["IMAGES"])}</b>'
        buttons = ButtonMaker()
        buttons.ibutton("<<", f"images {data[1]} turn {ind - 1}")
        buttons.ibutton(">>", f"images {data[1]} turn {ind + 1}")
        buttons.ibutton("Remove Image", f"images {data[1]} remov {ind}")
        buttons.ibutton("Close", f"images {data[1]} close")
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
        ind = int(data[3]) + 1
        ind = len(config_dict['IMAGES']) - abs(ind) if ind < 0 else ind
        pic_info = f'🌄 <b>Image No. : {ind + 1} / {len(config_dict["IMAGES"])}</b>'
        buttons = ButtonMaker()
        buttons.ibutton("<<", f"images {data[1]} turn {ind - 1}")
        buttons.ibutton(">>", f"images {data[1]} turn {ind + 1}")
        buttons.ibutton("Remove Image", f"images {data[1]} remov {ind}")
        buttons.ibutton("Close", f"images {data[1]} close")
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
