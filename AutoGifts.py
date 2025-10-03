__version__ = (7, 0, 0)

# meta developer: @your_username
# description: Автоматически меняет NFT подарок в статусе из коллекции

import asyncio
import logging
import re
from datetime import datetime
from .. import loader, utils
from telethon.tl.functions.account import UpdateEmojiStatusRequest
from telethon.tl.types import EmojiStatus
from telethon.tl.functions.messages import GetStickerSetRequest
from telethon.tl.types import InputStickerSetShortName

logger = logging.getLogger(__name__)

@loader.tds
class AutoGifts(loader.Module):
    """Автоматически меняет NFT подарок в статусе из коллекции"""
    
    strings = {
        "name": "AutoGifts",
        "started": "✅ Автоматическая смена NFT подарков запущена\n⏰ Интервал: {} секунд\n🎁 Подарков в коллекции: {}",
        "stopped": "✅ Автоматическая смена NFT подарков остановлена",
        "already_running": "❌ Смена NFT подарков уже запущена",
        "already_stopped": "❌ Смена NFT подарков уже остановлена",
        "no_premium": "❌ Требуется Telegram Premium для использования NFT подарков",
        "no_collection": "❌ Не указана ссылка на коллекцию\nИспользуй: .agsetcollection t.me/addemoji/CollectionName",
        "loading": "💫 Загружаю коллекцию...",
        "collection_updated": "✅ Коллекция обновлена: {} кастомных эмодзи",
        "error_loading": "❌ Ошибка загрузки коллекции: {}",
        "no_custom_emojis": "❌ В коллекции не найдено кастомных эмодзи",
    }
    
    strings_ru = {
        "started": "✅ Автоматическая смена NFT подарков запущена\n⏰ Интервал: {} секунд\n🎁 Подарков в коллекции: {}",
        "stopped": "✅ Автоматическая смена NFT подарков остановлена", 
        "already_running": "❌ Смена NFT подарков уже запущена",
        "already_stopped": "❌ Смена NFT подарков уже остановлена",
        "no_premium": "❌ Требуется Telegram Premium для использования NFT подарков",
        "no_collection": "❌ Не указана ссылка на коллекцию\nИспользуй: .agsetcollection t.me/addemoji/CollectionName",
        "loading": "💫 Загружаю коллекцию...",
        "collection_updated": "✅ Коллекция обновлена: {} кастомных эмодзи",
        "error_loading": "❌ Ошибка загрузки коллекции: {}",
        "no_custom_emojis": "❌ В коллекции не найдено кастомных эмодзи",
    }
    
    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "interval_seconds",
                3600,
                "Интервал смены подарков в секундах",
                validator=loader.validators.Integer(minimum=120)
            ),
            loader.ConfigValue(
                "collection_name",
                "",
                "Название коллекции кастомных эмодзи",
                validator=loader.validators.String()
            ),
        )
        self.is_running = False
        self.task = None
        self.current_index = 0
        self.custom_emojis = []
        self.me = None

    async def client_ready(self, client, db):
        self._client = client
        self._db = db
        self.me = await self._client.get_me()
        # Загружаем список эмодзи из базы данных
        self.custom_emojis = self._db.get(__name__, "custom_emojis", [])
        
        if not self.me.premium:
            logger.warning("Telegram Premium required for custom emojis")

    def _save_emojis(self):
        """Сохраняет список эмодзи в базу данных"""
        self._db.set(__name__, "custom_emojis", self.custom_emojis)

    async def _load_custom_emojis(self, collection_name: str):
        """Загружает кастомные эмодзи из набора"""
        try:
            # Получаем набор стикеров (кастомных эмодзи)
            sticker_set = await self._client(GetStickerSetRequest(
                stickerset=InputStickerSetShortName(short_name=collection_name),
                hash=0
            ))
            
            custom_emojis = []
            for document in sticker_set.documents:
                if hasattr(document, 'id'):
                    # Получаем текст эмодзи из атрибутов
                    emoji_text = "❓"
                    if hasattr(document, 'attributes'):
                        for attr in document.attributes:
                            if hasattr(attr, 'alt'):
                                emoji_text = attr.alt
                                break
                    
                    custom_emojis.append({
                        'document_id': document.id,
                        'emoji': emoji_text,
                        'title': f"{emoji_text} {collection_name}"
                    })
                    logger.info(f"Found custom emoji: {emoji_text} (ID: {document.id})")

            return custom_emojis, None

        except Exception as e:
            logger.error(f"Error loading custom emojis: {e}")
            return None, str(e)

    async def _set_emoji_status(self, document_id: int):
        """Устанавливает эмодзи статус"""
        try:
            await self._client(UpdateEmojiStatusRequest(
                emoji_status=EmojiStatus(document_id=document_id)
            ))
            return True
        except Exception as e:
            logger.error(f"Error setting emoji status: {e}")
            return False

    async def _change_gift(self):
        """Смена текущего кастомного эмодзи в статусе"""
        try:
            if not self.custom_emojis:
                logger.warning("No custom emojis available")
                return

            # Выбираем следующий эмодзи
            emoji_data = self.custom_emojis[self.current_index]
            
            # Устанавливаем как emoji статус
            success = await self._set_emoji_status(emoji_data['document_id'])
            
            if success:
                logger.info(f"Emoji changed: {emoji_data['emoji']}")
                # Уведомляем в лс о смене эмодзи
                try:
                    status_msg = (
                        f"🎁 **Эмодзи статус изменен**\n\n"
                        f"{emoji_data['emoji']} {emoji_data['title']}\n"
                        f"📊 {self.current_index + 1}/{len(self.custom_emojis)}\n"
                        f"⏰ {datetime.now().strftime('%H:%M:%S')}"
                    )
                    await self._client.send_message(self.me.id, status_msg)
                except Exception as e:
                    logger.error(f"Error sending status message: {e}")
            else:
                logger.error(f"Failed to set emoji: {emoji_data['emoji']}")
            
            # Переходим к следующему эмодзи
            self.current_index = (self.current_index + 1) % len(self.custom_emojis)
            
        except Exception as e:
            logger.error(f"Error changing emoji: {e}")

    async def _gift_loop(self):
        """Основной цикл смены эмодзи"""
        while self.is_running:
            try:
                await self._change_gift()
                await asyncio.sleep(self.config["interval_seconds"])
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in emoji loop: {e}")
                await asyncio.sleep(60)

    @loader.command(
        en_doc="Start automatic emoji changing",
        ru_doc="Запустить автоматическую смену эмодзи"
    )
    async def agstart(self, message):
        """Запустить автоматическую смену эмодзи"""
        if self.is_running:
            await utils.answer(message, self.strings("already_running"))
            return
        
        if not self.me.premium:
            await utils.answer(message, self.strings("no_premium"))
            return
        
        if not self.config["collection_name"]:
            await utils.answer(message, self.strings("no_collection"))
            return
        
        if not self.custom_emojis:
            await utils.answer(message, "❌ Сначала загрузите эмодзи командой .agreload")
            return
        
        self.is_running = True
        self.current_index = 0
        self.task = asyncio.create_task(self._gift_loop())
        
        # Сразу устанавливаем первый эмодзи
        await self._change_gift()
        
        await utils.answer(message, self.strings("started").format(
            self.config["interval_seconds"], 
            len(self.custom_emojis)
        ))

    @loader.command(
        en_doc="Stop automatic emoji changing", 
        ru_doc="Остановить автоматическую смену эмодзи"
    )
    async def agstop(self, message):
        """Остановить автоматическую смену эмодзи"""
        if not self.is_running:
            await utils.answer(message, self.strings("already_stopped"))
            return
            
        self.is_running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        
        await utils.answer(message, self.strings("stopped"))

    @loader.command(
        en_doc="Set collection name",
        ru_doc="Установить название коллекции"
    )
    async def agsetcollection(self, message):
        """Установить название коллекции"""
        args = utils.get_args(message)
        if not args:
            current_name = self.config["collection_name"]
            if current_name:
                await utils.answer(message, f"📚 Текущая коллекция: {current_name}")
            else:
                await utils.answer(message, self.strings("no_collection"))
            return
        
        collection_name = args[0].strip()
        self.config["collection_name"] = collection_name
        await utils.answer(message, f"✅ Коллекция установлена: {collection_name}")

    @loader.command(
        en_doc="Reload custom emojis",
        ru_doc="Перезагрузить кастомные эмодзи"
    )
    async def agreload(self, message):
        """Перезагрузить кастомные эмодзи"""
        if not self.config["collection_name"]:
            await utils.answer(message, self.strings("no_collection"))
            return
        
        await utils.answer(message, self.strings("loading"))
        
        custom_emojis, error = await self._load_custom_emojis(self.config["collection_name"])
        
        if error:
            await utils.answer(message, self.strings("error_loading").format(error))
            return
        
        if not custom_emojis:
            await utils.answer(message, self.strings("no_custom_emojis"))
            return
        
        self.custom_emojis = custom_emojis
        self.current_index = 0
        self._save_emojis()
        
        await utils.answer(message, self.strings("collection_updated").format(len(self.custom_emojis)))

    @loader.command(
        en_doc="Set change interval",
        ru_doc="Установить интервал смены"
    )
    async def aginterval(self, message):
        """Установить интервал смены"""
        args = utils.get_args(message)
        if not args:
            current_interval = self.config["interval_seconds"]
            await utils.answer(message, f"⏰ Текущий интервал: {current_interval} секунд")
            return
        
        try:
            seconds = int(args[0])
            if seconds < 120:
                await utils.answer(message, "❌ Интервал должен быть не менее 120 секунд")
                return
                
            self.config["interval_seconds"] = seconds
            await utils.answer(message, f"✅ Интервал обновлен: {seconds} секунд")
            
        except ValueError:
            await utils.answer(message, "❌ Укажите целое число секунд")

    @loader.command(
        en_doc="Show emojis list",
        ru_doc="Показать список эмодзи"
    )
    async def aglist(self, message):
        """Показать список эмодзи"""
        if not self.custom_emojis:
            await utils.answer(message, "❌ Коллекция не загружена")
            return
        
        emojis_text = "\n".join([
            f"{i+1}. {emoji['emoji']} - {emoji['title']}"
            for i, emoji in enumerate(self.custom_emojis)
        ])
        
        await utils.answer(message, 
            f"🎁 Коллекция: {self.config['collection_name']}\n"
            f"🔄 Статус: {'активен' if self.is_running else 'остановлен'}\n"
            f"📊 Эмодзи: {len(self.custom_emojis)}\n"
            f"⏰ Интервал: {self.config['interval_seconds']} сек\n\n"
            f"Список эмодзи:\n{emojis_text}"
        )

    async def on_unload(self):
        """Остановка при выгрузке модуля"""
        if self.is_running and self.task:
            self.is_running = False
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        self._save_emojis() 
