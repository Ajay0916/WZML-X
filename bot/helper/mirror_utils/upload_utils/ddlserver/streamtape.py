import asyncio
import time
from aiohttp import ClientSession
from pathlib import Path
from bot import config_dict, LOGGER
from bot.helper.ext_utils.telegraph_helper import telegraph

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
        self.session = None

    async def __initialize_session(self):
        if not self.session:
            self.session = ClientSession()

    async def __api_request(self, url, method='GET', retries=3, backoff_factor=1):
        await self.__initialize_session()
        for attempt in range(retries):
            async with self.session.request(method, url) as response:
                content = await response.text()
                LOGGER.info(f"API Request: {method} {url}")
                LOGGER.info(f"Response Status: {response.status}")
                LOGGER.info(f"Response Headers: {response.headers}")
                LOGGER.info(f"Response Content: {content}")

                if response.status == 200:
                    try:
                        data = await response.json()
                        LOGGER.info(f"Parsed Data: {data}")
                        if data.get("status") == 200:
                            return data.get("result")
                        elif data.get("status") == 429:  # Rate limit exceeded
                            LOGGER.error("Rate limit exceeded. Retrying...")
                            await asyncio.sleep(backoff_factor * (2 ** attempt))
                        else:
                            LOGGER.error(f"API Response Error: {data.get('msg')}")
                            return None
                    except Exception as parse_exception:
                        LOGGER.error(f"Error parsing JSON response: {parse_exception}")
                        return None
                else:
                    LOGGER.error(f"Failed API request. Status: {response.status}")
                    return None
        LOGGER.error("Max retries exceeded.")
        return None

    async def __getAccInfo(self):
        url = f"{self.base_url}/account/info?login={self.__userLogin}&key={self.__passKey}"
        return await self.__api_request(url)

    async def __getUploadURL(self, folder=None, sha256=None, httponly=False):
        url = f"{self.base_url}/file/ul?login={self.__userLogin}&key={self.__passKey}"
        if folder is not None:
            url += f"&folder={folder}"
        if sha256 is not None:
            url += f"&sha256={sha256}"
        if httponly:
            url += "&httponly=true"
        return await self.__api_request(url)

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
        uploaded = await self.dluploader.upload_aiohttp(upload_info["url"], file_path, file_name, {})
        
        if uploaded:
            folder_contents = await self.list_folder(folder=folder_id)
            if folder_contents is None or 'files' not in folder_contents or not folder_contents['files']:
                return None
            
            file_id = folder_contents['files'][0]['linkid']
            await self.rename(file_id, file_name)
            return f"https://streamtape.to/v/{file_id}"
        
        return None

    async def create_folder(self, name, parent=None):
        exfolders = [folder["name"] for folder in (await self.list_folder(folder=parent) or {"folders": []})["folders"]]
        if name in exfolders:
            i = 1
            while f"{i} {name}" in exfolders:
                i += 1
            name = f"{i} {name}"
        
        url = f"{self.base_url}/file/createfolder?login={self.__userLogin}&key={self.__passKey}&name={name}"
        if parent is not None:
            url += f"&pid={parent}"
        
        return await self.__api_request(url)

    async def rename(self, file_id, name):
        url = f"{self.base_url}/file/rename?login={self.__userLogin}&key={self.__passKey}&file={file_id}&name={name}"
        return await self.__api_request(url)

    async def list_telegraph(self, folder_id, nested=False):
        tg_html = ""
        contents = await self.list_folder(folder_id)
        if contents is None:
            return "Failed to retrieve folder contents."
        for fid in contents['folders']:
            tg_html += f"<aside>╾──────────────────────╼</aside><br><aside><b>🗂 {fid['name']}</b></aside><br><aside>╾──────────────────────╼</aside><br>"
            tg_html += await self.list_telegraph(fid['id'], True)
        tg_html += "<ol>"
        for finfo in contents['files']:
            tg_html += f"""<li> <code>{finfo['name']}</code><br>🔗 <a href="https://streamtape.to/v/{finfo['linkid']}">StreamTape URL</a><br> </li>"""
        tg_html += "</ol>"
        if nested:
            return tg_html
        tg_html = f"""<figure><img src='{config_dict["COVER_IMAGE"]}'></figure>""" + tg_html
        path = (await telegraph.create_page(title=f"StreamTape X", content=tg_html))["path"]
        return f"https://te.legra.ph/{path}"

    async def list_folder(self, folder=None):
        url = f"{self.base_url}/file/listfolder?login={self.__userLogin}&key={self.__passKey}"
        if folder is not None:
            url += f"&folder={folder}"
        
        return await self.__api_request(url)

    async def __aenter__(self):
        await self.__initialize_session()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        if self.session:
            await self.session.close()
