__version__ = (2, 0, 0)

# meta developer: @your_username
# description: Автоматически меняет NFT подарок в статусе

import asyncio
import logging
from .. import loader, utils
from telethon.tl.functions.account import UpdateEmojiStatusRequest
from telethon.tl.types import EmojiStatus
from telethon.tl.functions.payments import GetSavedStarGiftsRequest
from telethon.tl.types import SavedStarGift, StarGiftUnique, StarGift

logger = logging.getLogger(__name__)

@loader.tds
class AutoGifts(loader.Module):
    """Автоматически меняет NFT подарок в статусе"""
    
    strings = {
        "name": "AutoGifts",
        "started": "✅ Автоматическая смена NFT подарков запущена\n⏰ Интервал: {} секунд\n🎁 Найдено подарков: {}",
        "stopped": "✅ Автоматическая смена NFT подарков остановлена",
        "already_running": "❌ Смена NFT подарков уже запущена",
        "already_stopped": "❌ Смена NFT подарков уже остановлена",
        "no_premium": "❌ Требуется Telegram Premium для использования NFT подарков",
        "no_gifts": "❌ Не найдено NFT подарков в вашем аккаунте",
        "loading": "💫 Ищу NFT подарки в вашем аккаунте...",
        "found_gifts": "✅ Найдено {} NFT подарков",
    }
    
    strings_ru = {
        "started": "✅ Автоматическая смена NFT подарков запущена\n⏰ Интервал: {} секунд\n🎁 Найдено подарков: {}",
        "stopped": "✅ Автоматическая смена NFT подарков остановлена", 
        "already_running": "❌ Смена NFT подарков уже запущена",
        "already_stopped": "❌ Смена NFT подарков уже остановлена",
        "no_premium": "❌ Требуется Telegram Premium для использования NFT подарков",
        "no_gifts": "❌ Не найдено NFT подарков в вашем аккаунте",
        "loading": "💫 Ищу NFT подарки в вашем аккаунте...",
        "found_gifts": "✅ Найдено {} NFT подарков",
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

    async def _get_saved_star_gifts(self):
        """Получает сохраненные звездные подарки"""
        try:
            result = await self._client(GetSavedStarGiftsRequest(
                peer="me",
                offset="",
                limit=100
            ))
            
            gifts = []
            if hasattr(result, 'gifts') and result.gifts:
                for gift in result.gifts:
                    if isinstance(gift, SavedStarGift):
                        # Проверяем тип подарка
                        if isinstance(gift.gift, StarGiftUnique):
                            # Это NFT подарок
                            if hasattr(gift.gift, 'document_id'):
                                gifts.append({
                                    'document_id': gift.gift.document_id,
                                    'title': getattr(gift.gift, 'title', 'NFT Gift'),
                                    'gift': gift
                                })
                                logger.info(f"Found NFT gift: {gift.gift.title} (ID: {gift.gift.document_id})")
                        
            return gifts
            
        except Exception as e:
            logger.error(f"Ошибка при получении подарков: {e}")
            return []

    async def _set_emoji_status(self, document_id: int):
        """Устанавливает эмодзи статус"""
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
                logger.info(f"Подарок изменен: {nft_gift['title']} (ID: {nft_gift['document_id']})")
            else:
                logger.error(f"Не удалось установить подарок: {nft_gift['title']}")
                # Пропускаем проблемный подарок
                self.current_index = (self.current_index + 1) % len(self.nft_gifts)
                return
            
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
        self.nft_gifts = await self._get_saved_star_gifts()
        
        if not self.nft_gifts:
            await utils.answer(message, self.strings("no_gifts"))
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
        en_doc="Reload gifts list",
        ru_doc="Обновить список подарков"
    )
    async def giftreload(self, message):
        """Обновить список подарков"""
        await utils.answer(message, self.strings("loading"))
        self.nft_gifts = await self._get_saved_star_gifts()
        
        if not self.nft_gifts:
            await utils.answer(message, self.strings("no_gifts"))
            return
        
        await utils.answer(message, self.strings("found_gifts").format(len(self.nft_gifts)))

    @loader.command(
        en_doc="Show current status",
        ru_doc="Показать текущий статус"
    )
    async def giftstatus(self, message):
        """Показать текущий статус"""
        status_text = f"🔄 Статус: {'активен' if self.is_running else 'остановлен'}\n"
        status_text += f"⏰ Интервал: {self.config['interval_seconds']} сек\n"
        status_text += f"🎁 Всего NFT подарков: {len(self.nft_gifts)}\n"
        
        if self.nft_gifts and self.current_index < len(self.nft_gifts):
            current_gift = self.nft_gifts[self.current_index]
            status_text += f"📊 Текущий: {current_gift['title']} ({self.current_index + 1}/{len(self.nft_gifts)})"
        
        await utils.answer(message, status_text)

    @loader.command(
        en_doc="List gifts",
        ru_doc="Показать список подарков"
    )
    async def giftslist(self, message):
        """Показать список подарков"""
        if not self.nft_gifts:
            await utils.answer(message, self.strings("no_gifts"))
            return
        
        gifts_text = "\n".join([f"{i+1}. {nft['title']}\n   🆔 {nft['document_id']}" for i, nft in enumerate(self.nft_gifts)])
        await utils.answer(message, f"🎁 Список NFT подарков ({len(self.nft_gifts)}):\n\n{gifts_text}")

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
        en_doc="Test current gift",
        ru_doc="Протестировать текущий подарок"
    )
    async def gifttest(self, message):
        """Протестировать текущий подарок"""
        if not self.nft_gifts:
            await utils.answer(message, self.strings("no_gifts"))
            return
        
        current_gift = self.nft_gifts[self.current_index]
        success = await self._set_emoji_status(current_gift['document_id'])
        
        if success:
            await utils.answer(message, f"✅ Подарок установлен: {current_gift['title']}")
        else:
            await utils.answer(message, f"❌ Ошибка при установке: {current_gift['title']}")

    @loader.command(
        en_doc="Debug gifts info",
        ru_doc="Отладочная информация о подарках"
    )
    async def giftdebug(self, message):
        """Отладочная информация о подарках"""
        try:
            result = await self._client(GetSavedStarGiftsRequest(
                peer="me",
                offset="",
                limit=100
            ))
            
            debug_info = f"Всего подарков в аккаунте: {getattr(result, 'count', 0)}\n"
            
            if hasattr(result, 'gifts') and result.gifts:
                for i, gift in enumerate(result.gifts[:10]):
                    if isinstance(gift, SavedStarGift):
                        gift_type = "Unknown"
                        doc_id = "N/A"
                        
                        if isinstance(gift.gift, StarGiftUnique):
                            gift_type = "NFT"
                            doc_id = getattr(gift.gift, 'document_id', 'N/A')
                        elif isinstance(gift.gift, StarGift):
                            gift_type = "Regular"
                        
                        debug_info += f"{i+1}. Тип: {gift_type}, ID: {doc_id}\n"
            
            await utils.answer(message, f"🔧 Отладочная информация:\n{debug_info}")
            
        except Exception as e:
            await utils.answer(message, f"❌ Ошибка отладки: {e}")

    async def on_unload(self):
        """Остановка при выгрузке модуля"""
        if self.is_running and self.task:
            self.is_running = False
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
