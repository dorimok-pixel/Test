__version__ = (1, 1, 0)

import random
import logging
import asyncio
import time
from collections import defaultdict
from herokutl.types import Message
from .. import loader, utils
from telethon.errors import FloodWaitError
from ..inline.types import InlineCall

logger = logging.getLogger(__name__)

FOUNDATION_LINK = "https://t.me/+ZfmKdDrEMCA1NWEy"

@loader.tds
class Foundation(loader.Module):
    
    strings = {
        "name": "Foundation",
        "sending": "<emoji document_id=6012681561286122335>🤤</emoji> Ищем...",
        "error": "<emoji document_id=6012681561286122335>🤤</emoji> Чот не то, чекай логи",
        "not_joined": "<emoji document_id=6012681561286122335>🤤</emoji> Нужно вступить в канал, внимательно читай при подаче заявки: https://t.me/+ZfmKdDrEMCA1NWEy",
        "no_media": "<emoji document_id=6012681561286122335>🤤</emoji> Не найдено медиа в канале",
        "no_messages": "<emoji document_id=6012681561286122335>🤤</emoji> Не найдено сообщений в канале",
        "no_videos": "<emoji document_id=6012681561286122335>🤤</emoji> Не найдено видео в канале",
        "triggers_config": "⚙️ <b>Настройка триггеров для Foundation</b>\n\nЧат: {} (ID: {})\n\nТекущие триггеры:\n• <code>fond</code>: {}\n• <code>vfond</code>: {}",
        "select_trigger": "Выберите триггер для настройки:",
        "enter_trigger_word": "✍️ Введите слово-триггер (или 'off' для отключения):",
        "trigger_updated": "✅ Триггер обновлен!\n\n<code>{}</code> теперь будет вызывать <code>.{}</code> в чате {}",
        "trigger_disabled": "✅ Триггер отключен для <code>.{}</code> в чате {}",
        "no_triggers": "Триггеры не настроены",
        "spam_protection": "<emoji document_id=6012681561286122335>🤤</emoji> Слишком много запросов, подождите",
    }

    def __init__(self):
        self._media_cache = {}
        self._video_cache = {}
        self._cache_time = {}
        self.entity = None
        self._last_entity_check = 0
        self.entity_check_interval = 300
        self.cache_ttl = 1200
        self._spam_timestamps = defaultdict(list)
        self._spam_lock = defaultdict(asyncio.Lock)
        
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "triggers_enabled",
                True,
                "Enable trigger watcher",
                validator=loader.validators.Boolean()
            )
        )
    
    async def client_ready(self, client, db):
        self.client = client
        self._db = db
        self.triggers = self._db.get(__name__, "triggers", {})
        await self._load_entity()

    async def _load_entity(self):
        current_time = time.time()
        
        if self.entity and current_time - self._last_entity_check < self.entity_check_interval:
            return True
        
        try:
            self.entity = await self.client.get_entity(FOUNDATION_LINK)
            self._last_entity_check = current_time
            return True
        except Exception:
            self.entity = None
            return False

    async def _get_cached_media(self, media_type="any"):
        current_time = time.time()
        cache_key = media_type
        
        if cache_key in self._cache_time and current_time - self._cache_time[cache_key] < self.cache_ttl:
            if cache_key == "any" and cache_key in self._media_cache:
                return self._media_cache[cache_key]
            elif cache_key == "video" and cache_key in self._video_cache:
                return self._video_cache[cache_key]
        
        if not await self._load_entity():
            return None
        
        try:
            messages = await self.client.get_messages(self.entity, limit=1500)
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
            return await self._get_cached_media(media_type)
        except ValueError as e:
            if "Could not find the entity" in str(e):
                return None
            raise e
        
        if not messages:
            return []
        
        if media_type == "any":
            media_messages = [msg for msg in messages if msg.media]
            self._media_cache["any"] = media_messages
        else:
            video_messages = []
            for msg in messages:
                if msg.media and hasattr(msg.media, 'document'):
                    attr = getattr(msg.media.document, 'mime_type', '')
                    if 'video' in attr:
                        video_messages.append(msg)
            self._video_cache["video"] = video_messages
        
        self._cache_time[cache_key] = current_time
        return self._media_cache.get("any") if media_type == "any" else self._video_cache.get("video")

    async def _check_spam(self, user_id, chat_id):
        key = f"{user_id}:{chat_id}"
        now = time.time()
        
        async with self._spam_lock[key]:
            timestamps = self._spam_timestamps[key]
            timestamps = [ts for ts in timestamps if now - ts < 1]
            
            if len(timestamps) >= 3:
                return True
            
            timestamps.append(now)
            self._spam_timestamps[key] = timestamps[-10:]
            return False

    async def _send_media(self, message: Message, media_type: str = "any"):
        try:
            if not await self._load_entity():
                return await utils.answer(message, self.strings["not_joined"])
            
            send = await utils.answer(message, self.strings["sending"])
            
            media_list = await self._get_cached_media(media_type)
            
            if media_list is None:
                await utils.answer(send, self.strings["not_joined"])
                return
            
            if not media_list:
                if media_type == "any":
                    await utils.answer(send, self.strings["no_media"])
                else:
                    await utils.answer(send, self.strings["no_videos"])
                return
            
            random_message = random.choice(media_list)
            
            await self.client.send_message(
                message.peer_id,
                message=random_message,
                reply_to=getattr(message, "reply_to_msg_id", None)
            )
            
            await asyncio.sleep(0.2)
            try:
                await send.delete()
            except Exception:
                pass
            
        except Exception:
            await utils.answer(message, self.strings["error"])

    async def fond(self, message: Message):
        if await self._check_spam(message.sender_id, utils.get_chat_id(message)):
            await utils.answer(message, self.strings["spam_protection"])
            return
        await self._send_media(message, "any")

    async def vfond(self, message: Message):
        if await self._check_spam(message.sender_id, utils.get_chat_id(message)):
            await utils.answer(message, self.strings["spam_protection"])
            return
        await self._send_media(message, "video")

    async def ftriggers(self, message: Message):
        chat_id = utils.get_chat_id(message)
        chat = await message.get_chat()
        chat_title = getattr(chat, "title", "Private Chat")
        
        chat_triggers = self.triggers.get(str(chat_id), {})
        fond_trigger = chat_triggers.get("fond", self.strings["no_triggers"])
        vfond_trigger = chat_triggers.get("vfond", self.strings["no_triggers"])
        
        await self.inline.form(
            message=message,
            text=self.strings["triggers_config"].format(
                chat_title,
                chat_id,
                fond_trigger,
                vfond_trigger
            ),
            reply_markup=[
                [
                    {
                        "text": "⚙️ Configure fond trigger",
                        "callback": self._configure_trigger,
                        "args": (chat_id, "fond")
                    }
                ],
                [
                    {
                        "text": "⚙️ Configure vfond trigger",
                        "callback": self._configure_trigger,
                        "args": (chat_id, "vfond")
                    }
                ],
                [
                    {
                        "text": "❌ Close",
                        "action": "close"
                    }
                ]
            ]
        )

    async def _configure_trigger(self, call: InlineCall, chat_id: int, command: str):
        await call.edit(
            self.strings["select_trigger"],
            reply_markup=[
                [
                    {
                        "text": f"✍️ Set trigger for .{command}",
                        "input": self.strings["enter_trigger_word"],
                        "handler": self._save_trigger,
                        "args": (chat_id, command, call)
                    }
                ],
                [
                    {
                        "text": "🔙 Back",
                        "callback": self._show_main_menu,
                        "args": (call, chat_id)
                    }
                ]
            ]
        )

    async def _save_trigger(self, call: InlineCall, query: str, chat_id: int, command: str, original_call: InlineCall):
        query = query.strip().lower()
        
        if str(chat_id) not in self.triggers:
            self.triggers[str(chat_id)] = {}
        
        if query == "off":
            if command in self.triggers[str(chat_id)]:
                del self.triggers[str(chat_id)][command]
                if not self.triggers[str(chat_id)]:
                    del self.triggers[str(chat_id)]
        else:
            self.triggers[str(chat_id)][command] = query
        
        self._db.set(__name__, "triggers", self.triggers)
        
        try:
            chat = await self.client.get_entity(chat_id)
            chat_title = getattr(chat, "title", "Private Chat")
        except:
            chat_title = f"Chat {chat_id}"
        
        if query == "off":
            await original_call.answer(
                self.strings["trigger_disabled"].format(command, chat_title),
                show_alert=True
            )
        else:
            await original_call.answer(
                self.strings["trigger_updated"].format(query, command, chat_title),
                show_alert=True
            )
        
        await self._show_main_menu(original_call, chat_id)

    async def _show_main_menu(self, call: InlineCall, chat_id: int):
        try:
            chat = await self.client.get_entity(chat_id)
            chat_title = getattr(chat, "title", "Private Chat")
        except:
            chat_title = f"Chat {chat_id}"
        
        chat_triggers = self.triggers.get(str(chat_id), {})
        fond_trigger = chat_triggers.get("fond", self.strings["no_triggers"])
        vfond_trigger = chat_triggers.get("vfond", self.strings["no_triggers"])
        
        await call.edit(
            self.strings["triggers_config"].format(
                chat_title,
                chat_id,
                fond_trigger,
                vfond_trigger
            ),
            reply_markup=[
                [
                    {
                        "text": "⚙️ Configure fond trigger",
                        "callback": self._configure_trigger,
                        "args": (chat_id, "fond")
                    }
                ],
                [
                    {
                        "text": "⚙️ Configure vfond trigger",
                        "callback": self._configure_trigger,
                        "args": (chat_id, "vfond")
                    }
                ],
                [
                    {
                        "text": "❌ Close",
                        "action": "close"
                    }
                ]
            ]
        )

    @loader.watcher(only_incoming=True)
    async def trigger_watcher(self, message: Message):
        if not message.text or message.out or message.sender_id == (await self.client.get_me()).id:
            return
        
        if not self.config["triggers_enabled"]:
            return
        
        chat_id = utils.get_chat_id(message)
        text = message.text.strip().lower()
        
        if await self._check_spam(message.sender_id, chat_id):
            await utils.answer(message, self.strings["spam_protection"])
            return
        
        chat_triggers = self.triggers.get(str(chat_id), {})
        
        if not chat_triggers:
            return
        
        for command, trigger in chat_triggers.items():
            if text == trigger:
                if command == "fond":
                    await self.fond(message)
                elif command == "vfond":
                    await self.vfond(message)
                break 
