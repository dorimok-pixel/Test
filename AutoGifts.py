__version__ = 7, 7, 7
# name: AutoGifts
# meta developer: @mofkomodules
# description: Авто подарки

import asyncio
import logging
from telethon import TelegramClient
from telethon.tl.functions.account import UpdateProfileRequest

logger = logging.getLogger(__name__)

class GiftChanger:
    def __init__(self, client: TelegramClient, interval: int = 3600):
        self.client = client
        self.interval = interval
        self.is_running = False
        self.task = None
        self.current_gift_index = 0
        self.gifts = ["🎁", "🎄", "🎅", "🤶", "🧦", "🌟", "⭐", "✨", "❄️"]
        
    async def start(self):
        """Запуск автоматической смены подарков"""
        if self.is_running:
            return
            
        self.is_running = True
        self.task = asyncio.create_task(self._gift_loop())
        logger.info(f"Gift changer запущен с интервалом {self.interval} сек")
        
    async def stop(self):
        """Остановка автоматической смены подарков"""
        if not self.is_running:
            return
            
        self.is_running = False
        if self.task:
            self.task.cancel()
        logger.info("Gift changer остановлен")
        
    async def _gift_loop(self):
        """Основной цикл смены подарков"""
        while self.is_running:
            try:
                await self._change_gift()
                await asyncio.sleep(self.interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ошибка в цикле смены подарков: {e}")
                await asyncio.sleep(60)
    
    async def _change_gift(self):
        """Смена текущего подарка в профиле"""
        try:
            me = await self.client.get_me()
            current_first_name = me.first_name or ""
            
            # Убираем предыдущие подарки из имени
            clean_name = current_first_name
            for gift in self.gifts:
                clean_name = clean_name.replace(gift, "").strip()
            
            # Добавляем новый подарок
            gift = self.gifts[self.current_gift_index]
            new_first_name = f"{clean_name} {gift}".strip()
            
            await self.client(UpdateProfileRequest(first_name=new_first_name))
            
            self.current_gift_index = (self.current_gift_index + 1) % len(self.gifts)
            logger.debug(f"Подарок обновлен: {new_first_name}")
            
        except Exception as e:
            logger.error(f"Ошибка при смене подарка: {e}")

# Инициализация модуля
async def initialize_gift_changer(client: TelegramClient, config: dict):
    """Инициализация модуля смены подарков"""
    logger.info("Инициализация модуля GiftChanger...")
    
    interval = config.get('gift_change_interval', 3600)
    gift_changer = GiftChanger(client, interval)
    
    # Автозапуск если указано в конфиге
    if config.get('gift_auto_start', True):
        await gift_changer.start()
    
    logger.info("Модуль GiftChanger инициализирован")
    return gift_changer
