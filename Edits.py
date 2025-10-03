__version__ = (1, 2, 0)
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
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "source_channel",
                "https://t.me/MindfulEdit",
                lambda: "Source channel for edits",
                validator=loader.validators.Link()
            ),
            loader.ConfigValue(
                "cache_ttl",
                3600,
                lambda: "Cache time-to-live in seconds",
                validator=loader.validators.Integer(minimum=300)
            ),
            loader.ConfigValue(
                "messages_limit",
                1000,
                lambda: "Maximum messages to load from channel",
                validator=loader.validators.Integer(minimum=100, maximum=5000)
            )
        )
        self._videos_cache: Optional[List[Message]] = None
        self._cache_time: float = 0

    async def client_ready(self, client, db):
        self.client = client
        self._db = db

    async def _get_videos(self) -> List[Message]:
        current_time = time.time()
        
        if (self._videos_cache and 
            current_time - self._cache_time < self.config["cache_ttl"]):
            return self._videos_cache
        
        try:
            videos = await self.client.get_messages(
                self.config["source_channel"],
                limit=self.config["messages_limit"]
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

    async def _send_random_edit(self, message: Message, retry: bool = False) -> None:
        try:
            if not retry:
                status_msg = await utils.answer(message, self.strings["sending"])
            else:
                status_msg = message

            videos = await self._get_videos()
            
            if not videos:
                if retry:
                    await utils.answer(message, self.strings["no_videos"])
                else:
                    await utils.answer(status_msg, self.strings["no_videos"])
                return

            selected_video = random.choice(videos)
            
            await self.client.send_message(
                message.peer_id,
                message=selected_video,
                reply_to=getattr(message, "reply_to_msg_id", None)
            )
            
            if retry:
                await self._show_success_with_retry(message)
            else:
                await self.client.delete_messages(message.chat_id, [status_msg])
                
        except Exception as e:
            logger.error(f"Error sending edit: {e}")
            error_msg = await utils.answer(
                message if retry else status_msg, 
                self.strings["error"]
            )
            await asyncio.sleep(3)
            await self.client.delete_messages(message.chat_id, [error_msg])

    async def _show_success_with_retry(self, message: Message):
        await self.inline.form(
            text=self.strings["sent_success"],
            message=message,
            reply_markup=[
                [{
                    "text": "🔄 Try Another", 
                    "callback": self._retry_callback,
                    "args": (message,)
                }],
                [{
                    "text": "❌ Close", 
                    "action": "close"
                }]
            ],
            ttl=30
        )

    async def _retry_callback(self, call: InlineCall, original_message: Message):
        await call.edit(self.strings["sending"])
        await self._send_random_edit(call, retry=True)

    @loader.command(
        en_doc="Send random edit",
        ru_doc="Отправить рандомный эдит",
        alias="эдит"
    ) 
    async def redit(self, message: Message):
        await self._send_random_edit(message)
