#!/usr/bin/env python3
from pathlib import Path
from aiofiles.os import scandir, path as aiopath
from aiofiles import open as aiopen
from aiohttp import ClientSession
from bot import config_dict, LOGGER
from bot.helper.ext_utils.telegraph_helper import telegraph
from pyrogram.errors import RPCError

ALLOWED_EXTS = [
    '.avi', '.mkv', '.mpg', '.mpeg', '.vob', '.wmv', '.flv', '.mp4', '.mov', '.m4v',
    '.m2v', '.divx', '.3gp', '.webm', '.ogv', '.ogg', '.ts', '.ogm'
]

class Streamtape:
    def __init__(self, dluploader, login, key):
        self.__userLogin = login
        self.__passKey = key
        self.dluploader = dluploader
        self.base_url = 'https://api.streamtape.com'
        self.session = ClientSession()  # Use a single session for the lifetime of the instance

    async def __getAccInfo(self):
        url = f"{self.base_url}/account/info?login={self.__userLogin}&key={self.__passKey}"
        try:
            async with self.session.get(url) as response:
                response.raise_for_status()
                data = await response.json()
                if data.get("status") == 200:
                    return data.get("result")
        except Exception as e:
            LOGGER.error(f"Failed to get account info: {e}")
        return None

    async def __getUploadURL(self, folder=None, sha256=None, httponly=False):
        _url = f"{self.base_url}/file/ul?login={self.__userLogin}&key={self.__passKey}"
        if folder is not None:
            _url += f"&folder={folder}"
        if sha256 is not None:
            _url += f"&sha256={sha256}"
        if httponly:
            _url += "&httponly=true"
        try:
            async with self.session.get(_url) as response:
                response.raise_for_status()
                data = await response.json()
                if data.get("status") == 200:
                    return data.get("result")
        except Exception as e:
            LOGGER.error(f"Failed to get upload URL: {e}")
        return None

    async def upload_file(self, file_path, folder_id=None, sha256=None, httponly=False):
        if Path(file_path).suffix.lower() not in ALLOWED_EXTS:
            return f"Skipping '{file_path}' due to disallowed extension."
        
        file_name = Path(file_path).name
        if not folder_id:
            genfolder = await self.create_folder(file_name.rsplit(".", 1)[0])
            if genfolder is None:
                return None
            folder_id = genfolder.get("folderid")
        
        upload_info = await self.__getUploadURL(folder=folder_id, sha256=sha256, httponly=httponly)
        if upload_info is None:
            return None
        
        if self.dluploader.is_cancelled:
            return
        
        self.dluploader.last_uploaded = 0
        try:
            uploaded = await self.dluploader.upload_aiohttp(upload_info["url"], file_path, file_name, {})
            if uploaded:
                folder_contents = await self.list_folder(folder=folder_id)
                if folder_contents is None or 'files' not in folder_contents or not folder_contents['files']:
                    return None
                
                file_id = folder_contents['files'][0]['linkid']
                await self.rename(file_id, file_name)
                return f"https://streamtape.to/v/{file_id}"
        except Exception as e:
            LOGGER.error(f"Failed to upload file '{file_path}': {e}")
        return None

    async def create_folder(self, name, parent=None):
        try:
            exfolders = [folder["name"] for folder in (await self.list_folder(folder=parent) or {"folders": []})["folders"]]
            if name in exfolders:
                i = 1
                while f"{i} {name}" in exfolders:
                    i += 1
                name = f"{i} {name}"

            url = f"{self.base_url}/file/createfolder?login={self.__userLogin}&key={self.__passKey}&name={name}"
            if parent is not None:
                url += f"&pid={parent}"
            async with self.session.get(url) as response:
                response.raise_for_status()
                data = await response.json()
                if data.get("status") == 200:
                    return data.get("result")
        except Exception as e:
            LOGGER.error(f"Failed to create folder '{name}': {e}")
        return None

    async def rename(self, file_id, name):
        url = f"{self.base_url}/file/rename?login={self.__userLogin}&key={self.__passKey}&file={file_id}&name={name}"
        try:
            async with self.session.get(url) as response:
                response.raise_for_status()
                data = await response.json()
                if data.get("status") == 200:
                    return data.get("result")
        except Exception as e:
            LOGGER.error(f"Failed to rename file '{file_id}' to '{name}': {e}")
        return None

    async def list_folder(self, folder=None):
        url = f"{self.base_url}/file/listfolder?login={self.__userLogin}&key={self.__passKey}"
        if folder is not None:
            url += f"&folder={folder}"
        try:
            async with self.session.get(url) as response:
                response.raise_for_status()
                data = await response.json()
                if data.get("status") == 200:
                    return data.get("result")
        except Exception as e:
            LOGGER.error(f"Failed to list folder '{folder}': {e}")
        return None

    async def list_telegraph(self, folder_id, nested=False):
        tg_html = ""
        contents = await self.list_folder(folder_id)
        if contents is None:
            return "Failed to retrieve folder contents."
        
        for fid in contents.get('folders', []):
            tg_html += f"<aside>╾──────────────────────╼</aside><br><aside><b>🗂 {fid['name']}</b></aside><br><aside>╾──────────────────────╼</aside><br>"
            tg_html += await self.list_telegraph(fid['id'], True)
        
        tg_html += "<ol>"
        for finfo in contents.get('files', []):
            tg_html += f"""<li> <code>{finfo['name']}</code><br>🔗 <a href="https://streamtape.to/v/{finfo['linkid']}">StreamTape URL</a><br> </li>"""
        tg_html += "</ol>"
        
        if nested:
            return tg_html
        
        tg_html = f"""<figure><img src='{config_dict["COVER_IMAGE"]}'></figure>""" + tg_html
        try:
            path = (await telegraph.create_page(title=f"StreamTape X", content=tg_html))["path"]
            return f"https://te.legra.ph/{path}"
        except Exception as e:
            LOGGER.error(f"Failed to create Telegraph page: {e}")
        return None

    async def upload_folder(self, folder_path, parent_folder_id=None):
        folder_name = Path(folder_path).name
        genfolder = await self.create_folder(name=folder_name, parent=parent_folder_id)

        if genfolder and (newfid := genfolder.get("folderid")):
            try:
                for entry in await scandir(folder_path):
                    if entry.is_file():
                        await self.upload_file(entry.path, newfid)
                        self.dluploader.total_files += 1
                    elif entry.is_dir():
                        await self.upload_folder(entry.path, newfid)
                        self.dluploader.total_folders += 1
                return await self.list_telegraph(newfid)
            except Exception as e:
                LOGGER.error(f"Failed to upload folder '{folder_path}': {e}")
        return None

    async def upload(self, file_path):
        stlink = None
        if await aiopath.isfile(file_path):
            stlink = await self.upload_file(file_path)
        elif await aiopath.isdir(file_path):
            stlink = await self.upload_folder(file_path)
        if stlink:
            return stlink
        if self.dluploader.is_cancelled:
            return
        raise Exception("Failed to upload file/folder to StreamTape API. Retry or try after some time.")
    
    async def close(self):
        await self.session.close()  # Ensure the session is closed when done
