__version__ = (2, 0, 0)
# name: AutoGifts
# meta developer: @mofkomodules
# description: Автоматически меняет NFT подарок в профиле

import asyncio
import logging
from telethon.tl.functions.account import UpdateEmojiStatusRequest
from telethon.tl.types import EmojiStatus
from .. import loader, utils

logger = logging.getLogger(__name__)

@loader.tds
class AutoGifts(loader.Module):
    """Автоматически меняет NFT подарок в профиле"""
    
    strings = {
        "name": "GiftChanger",
        "started": "✅ Автоматическая смена NFT подарков запущена\n⏰ Интервал: {} секунд",
        "stopped": "✅ Автоматическая смена NFT подарков остановлена",
        "already_running": "❌ Смена NFT подарков уже запущена",
        "already_stopped": "❌ Смена NFT подарков уже остановлена",
        "no_premium": "❌ Требуется Telegram Premium для использования NFT подарков",
        "no_gifts": "❌ В списке нет NFT подарков. Добавьте их командой .addgift",
        "gift_added": "✅ NFT подарок {} добавлен в список",
        "gift_removed": "✅ NFT подарок {} удален из списка",
        "gift_not_found": "❌ NFT подарок {} не найден в списке",
        "interval_updated": "✅ Интервал смены обновлен: {} секунд",
    }
    
    strings_ru = {
        "started": "✅ Автоматическая смена NFT подарков запущена\n⏰ Интервал: {} секунд",
        "stopped": "✅ Автоматическая смена NFT подарков остановлена", 
        "already_running": "❌ Смена NFT подарков уже запущена",
        "already_stopped": "❌ Смена NFT подарков уже остановлена",
        "no_premium": "❌ Требуется Telegram Premium для использования NFT подарков",
        "no_gifts": "❌ В списке нет NFT подарков. Добавьте их командой .addgift",
        "gift_added": "✅ NFT подарок {} добавлен в список",
        "gift_removed": "✅ NFT подарок {} удален из списка",
        "gift_not_found": "❌ NFT подарок {} не найден в списке",
        "interval_updated": "✅ Интервал смены обновлен: {} секунд",
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
        self.gift_ids = []
    
    async def client_ready(self, client, db):
        self._client = client
        self._db = db
        self.gift_ids = self._db.get(__name__, "gift_ids", [])
        me = await self._client.get_me()
        if not me.premium:
            logger.warning("Telegram Premium required for NFT gifts")
    
    def _save_gifts(self):
        """Сохраняет список подарков в базу данных"""
        self._db.set(__name__, "gift_ids", self.gift_ids)
    
    async def _change_gift(self):
        """Смена NFT подарка в профиле"""
        try:
            if not self.gift_ids:
                logger.error("No gifts in list")
                return
                
            me = await self._client.get_me()
            if not me.premium:
                logger.error("No Telegram Premium")
                return
                
            gift_id = self.gift_ids[self.current_index]
            
            await self._client(UpdateEmojiStatusRequest(
                emoji_status=EmojiStatus(document_id=gift_id)
            ))
            
            self.current_index = (self.current_index + 1) % len(self.gift_ids)
            logger.info(f"NFT подарок обновлен: {gift_id}")
            
        except Exception as e:
            logger.error(f"Ошибка при смене NFT подарка: {e}")
    
    async def _gift_loop(self):
        """Основной цикл смены NFT подарков"""
        while self.is_running:
            try:
                await self._change_gift()
                await asyncio.sleep(self.config["interval_seconds"])
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ошибка в цикле смены NFT подарков: {e}")
                await asyncio.sleep(60)
    
    @loader.command(
        en_doc="Start automatic NFT gift changing",
        ru_doc="Запустить автоматическую смену NFT подарков"
    )
    async def giftstart(self, message):
        """Запустить автоматическую смену NFT подарков"""
        if self.is_running:
            await utils.answer(message, self.strings("already_running"))
            return
        
        me = await self._client.get_me()
        if not me.premium:
            await utils.answer(message, self.strings("no_premium"))
            return
        
        if not self.gift_ids:
            await utils.answer(message, self.strings("no_gifts"))
            return
            
        self.is_running = True
        self.task = asyncio.create_task(self._gift_loop())
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
        en_doc="Add NFT gift ID",
        ru_doc="Добавить ID NFT подарка"
    )
    async def addgift(self, message):
        """Добавить ID NFT подарка"""
        args = utils.get_args(message)
        if not args:
            await utils.answer(message, "❌ Укажите ID подарка")
            return
        
        try:
            gift_id = int(args[0])
            if gift_id not in self.gift_ids:
                self.gift_ids.append(gift_id)
                self._save_gifts()
                await utils.answer(message, self.strings("gift_added").format(gift_id))
            else:
                await utils.answer(message, f"❌ NFT подарок {gift_id} уже есть в списке")
        except ValueError:
            await utils.answer(message, "❌ Укажите числовой ID")
    
    @loader.command(
        en_doc="Remove NFT gift ID",
        ru_doc="Удалить ID NFT подарка"
    )
    async def delgift(self, message):
        """Удалить ID NFT подарка"""
        args = utils.get_args(message)
        if not args:
            await utils.answer(message, "❌ Укажите ID подарка для удаления")
            return
        
        try:
            gift_id = int(args[0])
            if gift_id in self.gift_ids:
                self.gift_ids.remove(gift_id)
                self._save_gifts()
                if self.current_index >= len(self.gift_ids) and self.gift_ids:
                    self.current_index = 0
                await utils.answer(message, self.strings("gift_removed").format(gift_id))
            else:
                await utils.answer(message, self.strings("gift_not_found").format(gift_id))
        except ValueError:
            await utils.answer(message, "❌ Укажите числовой ID")
    
    @loader.command(
        en_doc="List NFT gifts",
        ru_doc="Показать список NFT подарков"
    )
    async def giftslist(self, message):
        """Показать список NFT подарков"""
        if not self.gift_ids:
            await utils.answer(message, self.strings("no_gifts"))
            return
        
        gifts_text = "\n".join([f"• {gid}" for gid in self.gift_ids])
        await utils.answer(message, f"🎁 Список NFT подарков ({len(self.gift_ids)}):\n{gifts_text}")
    
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
            await utils.answer(message, self.strings("interval_updated").format(seconds))
            
        except ValueError:
            await utils.answer(message, "❌ Укажите целое число секунд")
    
    @loader.command(
        en_doc="Clear all gifts",
        ru_doc="Очистить список подарков"
    )
    async def cleargifts(self, message):
        """Очистить список подарков"""
        if not self.gift_ids:
            await utils.answer(message, "📭 Список подарков уже пуст")
            return
            
        self.gift_ids.clear()
        self._save_gifts()
        self.current_index = 0
        await utils.answer(message, "✅ Список подарков очищен")
    
    async def on_unload(self):
        """Остановка при выгрузке модуля"""
        if self.is_running and self.task:
            self.is_running = False
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass 
