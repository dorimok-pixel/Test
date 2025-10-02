__version__ = (1, 0, 0)

# meta developer: @mofkomodules
# description: Автоматически меняет NFT подарок в профиле

import asyncio
import logging
from telethon.tl.functions.account import UpdateEmojiStatusRequest
from telethon.tl.types import EmojiStatus
from .. import loader, utils

logger = logging.getLogger(__name__)

@loader.tds
class GiftChangerMod(loader.Module):
    """Автоматически меняет NFT подарок в профиле"""
    
    strings = {
        "name": "GiftChanger",
        "started": "✅ Автоматическая смена NFT подарков запущена",
        "stopped": "✅ Автоматическая смена NFT подарков остановлена",
        "already_running": "❌ Смена NFT подарков уже запущена",
        "already_stopped": "❌ Смена NFT подарков уже остановлена",
        "no_premium": "❌ Требуется Telegram Premium для использования NFT подарков",
    }
    
    strings_ru = {
        "started": "✅ Автоматическая смена NFT подарков запущена",
        "stopped": "✅ Автоматическая смена NFT подарков остановлена", 
        "already_running": "❌ Смена NFT подарков уже запущена",
        "already_stopped": "❌ Смена NFT подарков уже остановлена",
        "no_premium": "❌ Требуется Telegram Premium для использования NFT подарков",
    }
    
    def __init__(self):
        self.is_running = False
        self.task = None
        self.current_index = 0
        self.interval = 3600
        
        self.gift_ids = [
            123456789,  
            123456790,
            123456791,
        ]
    
    async def client_ready(self, client, db):
        self._client = client
        me = await self._client.get_me()
        if not me.premium:
            logger.warning("Telegram Premium required for NFT gifts")
    
    async def _change_gift(self):
        """Смена NFT подарка в профиле"""
        try:
            me = await self._client.get_me()
            if not me.premium:
                logger.error("No Telegram Premium")
                return
            
            if not self.gift_ids:
                logger.error("No gift IDs configured")
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
                await asyncio.sleep(self.interval)
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
            
        self.is_running = True
        self.task = asyncio.create_task(self._gift_loop())
        await utils.answer(message, self.strings("started"))
    
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
                await utils.answer(message, f"✅ NFT подарок {gift_id} добавлен")
            else:
                await utils.answer(message, f"❌ NFT подарок {gift_id} уже есть в списке")
        except ValueError:
            await utils.answer(message, "❌ Укажите числовой ID")
    
    @loader.command(
        en_doc="List NFT gifts",
        ru_doc="Показать список NFT подарков"
    )
    async def giftslist(self, message):
        """Показать список NFT подарков"""
        if not self.gift_ids:
            await utils.answer(message, "📭 Список NFT подарков пуст")
            return
        
        gifts_text = "\n".join([f"• {gid}" for gid in self.gift_ids])
        await utils.answer(message, f"🎁 Список NFT подарков:\n{gifts_text}")
    
    async def on_unload(self):
        """Остановка при выгрузке модуля"""
        if self.is_running and self.task:
            self.is_running = False
            self.task.cancel()
