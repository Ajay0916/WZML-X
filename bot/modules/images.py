#!/usr/bin/env python3
from asyncio import sleep as asleep
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.filters import command, regex

from bot import bot, LOGGER, config_dict, DATABASE_URL
from bot.helper.telegram_helper.message_utils import sendMessage, editMessage, deleteMessage
from bot.helper.ext_utils.bot_utils import handleIndex, new_task
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.ext_utils.db_handler import DbManger
from bot.helper.telegram_helper.button_build import ButtonMaker


# Function to get all image files in the specified Google Drive folder
async def get_drive_image_links(service, folder_id):
    query = f"'{folder_id}' in parents and mimeType contains 'image/'"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    items = results.get('files', [])
    
    image_links = []
    for item in items:
        file_id = item['id']
        file_name = item['name']
        image_link = f"https://drive.google.com/uc?id={file_id}"  # Google Drive direct link format
        image_links.append(image_link)
    return image_links


# Function to make files public
def make_files_public(service, file_id):
    try:
        permission = {
            'role': 'reader',
            'type': 'anyone',
        }
        service.permissions().create(fileId=file_id, body=permission).execute()
    except HttpError as error:
        LOGGER.error(f"An error occurred: {error}")
        return None


@new_task
async def picture_add(_, message):
    resm = message.reply_to_message
    editable = await sendMessage(message, "<i>Fetching Input ...</i>")
    
    if len(message.command) > 1 or resm and resm.text:
        msg_text = resm.text if resm else message.command[1]
        if not msg_text.startswith("http"):
            return await editMessage(editable, "<b>Not a Valid Link, Must Start with 'http'</b>")
        
        if "drive.google.com" in msg_text:
            folder_id = msg_text.split("/")[-1]  # Extract folder ID from the Google Drive URL
            service = build('drive', 'v3')  # Assuming Google Drive credentials are set up properly

            # Fetch all image links from the Google Drive folder
            image_links = await get_drive_image_links(service, folder_id)
            if not image_links:
                return await editMessage(editable, "<b>No images found in the Google Drive folder!</b>")
            
            # Make all images public
            for image in image_links:
                make_files_public(service, image.split('=')[1])

            # Add all image links to config_dict['IMAGES']
            config_dict['IMAGES'].extend(image_links)
            if DATABASE_URL:
                await DbManger().update_config({'IMAGES': config_dict['IMAGES']})

            await asleep(1.5)
            await editMessage(editable, f"<b><i>Successfully Added {len(image_links)} Images to the List!</i></b>\n\n<b>• Total Images : {len(config_dict['IMAGES'])}</b>")
        else:
            # Handle adding from a direct link
            pic_add = msg_text.strip()
            await editMessage(editable, f"<b>Adding your Link :</b> <code>{pic_add}</code>")
            config_dict['IMAGES'].append(pic_add)
            if DATABASE_URL:
                await DbManger().update_config({'IMAGES': config_dict['IMAGES']})
            await asleep(1.5)
            await editMessage(editable, f"<b><i>Successfully Added to Images List!</i></b>\n\n<b>• Total Images : {len(config_dict['IMAGES'])}</b>")
    
    elif resm and resm.photo:
        # Handle adding a photo from a Telegram message
        if resm.photo.file_size > 5242880 * 2:
            return await editMessage(editable, "<i>Media is Not Supported! Only Photos!!</i>")
        try:
            photo_dir = await resm.download()
            await editMessage(editable, "<b>Now, Uploading to <code>graph.org</code>, Please Wait...</b>")
            await asleep(1)
            pic_add = f'https://graph.org{upload_file(photo_dir)[0]}'
            LOGGER.info(f"Telegraph Link : {pic_add}")
            config_dict['IMAGES'].append(pic_add)
        except Exception as e:
            LOGGER.error(f"Images Error: {str(e)}")
            await editMessage(editable, str(e))
        finally:
            await aioremove(photo_dir)

        if DATABASE_URL:
            await DbManger().update_config({'IMAGES': config_dict['IMAGES']})
        await asleep(1.5)
        await editMessage(editable, f"<b><i>Successfully Added to Images List!</i></b>\n\n<b>• Total Images : {len(config_dict['IMAGES'])}</b>")
    
    else:
        help_msg = "<b>By Replying to Link (Telegra.ph or DDL):</b>"
        help_msg += f"\n<code>/{BotCommands.AddImageCommand} {{link}}</code>\n"
        help_msg += "\n<b>By Replying to Photo on Telegram:</b>"
        help_msg += f"\n<code>/{BotCommands.AddImageCommand} {{photo}}</code>"
        return await editMessage(editable, help_msg)


# Other handlers and callbacks remain the same


bot.add_handler(MessageHandler(picture_add, filters=command(BotCommands.AddImageCommand) & CustomFilters.authorized & ~CustomFilters.blacklisted))
bot.add_handler(MessageHandler(pictures, filters=command(BotCommands.ImagesCommand) & CustomFilters.authorized & ~CustomFilters.blacklisted))
bot.add_handler(CallbackQueryHandler(pics_callback, filters=regex(r'^images')))
