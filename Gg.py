__version__ = (1, 3, 0)
# meta developer: @mofkomodules 
# name: MindfulEdit

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
class MindfulEdit(loader.Module):
    strings = {
        "name": "MindfulEdit",
        "sending": "<emoji document_id=5210956306952758910>👀</emoji> Looking for edit",
        "error": "<emoji document_id=5420323339723881652>⚠️</emoji> An error occurred, check logs",
        "no_videos": "<emoji document_id=5400086192559503700>😳</emoji> No videos found in channel",
        "invalid_channel": "<emoji document_id=5420323339723881652>⚠️</emoji> Invalid channel link",
        "channel_added": "<emoji document_id=5206607081334906820>✔️</emoji> Channel added successfully",
        "channel_removed": "<emoji document_id=5206607081334906820>✔️</emoji> Channel removed successfully",
        "max_channels": "<emoji document_id=5420323339723881652>⚠️</emoji> Maximum 19 additional channels allowed",
        "channel_not_found": "<emoji document_id=5420323339723881652>⚠️</emoji> Channel not found in list",
    }
    
    strings_ru = {
        "sending": "<emoji document_id=5210956306952758910>👀</emoji> Ищу эдит",
        "error": "<emoji document_id=5420323339723881652>⚠️</emoji> Ошибка, проверьте логи",
        "no_videos": "<emoji document_id=5400086192559503700>😳</emoji> В канале не найдено видео",
        "invalid_channel": "<emoji document_id=5420323339723881652>⚠️</emoji> Неверная ссылка на канал",
        "channel_added": "<emoji document_id=5206607081334906820>✔️</emoji> Канал успешно добавлен",
        "channel_removed": "<emoji document_id=5206607081334906820>✔️</emoji> Канал успешно удален",
        "max_channels": "<emoji document_id=5420323339723881652>⚠️</emoji> Максимум 19 дополнительных каналов",
        "channel_not_found": "<emoji document_id=5420323339723881652>⚠️</emoji> Канал не найден в списке",
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "additional_channels",
                [],
                lambda: "Additional channels for edits (up to 19)",
                validator=loader.validators.Series(
                    validator=loader.validators.Link()
                )
            )
        )
        self._videos_cache: dict = {}
        self._cache_time: dict = {}
        self.main_channel = "https://t.me/MindfulEdit"
        self.cache_ttl = 3600
        self.messages_limit = 1000

    async def client_ready(self, client, db):
        self.client = client
        self._db = db

    def _get_all_channels(self) -> List[str]:
        """Get all channels including main and additional ones"""
        channels = [self.main_channel]
        if self.config["additional_channels"]:
            channels.extend(self.config["additional_channels"])
        return channels

    async def _get_videos(self, channel: str) -> List[Message]:
        current_time = time.time()
        
        if (channel in self._videos_cache and 
            channel in self._cache_time and
            current_time - self._cache_time[channel] < self.cache_ttl):
            return self._videos_cache[channel]
        
        try:
            videos = await self.client.get_messages(
                channel,
                limit=self.messages_limit
            )
            
            videos_with_media = [msg for msg in videos if msg.media]
            
            if not videos_with_media:
                logger.warning(f"No media found in channel {channel}")
                return []
            
            self._videos_cache[channel] = videos_with_media
            self._cache_time[channel] = current_time
            logger.info(f"Cache updated for {channel} with {len(videos_with_media)} videos")
            
            return videos_with_media
            
        except Exception as e:
            logger.error(f"Error loading videos from {channel}: {e}")
            return self._videos_cache.get(channel, [])

    async def _send_random_edit(self, message: Message) -> None:
        try:
            status_msg = await utils.answer(message, self.strings["sending"])

            channels = self._get_all_channels()
            
            random.shuffle(channels)
            selected_video = None
            source_channel = None
            
            for channel in channels:
                videos = await self._get_videos(channel)
                if videos:
                    selected_video = random.choice(videos)
                    source_channel = channel
                    break
            
            if not selected_video:
                await utils.answer(status_msg, self.strings["no_videos"])
                return

            await self.client.delete_messages(message.chat_id, [status_msg])
            
            await self.client.send_message(
                message.peer_id,
                message=selected_video,
                reply_to=getattr(message, "reply_to_msg_id", None)
            )
            
            await asyncio.sleep(2)
            
            await self.inline.form(
                text="🔄 Отправить другой эдит?",
                message=message,
                reply_markup=[
                    [
                        {"text": "🔄 Другой эдит", "callback": self._retry_callback}
                    ]
                ]
            )
                
        except Exception as e:
            logger.error(f"Error sending edit: {e}")
            await utils.answer(message, self.strings["error"])

    async def _retry_callback(self, call: InlineCall):
        await call.delete()
        prefix = self.get_prefix()
        await self.client.send_message(call.form["chat"], f"{prefix}redit")

    @loader.command(
        en_doc="Send random edit",
        ru_doc="Отправить рандомный эдит",
        alias="эдит"
    ) 
    async def redit(self, message: Message):
        await self._send_random_edit(message)

    @loader.command(
        en_doc="Add channel to sources",
        ru_doc="Добавить канал в источники",
        alias="эдитканал"
    )
    async def reditchannel(self, message: Message):
        args = utils.get_args_raw(message)
        
        if not args:
            channels = self._get_all_channels()
            text = "📺 <b>Current edit sources:</b>\n\n"
            for i, channel in enumerate(channels, 1):
                text += f"{i}. {channel}\n"
            
            text += f"\n<b>Total:</b> {len(channels)} channels"
            await utils.answer(message, text)
            return
        
        if len(self.config["additional_channels"]) >= 19:
            await utils.answer(message, self.strings["max_channels"])
            return
        
        try:
            await self.client.get_entity(args)
            
            if args in self._get_all_channels():
                await utils.answer(message, "⚠️ Channel already in list")
                return
                
            new_channels = self.config["additional_channels"] + [args]
            self.config["additional_channels"] = new_channels
            
            if args in self._videos_cache:
                del self._videos_cache[args]
            if args in self._cache_time:
                del self._cache_time[args]
                
            await utils.answer(message, self.strings["channel_added"])
            
        except Exception:
            await utils.answer(message, self.strings["invalid_channel"])

    @loader.command(
        en_doc="Remove channel from sources",
        ru_doc="Удалить канал из источников", 
        alias="эдитудалить"
    )
    async def reditremove(self, message: Message):
        args = utils.get_args_raw(message)
        
        if not args:
            await utils.answer(message, "⚠️ Specify channel to remove")
            return
        
        if args == self.main_channel:
            await utils.answer(message, "⚠️ Cannot remove main channel")
            return
        
        if args not in self.config["additional_channels"]:
            await utils.answer(message, self.strings["channel_not_found"])
            return
        
        new_channels = [ch for ch in self.config["additional_channels"] if ch != args]
        self.config["additional_channels"] = new_channels
        
        if args in self._videos_cache:
            del self._videos_cache[args]
        if args in self._cache_time:
            del self._cache_time[args]
            
        await utils.answer(message, self.strings["channel_removed"])
