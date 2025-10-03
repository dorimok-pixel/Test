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
        "gift_changed": "🎁 NFT подарок изменен: {}",
        "error_changing": "❌ Ошибка при смене подарка: {}",
    }
    
    strings_ru = {
        "started": "✅ Автоматическая смена NFT подарков запущена\n⏰ Интервал: {} секунд\n🎁 Найдено NFT: {}",
        "stopped": "✅ Автоматическая смена NFT подарков остановлена", 
        "already_running": "❌ Смена NFT подарков уже запущена",
        "already_stopped": "❌ Смена NFT подарков уже остановлена",
        "no_premium": "❌ Требуется Telegram Premium для использования NFT подарков",
        "no_nft_gifts": "❌ В вашей коллекции нет NFT подарков",
        "loading": "💫 Ищу NFT подарки в вашей коллекции...",
        "gift_changed": "🎁 NFT подарок изменен: {}",
        "error_changing": "❌ Ошибка при смене подарка: {}",
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
        """Получает сохраненные подарки с правильными параметрами"""
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
        """Загружает NFT подарки из коллекции"""
        try:
            result = await self._get_saved_star_gifts()
            if not result or not hasattr(result, 'gifts'):
                return []

            nft_gifts = []
            for gift in result.gifts:
                if (isinstance(gift, SavedStarGift) and 
                    hasattr(gift, 'gift') and 
                    isinstance(gift.gift, StarGiftUnique) and
                    hasattr(gift.gift, 'document_id')):
                    
                    gift_title = getattr(gift.gift, 'title', f'NFT #{gift.gift.document_id}')
                    nft_gifts.append({
                        'document_id': gift.gift.document_id,
                        'title': gift_title,
                        'gift': gift
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
        en_doc="Show current status",
        ru_doc="Показать текущий статус"
    )
    async def agstatus(self, message):
        """Показать текущий статус"""
        status_text = (
            f"🔄 Статус: {'активен' if self.is_running else 'остановлен'}\n"
            f"⏰ Интервал: {self.config['interval_seconds']} сек\n"
            f"🎁 Всего NFT подарков: {len(self.nft_gifts)}\n"
        )
        
        if self.nft_gifts:
            if self.current_index < len(self.nft_gifts):
                current_gift = self.nft_gifts[self.current_index]
                status_text += f"📊 Текущий: {current_gift['title']} ({self.current_index + 1}/{len(self.nft_gifts)})"
            else:
                status_text += "📊 Текущий: не установлен"
        
        await utils.answer(message, status_text)

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
            f"{i+1}. {nft['title']} (ID: {nft['document_id']}){' ← ТЕКУЩИЙ' if i == self.current_index else ''}"
            for i, nft in enumerate(self.nft_gifts)
        ])
        await utils.answer(message, f"🎁 Список NFT подарков ({len(self.nft_gifts)}):\n\n{gifts_text}")

    @loader.command(
        en_doc="Test current NFT gift",
        ru_doc="Протестировать текущий NFT подарок"
    )
    async def agtest(self, message):
        """Протестировать текущий NFT подарок"""
        if not self.nft_gifts:
            await utils.answer(message, self.strings("no_nft_gifts"))
            return
        
        current_gift = self.nft_gifts[self.current_index]
        success = await self._set_emoji_status(current_gift['document_id'])
        
        if success:
            await utils.answer(message, f"✅ NFT подарок установлен: {current_gift['title']}")
        else:
            await utils.answer(message, f"❌ Ошибка при установке: {current_gift['title']}")

    @loader.command(
        en_doc="Force change to next NFT gift",
        ru_doc="Принудительно сменить на следующий NFT подарок"
    )
    async def agnext(self, message):
        """Принудительно сменить на следующий NFT подарок"""
        if not self.nft_gifts:
            await utils.answer(message, self.strings("no_nft_gifts"))
            return
        
        await self._change_gift()
        await utils.answer(message, "✅ Подарок принудительно изменен")

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
