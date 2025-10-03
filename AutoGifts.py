__version__ = (1, 0, 0)

# meta developer: @your_username
# description: Автоматически меняет NFT подарок в статусе

import asyncio
import logging
from datetime import datetime
from .. import loader, utils
from telethon.tl.functions.account import UpdateEmojiStatusRequest
from telethon.tl.functions.payments import GetSavedStarGiftsRequest
from telethon.tl.types import EmojiStatus, SavedStarGift, StarGiftUnique

logger = logging.getLogger(__name__)

@loader.tds
class AutoGifts(loader.Module):
    """Автоматически меняет NFT подарок в статусе"""
    
    strings = {
        "name": "AutoGifts",
        "started": "✅ Автоматическая смена NFT подарков запущена\n⏰ Интервал: {} секунд\n🎁 Найдено NFT: {}",
        "stopped": "✅ Автоматическая смена NFT подарков остановлена",
        "already_running": "❌ Смена NFT подарков уже запущена",
        "already_stopped": "❌ Смена NFT подарков уже остановлена",
        "no_premium": "❌ Требуется Telegram Premium для использования NFT подарков",
        "no_nft_gifts": "❌ В вашей коллекции нет NFT подарков",
        "loading": "💫 Ищу NFT подарки в вашей коллекции...",
    }
    
    strings_ru = {
        "started": "✅ Автоматическая смена NFT подарков запущена\n⏰ Интервал: {} секунд\n🎁 Найдено NFT: {}",
        "stopped": "✅ Автоматическая смена NFT подарков остановлена", 
        "already_running": "❌ Смена NFT подарков уже запущена",
        "already_stopped": "❌ Смена NFT подарков уже остановлена",
        "no_premium": "❌ Требуется Telegram Premium для использования NFT подарков",
        "no_nft_gifts": "❌ В вашей коллекции нет NFT подарков",
        "loading": "💫 Ищу NFT подарки в вашей коллекции...",
    }
    
    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "interval_seconds",
                3600,
                "Интервал смены подарков в секундах",
                validator=loader.validators.Integer(minimum=120)
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

    async def _get_saved_star_gifts(self):
        """Получает сохраненные подарки"""
        try:
            result = await self._client(GetSavedStarGiftsRequest(
                peer=self.me,
                offset="",
                limit=100
            ))
            return result
        except Exception as e:
            logger.error(f"Error getting saved gifts: {e}")
            return None

    async def _load_nft_gifts(self):
        """Загружает NFT подарки из коллекции пользователя"""
        try:
            result = await self._get_saved_star_gifts()
            if not result or not hasattr(result, 'gifts'):
                return []

            nft_gifts = []
            for gift in result.gifts:
                # Ищем только уникальные подарки (NFT)
                if (isinstance(gift, SavedStarGift) and 
                    hasattr(gift, 'gift') and 
                    isinstance(gift.gift, StarGiftUnique)):
                    
                    # Получаем document_id из NFT подарка
                    if hasattr(gift.gift, 'document_id'):
                        gift_title = getattr(gift.gift, 'title', 'NFT подарок')
                        nft_gifts.append({
                            'document_id': gift.gift.document_id,
                            'title': gift_title,
                        })
                        logger.info(f"Found NFT gift: {gift_title} (ID: {gift.gift.document_id})")

            return nft_gifts

        except Exception as e:
            logger.error(f"Error loading NFT gifts: {e}")
            return []

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
            else:
                logger.error(f"Failed to set gift: {nft_gift['title']}")
                # Пропускаем проблемный подарок
                self.current_index = (self.current_index + 1) % len(self.nft_gifts)
                return
            
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
        
        # Загружаем список NFT подарков
        await utils.answer(message, self.strings("loading"))
        self.nft_gifts = await self._load_nft_gifts()
        
        if not self.nft_gifts:
            await utils.answer(message, self.strings("no_nft_gifts"))
            return
        
        self.is_running = True
        self.current_index = 0
        self.task = asyncio.create_task(self._gift_loop())
        self._save_gifts()
        
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
        en_doc="Reload NFT gifts list",
        ru_doc="Перезагрузить список NFT подарков"
    )
    async def agreload(self, message):
        """Перезагрузить список NFT подарков"""
        await utils.answer(message, self.strings("loading"))
        self.nft_gifts = await self._load_nft_gifts()
        
        if not self.nft_gifts:
            await utils.answer(message, self.strings("no_nft_gifts"))
            return
        
        self.current_index = 0
        self._save_gifts()
        await utils.answer(message, f"✅ Найдено {len(self.nft_gifts)} NFT подарков")

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
            await utils.answer(message, self.strings("no_nft_gifts"))
            return
        
        gifts_text = "\n".join([
            f"{i+1}. {nft['title']} (ID: {nft['document_id']})"
            for i, nft in enumerate(self.nft_gifts)
        ])
        
        status = "активен" if self.is_running else "остановлен"
        current_gift = self.nft_gifts[self.current_index]['title'] if self.nft_gifts else "не установлен"
        
        await utils.answer(message, 
            f"🔄 Статус: {status}\n"
            f"📊 Подарков: {len(self.nft_gifts)}\n"
            f"🎁 Текущий: {current_gift}\n"
            f"⏰ Интервал: {self.config['interval_seconds']} сек\n\n"
            f"Список NFT подарков:\n{gifts_text}"
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
