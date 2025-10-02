__version__ = (3, 0, 0)

# meta developer: @your_username
# description: Автоматически меняет NFT подарок в статусе

import asyncio
import logging
from .. import loader, utils
from telethon.tl.functions.account import UpdateEmojiStatusRequest
from telethon.tl.functions.payments import GetSavedStarGiftsRequest
from telethon.tl.types import EmojiStatus, SavedStarGift, StarGiftUnique

logger = logging.getLogger(__name__)

@loader.tds
class GiftChangerMod(loader.Module):
    """Автоматически меняет NFT подарок в статусе"""
    
    strings = {
        "name": "GiftChanger",
        "started": "✅ Автоматическая смена NFT подарков запущена\n⏰ Интервал: {} секунд",
        "stopped": "✅ Автоматическая смена NFT подарков остановлена",
        "already_running": "❌ Смена NFT подарков уже запущена",
        "already_stopped": "❌ Смена NFT подарков уже остановлена",
        "no_premium": "❌ Требуется Telegram Premium для использования NFT подарков",
        "no_gifts": "❌ У вас нет NFT подарков",
        "loading": "💫 Получаю список подарков...",
        "current_gift": "🎁 Текущий подарок: {}",
    }
    
    strings_ru = {
        "started": "✅ Автоматическая смена NFT подарков запущена\n⏰ Интервал: {} секунд",
        "stopped": "✅ Автоматическая смена NFT подарков остановлена", 
        "already_running": "❌ Смена NFT подарков уже запущена",
        "already_stopped": "❌ Смена NFT подарков уже остановлена",
        "no_premium": "❌ Требуется Telegram Premium для использования NFT подарков",
        "no_gifts": "❌ У вас нет NFT подарков",
        "loading": "💫 Получаю список подарков...",
        "current_gift": "🎁 Текущий подарок: {}",
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
    
    async def client_ready(self, client, db):
        self._client = client
        self._db = db
        me = await self._client.get_me()
        if not me.premium:
            logger.warning("Telegram Premium required for NFT gifts")

    async def _fetch_all_saved_gifts(self):
        """Получает все сохраненные подарки"""
        try:
            first = await self._client(GetSavedStarGiftsRequest(peer="me", offset="", limit=100))
            gifts = list(first.gifts) if getattr(first, "gifts", None) else []
            total = getattr(first, "count", len(gifts))
            
            if total > len(gifts):
                pages = (total + 99) // 100
                for i in range(1, pages):
                    next_page = await self._client(GetSavedStarGiftsRequest(
                        peer="me", 
                        offset=str(100 * i).encode(), 
                        limit=100
                    ))
                    gifts.extend(next_page.gifts)
            
            return gifts
        except Exception as e:
            logger.error(f"Ошибка при получении подарков: {e}")
            return []

    async def _get_nft_gifts(self):
        """Получает только NFT подарки с document_id"""
        all_gifts = await self._fetch_all_saved_gifts()
        nft_gifts = []
        
        for gift in all_gifts:
            if not isinstance(gift, SavedStarGift):
                continue
            
            # Фильтруем только NFT подарки (StarGiftUnique)
            if isinstance(gift.gift, StarGiftUnique):
                # Получаем document_id из NFT подарка
                if hasattr(gift.gift, 'document_id'):
                    nft_gifts.append({
                        'document_id': gift.gift.document_id,
                        'title': getattr(gift.gift, 'title', 'Unknown NFT'),
                        'gift': gift
                    })
        
        return nft_gifts

    async def _set_emoji_status(self, document_id: int):
        """Устанавливает NFT подарок как emoji статус"""
        try:
            await self._client(UpdateEmojiStatusRequest(
                emoji_status=EmojiStatus(document_id=document_id)
            ))
            return True
        except Exception as e:
            logger.error(f"Ошибка при установке emoji статуса: {e}")
            return False

    async def _change_gift(self):
        """Смена текущего NFT подарка в статусе"""
        try:
            if not self.nft_gifts:
                return

            # Выбираем следующий подарок
            nft_gift = self.nft_gifts[self.current_index]
            
            # Устанавливаем как emoji статус
            success = await self._set_emoji_status(nft_gift['document_id'])
            
            if success:
                logger.info(f"NFT подарок изменен: {nft_gift['title']}")
            
            # Переходим к следующему подарку
            self.current_index = (self.current_index + 1) % len(self.nft_gifts)
            
        except Exception as e:
            logger.error(f"Ошибка при смене подарка: {e}")

    async def _gift_loop(self):
        """Основной цикл смены подарков"""
        while self.is_running:
            try:
                await self._change_gift()
                await asyncio.sleep(self.config["interval_seconds"])
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ошибка в цикле смены подарков: {e}")
                await asyncio.sleep(60)

    @loader.command(
        en_doc="Start automatic NFT gift changing",
        ru_doc="Запустить автоматическую смену NFT подарков в статусе"
    )
    async def giftstart(self, message):
        """Запустить автоматическую смену NFT подарков в статусе"""
        if self.is_running:
            await utils.answer(message, self.strings("already_running"))
            return
        
        me = await self._client.get_me()
        if not me.premium:
            await utils.answer(message, self.strings("no_premium"))
            return
        
        # Загружаем список NFT подарков
        await utils.answer(message, self.strings("loading"))
        self.nft_gifts = await self._get_nft_gifts()
        
        if not self.nft_gifts:
            await utils.answer(message, self.strings("no_gifts"))
            return
        
        self.is_running = True
        self.current_index = 0
        self.task = asyncio.create_task(self._gift_loop())
        
        # Сразу устанавливаем первый подарок
        await self._change_gift()
        
        await utils.answer(message, self.strings("started").format(self.config["interval_seconds"]))

    @loader.command(
        en_doc="Stop automatic NFT gift changing", 
        ru_doc="Остановить автоматическую смену NFT подарков"
    )
    async def giftstop(self, message):
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
        en_doc="Show current gift status",
        ru_doc="Показать статус текущего подарка"
    )
    async def giftstatus(self, message):
        """Показать статус текущего подарка"""
        if not self.nft_gifts:
            self.nft_gifts = await self._get_nft_gifts()
        
        if not self.nft_gifts:
            await utils.answer(message, self.strings("no_gifts"))
            return
        
        status_text = f"🔄 Статус: {'активен' if self.is_running else 'остановлен'}\n"
        status_text += f"⏰ Интервал: {self.config['interval_seconds']} сек\n"
        status_text += f"🎁 Всего NFT подарков: {len(self.nft_gifts)}\n"
        
        if self.nft_gifts and self.current_index < len(self.nft_gifts):
            current_gift = self.nft_gifts[self.current_index]
            status_text += f"📊 Текущий: {current_gift['title']} ({self.current_index + 1}/{len(self.nft_gifts)})"
        
        await utils.answer(message, status_text)

    @loader.command(
        en_doc="Set change interval",
        ru_doc="Установить интервал смены подарков"
    )
    async def giftinterval(self, message):
        """Установить интервал смены подарков"""
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
        en_doc="Reload gifts list",
        ru_doc="Перезагрузить список подарков"
    )
    async def giftreload(self, message):
        """Перезагрузить список подарков"""
        await utils.answer(message, self.strings("loading"))
        self.nft_gifts = await self._get_nft_gifts()
        
        if not self.nft_gifts:
            await utils.answer(message, self.strings("no_gifts"))
            return
        
        await utils.answer(message, f"✅ Список подарков обновлен: {len(self.nft_gifts)} NFT подарков")

    @loader.command(
        en_doc="Test current gift",
        ru_doc="Протестировать текущий подарок"
    )
    async def gifttest(self, message):
        """Протестировать текущий подарок"""
        if not self.nft_gifts:
            self.nft_gifts = await self._get_nft_gifts()
        
        if not self.nft_gifts:
            await utils.answer(message, self.strings("no_gifts"))
            return
        
        current_gift = self.nft_gifts[self.current_index]
        success = await self._set_emoji_status(current_gift['document_id'])
        
        if success:
            await utils.answer(message, f"✅ Подарок установлен: {current_gift['title']}")
        else:
            await utils.answer(message, "❌ Ошибка при установке подарка")

    async def on_unload(self):
        """Остановка при выгрузке модуля"""
        if self.is_running and self.task:
            self.is_running = False
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
