__version__ = (1, 3, 0)
# meta developer: @mofkomodules 
# name: MindfuleEdits

from herokutl.types import Message
from .. import loader, utils
from ..inline.types import InlineCall
import random
import asyncio
import logging
import time
from typing import List, Optional

logger = logging.getLogger(__name__)

@loader.tds
class MindfuleEdits(loader.Module):
    strings = {
        "name": "MindfuleEdits",
        "sending": "<emoji document_id=5210956306952758910>👀</emoji> Looking for edit",
        "error": "<emoji document_id=5420323339723881652>⚠️</emoji> An error occurred, check logs",
        "no_videos": "<emoji document_id=5400086192559503700>😳</emoji> No videos found in channel",
        "sent_success": "<emoji document_id=5206607081334906820>✔️</emoji> Edit sent",
    }
    
    strings_ru = {
        "sending": "<emoji document_id=5210956306952758910>👀</emoji> Ищу эдит",
        "error": "<emoji document_id=5420323339723881652>⚠️</emoji> Ошибка, проверьте логи",
        "no_videos": "<emoji document_id=5400086192559503700>😳</emoji> В канале не найдено видео",
        "sent_success": "<emoji document_id=5206607081334906820>✔️</emoji> Эдит отправлен",
    }

    def __init__(self):
        self._videos_cache: Optional[List[Message]] = None
        self._cache_time: float = 0
        self.source_channel = "https://t.me/MindfulEdit"
        self.cache_ttl = 3600
        self.messages_limit = 1000

    async def client_ready(self, client, db):
        self.client = client
        self._db = db

    async def _get_videos(self) -> List[Message]:
        current_time = time.time()
        
        if (self._videos_cache and 
            current_time - self._cache_time < self.cache_ttl):
            return self._videos_cache
        
        try:
            videos = await self.client.get_messages(
                self.source_channel,
                limit=self.messages_limit
            )
            
            videos_with_media = [msg for msg in videos if msg.media]
            
            if not videos_with_media:
                logger.warning("No media found in channel messages")
                return []
            
            self._videos_cache = videos_with_media
            self._cache_time = current_time
            logger.info(f"Cache updated with {len(videos_with_media)} videos")
            
            return videos_with_media
            
        except Exception as e:
            logger.error(f"Error loading videos: {e}")
            return self._videos_cache or []

    async def _send_random_edit(self, call: InlineCall, retry: bool = False) -> None:
        try:
            await call.edit(self.strings["sending"])

            videos = await self._get_videos()
            
            if not videos:
                await call.edit(self.strings["no_videos"])
                return

            selected_video = random.choice(videos)
            
            await self.client.send_message(
                call.form["chat"],
                message=selected_video,
                reply_to=call.form["reply_to_msg_id"]
            )
            
            await call.edit(
                self.strings["sent_success"],
                reply_markup=[
                    [{
                        "text": "🔄 Try Another", 
                        "callback": self._retry_callback
                    }],
                    [{
                        "text": "❌ Close", 
                        "action": "close"
                    }]
                ]
            )
                
        except Exception as e:
            logger.error(f"Error sending edit: {e}")
            await call.edit(self.strings["error"])

    async def _retry_callback(self, call: InlineCall):
        await self._send_random_edit(call, retry=True)

    @loader.command(
        en_doc="Send random edit",
        ru_doc="Отправить рандомный эдит",
        alias="эдит"
    ) 
    async def redit(self, message: Message):
        await self.inline.form(
            self.strings["sending"],
            message=message,
            reply_markup=[[{
                "text": "🔄 Search",
                "callback": self._send_random_edit
            }]]
        )
