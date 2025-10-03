__version__ = (1, 0, 1)

# meta developer: @your_username
# description: Автоматически меняет NFT подарок в статусе из коллекции

import asyncio
import logging
import re
from datetime import datetime
from .. import loader, utils
from telethon.tl.functions.account import UpdateEmojiStatusRequest
from telethon.tl.types import EmojiStatus

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
        "no_collection": "❌ Не указана ссылка на коллекцию\nИспользуй: .agsetcollection t.me/username/c/1",
        "loading": "💫 Загружаю коллекцию...",
        "collection_updated": "✅ Коллекция обновлена: {} подарков",
        "error_loading": "❌ Ошибка загрузки коллекции: {}",
    }
    
    strings_ru = {
        "started": "✅ Автоматическая смена NFT подарков запущена\n⏰ Интервал: {} секунд\n🎁 Подарков в коллекции: {}",
        "stopped": "✅ Автоматическая смена NFT подарков остановлена", 
        "already_running": "❌ Смена NFT подарков уже запущена",
        "already_stopped": "❌ Смена NFT подарков уже остановлена",
        "no_premium": "❌ Требуется Telegram Premium для использования NFT подарков",
        "no_collection": "❌ Не указана ссылка на коллекцию\nИспользуй: .agsetcollection t.me/username/c/1",
        "loading": "💫 Загружаю коллекцию...",
        "collection_updated": "✅ Коллекция обновлена: {} подарков",
        "error_loading": "❌ Ошибка загрузки коллекции: {}",
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
                "collection_link",
                "",
                "Ссылка на коллекцию подарков",
                validator=loader.validators.String()
            ),
        )
        self.is_running = False
        self.task = None
        self.current_index = 0
        self.nft_gifts = []
        self.me = None

    async def client_ready(self, client, db):
        self._client = client
        self._db = db
        self.me = await self._client.get_me()
        # Загружаем список подарков из базы данных
        self.nft_gifts = self._db.get(__name__, "nft_gifts", [])
        
        if not self.me.premium:
            logger.warning("Telegram Premium required for NFT gifts")

    def _save_gifts(self):
        """Сохраняет список подарков в базу данных"""
        self._db.set(__name__, "nft_gifts", self.nft_gifts)

    async def _parse_collection_link(self, link: str):
        """Парсит ссылку на коллекцию и извлекает username и ID канала"""
        try:
            # Форматы ссылок: t.me/username/c/1 или t.me/pupozermofko/c/2
            pattern = r"t\.me/([^/]+)/c/(\d+)"
            match = re.match(pattern, link)
            if match:
                username = match.group(1)
                channel_id = int(match.group(2))
                return username, channel_id
            return None, None
        except Exception as e:
            logger.error(f"Error parsing collection link: {e}")
            return None, None

    async def _load_collection_gifts(self, link: str):
        """Загружает подарки из коллекции по ссылке"""
        try:
            username, channel_id = await self._parse_collection_link(link)
            if not username or not channel_id:
                return None, "Неверный формат ссылки"

            # Получаем entity канала
            entity = await self._client.get_entity(f"t.me/{username}")
            
            # Получаем сообщения из канала (коллекции)
            nft_gifts = []
            async for message in self._client.iter_messages(entity, limit=100):
                if message.media:
                    # Ищем document_id в медиа
                    if hasattr(message.media, 'document'):
                        doc_id = message.media.document.id
                        gift_title = message.text or f"NFT #{doc_id}"
                        
                        nft_gifts.append({
                            'document_id': doc_id,
                            'title': gift_title,
                            'message_id': message.id
                        })
                        logger.info(f"Found NFT in collection: {gift_title} (ID: {doc_id})")

            return nft_gifts, None

        except Exception as e:
            logger.error(f"Error loading collection: {e}")
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
        """Смена текущего NFT подарка в статусе"""
        try:
            if not self.nft_gifts:
                logger.warning("No NFT gifts available")
                return

            # Выбираем следующий подарок
            nft_gift = self.nft_gifts[self.current_index]
            
            # Устанавливаем как emoji статус
            success = await self._set_emoji_status(nft_gift['document_id'])
            
            if success:
                logger.info(f"Gift changed: {nft_gift['title']}")
                # Уведомляем в лс о смене подарка
                try:
                    status_msg = (
                        f"🎁 **NFT подарок изменен**\n\n"
                        f"💎 {nft_gift['title']}\n"
                        f"🆔 ID: {nft_gift['document_id']}\n"
                        f"📊 {self.current_index + 1}/{len(self.nft_gifts)}\n"
                        f"⏰ {datetime.now().strftime('%H:%M:%S')}"
                    )
                    await self._client.send_message(self.me.id, status_msg)
                except Exception as e:
                    logger.error(f"Error sending status message: {e}")
            else:
                logger.error(f"Failed to set gift: {nft_gift['title']}")
            
            # Переходим к следующему подарку
            self.current_index = (self.current_index + 1) % len(self.nft_gifts)
            
        except Exception as e:
            logger.error(f"Error changing gift: {e}")

    async def _gift_loop(self):
        """Основной цикл смены подарков"""
        while self.is_running:
            try:
                await self._change_gift()
                await asyncio.sleep(self.config["interval_seconds"])
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in gift loop: {e}")
                await asyncio.sleep(60)

    @loader.command(
        en_doc="Start automatic NFT gift changing",
        ru_doc="Запустить автоматическую смену NFT подарков"
    )
    async def agstart(self, message):
        """Запустить автоматическую смену NFT подарков"""
        if self.is_running:
            await utils.answer(message, self.strings("already_running"))
            return
        
        if not self.me.premium:
            await utils.answer(message, self.strings("no_premium"))
            return
        
        if not self.config["collection_link"]:
            await utils.answer(message, self.strings("no_collection"))
            return
        
        if not self.nft_gifts:
            await utils.answer(message, "❌ Сначала загрузите коллекцию командой .agreload")
            return
        
        self.is_running = True
        self.current_index = 0
        self.task = asyncio.create_task(self._gift_loop())
        
        # Сразу устанавливаем первый подарок
        await self._change_gift()
        
        await utils.answer(message, self.strings("started").format(
            self.config["interval_seconds"], 
            len(self.nft_gifts)
        ))

    @loader.command(
        en_doc="Stop automatic NFT gift changing", 
        ru_doc="Остановить автоматическую смену NFT подарков"
    )
    async def agstop(self, message):
        """Остановить автоматическую смену NFT подарков"""
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
        en_doc="Set collection link",
        ru_doc="Установить ссылку на коллекцию"
    )
    async def agsetcollection(self, message):
        """Установить ссылку на коллекцию"""
        args = utils.get_args(message)
        if not args:
            current_link = self.config["collection_link"]
            if current_link:
                await utils.answer(message, f"📚 Текущая коллекция: {current_link}")
            else:
                await utils.answer(message, self.strings("no_collection"))
            return
        
        link = args[0].strip()
        if not link.startswith("t.me/"):
            await utils.answer(message, "❌ Неверный формат ссылки. Пример: t.me/username/c/1")
            return
        
        self.config["collection_link"] = link
        await utils.answer(message, f"✅ Коллекция установлена: {link}")

    @loader.command(
        en_doc="Reload collection gifts",
        ru_doc="Перезагрузить подарки из коллекции"
    )
    async def agreload(self, message):
        """Перезагрузить подарки из коллекции"""
        if not self.config["collection_link"]:
            await utils.answer(message, self.strings("no_collection"))
            return
        
        await utils.answer(message, self.strings("loading"))
        
        nft_gifts, error = await self._load_collection_gifts(self.config["collection_link"])
        
        if error:
            await utils.answer(message, self.strings("error_loading").format(error))
            return
        
        if not nft_gifts:
            await utils.answer(message, "❌ В коллекции не найдено NFT подарков")
            return
        
        self.nft_gifts = nft_gifts
        self.current_index = 0
        self._save_gifts()
        
        await utils.answer(message, self.strings("collection_updated").format(len(self.nft_gifts)))

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
        en_doc="Show NFT gifts list",
        ru_doc="Показать список NFT подарков"
    )
    async def aglist(self, message):
        """Показать список NFT подарков"""
        if not self.nft_gifts:
            await utils.answer(message, "❌ Коллекция не загружена")
            return
        
        gifts_text = "\n".join([
            f"{i+1}. {nft['title']} (ID: {nft['document_id']})"
            for i, nft in enumerate(self.nft_gifts)
        ])
        
        status = "активен" if self.is_running else "остановлен"
        await utils.answer(message, 
            f"🎁 Коллекция: {self.config['collection_link']}\n"
            f"🔄 Статус: {status}\n"
            f"📊 Подарков: {len(self.nft_gifts)}\n"
            f"⏰ Интервал: {self.config['interval_seconds']} сек\n\n"
            f"Список подарков:\n{gifts_text}"
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
        self._save_gifts() 
