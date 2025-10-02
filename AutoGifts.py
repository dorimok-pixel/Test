__version__ = (1, 0, 0)

# meta developer: @your_username
# description: Автоматически меняет NFT подарок в статусе

import asyncio
import logging
from .. import loader, utils
from telethon.tl.functions.account import UpdateEmojiStatusRequest
from telethon.tl.types import EmojiStatus

logger = logging.getLogger(__name__)

@loader.tds
class GiftChangerMod(loader.Module):
    """Автоматически меняет NFT подарок в статусе"""
    
    strings = {
        "name": "GiftChanger",
        "started": "✅ Автоматическая смена NFT подарков запущена\n⏰ Интервал: {} секунд\n🎁 Найдено подарков: {}",
        "stopped": "✅ Автоматическая смена NFT подарков остановлена",
        "already_running": "❌ Смена NFT подарков уже запущена",
        "already_stopped": "❌ Смена NFT подарков уже остановлена",
        "no_premium": "❌ Требуется Telegram Premium для использования NFT подарков",
        "no_gifts": "❌ Не удалось найти NFT подарки",
        "loading": "💫 Ищу NFT подарки...",
        "debug_info": "🔧 Информация для отладки:\n{}",
    }
    
    strings_ru = {
        "started": "✅ Автоматическая смена NFT подарков запущена\n⏰ Интервал: {} секунд\n🎁 Найдено подарков: {}",
        "stopped": "✅ Автоматическая смена NFT подарков остановлена", 
        "already_running": "❌ Смена NFT подарков уже запущена",
        "already_stopped": "❌ Смена NFT подарков уже остановлена",
        "no_premium": "❌ Требуется Telegram Premium для использования NFT подарков",
        "no_gifts": "❌ Не удалось найти NFT подарки",
        "loading": "💫 Ищу NFT подарки...",
        "debug_info": "🔧 Информация для отладки:\n{}",
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

    async def _get_available_gifts(self):
        """Получает доступные подарки через различные методы"""
        gifts = []
        
        try:
            # Метод 1: Попробуем получить подарки через get_stickers
            async for dialog in self._client.iter_dialogs():
                if dialog.is_channel or dialog.is_group:
                    try:
                        # Получаем сообщения с медиа
                        async for message in self._client.iter_messages(dialog.id, limit=50):
                            if message.media:
                                # Проверяем, является ли медиа подарком
                                if hasattr(message.media, 'document'):
                                    doc = message.media.document
                                    if hasattr(doc, 'attributes'):
                                        for attr in doc.attributes:
                                            if hasattr(attr, 'alt') and attr.alt:
                                                # Это может быть кастомный эмодзи
                                                gifts.append({
                                                    'document_id': doc.id,
                                                    'title': attr.alt,
                                                    'type': 'custom_emoji'
                                                })
                    except Exception as e:
                        continue
            
            # Метод 2: Ищем в избранных стикерах
            try:
                featured_stickers = await self._client.get_featured_stickers()
                for sticker_set in featured_stickers.sets:
                    stickers = await self._client.get_stickers(sticker_set.id)
                    for sticker in stickers:
                        if hasattr(sticker, 'id'):
                            gifts.append({
                                'document_id': sticker.id,
                                'title': f"Sticker {sticker.id}",
                                'type': 'sticker'
                            })
            except Exception as e:
                logger.debug(f"Error getting featured stickers: {e}")
                
        except Exception as e:
            logger.error(f"Error getting gifts: {e}")
        
        return gifts

    async def _get_nft_gifts_from_emoji(self):
        """Получает NFT подарки через кастомные эмодзи"""
        gifts = []
        
        try:
            # Получаем все кастомные эмодзи
            emoji_packs = []
            
            # Попробуем несколько популярных наборов эмодзи
            test_packs = [
                "TelegramStars",
                "TelegramNFT", 
                "StarGifts",
                "PremiumGifts"
            ]
            
            for pack_name in test_packs:
                try:
                    stickers = await self._client.get_stickers(pack_name)
                    for sticker in stickers:
                        gifts.append({
                            'document_id': sticker.id,
                            'title': getattr(sticker, 'alt', f'Emoji {sticker.id}'),
                            'type': 'emoji'
                        })
                except Exception:
                    continue
            
            # Также пробуем получить эмодзи из нашего аккаунта
            try:
                me = await self._client.get_me()
                if hasattr(me, 'emoji_status'):
                    if me.emoji_status and hasattr(me.emoji_status, 'document_id'):
                        gifts.append({
                            'document_id': me.emoji_status.document_id,
                            'title': 'Current Status',
                            'type': 'current_status'
                        })
            except Exception as e:
                logger.debug(f"Error getting current status: {e}")
                
        except Exception as e:
            logger.error(f"Error getting emoji gifts: {e}")
        
        return gifts

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
        
        # Пробуем разные методы получения подарков
        self.nft_gifts = await self._get_nft_gifts_from_emoji()
        
        if not self.nft_gifts:
            # Если не нашли через эмодзи, пробуем общий метод
            self.nft_gifts = await self._get_available_gifts()
        
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
        en_doc="Show current gift status",
        ru_doc="Показать статус текущего подарка"
    )
    async def giftstatus(self, message):
        """Показать статус текущего подарка"""
        status_text = f"🔄 Статус: {'активен' if self.is_running else 'остановлен'}\n"
        status_text += f"⏰ Интервал: {self.config['interval_seconds']} сек\n"
        
        if self.nft_gifts:
            status_text += f"🎁 Всего подарков: {len(self.nft_gifts)}\n"
            if self.current_index < len(self.nft_gifts):
                current_gift = self.nft_gifts[self.current_index]
                status_text += f"📊 Текущий: {current_gift['title']} ({self.current_index + 1}/{len(self.nft_gifts)})"
        else:
            status_text += "🎁 Подарки не загружены"
        
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
        
        self.nft_gifts = await self._get_nft_gifts_from_emoji()
        if not self.nft_gifts:
            self.nft_gifts = await self._get_available_gifts()
        
        if not self.nft_gifts:
            await utils.answer(message, self.strings("no_gifts"))
            return
        
        await utils.answer(message, f"✅ Список подарков обновлен: {len(self.nft_gifts)} подарков")

    @loader.command(
        en_doc="Debug gifts info",
        ru_doc="Отладочная информация о подарках"
    )
    async def giftdebug(self, message):
        """Отладочная информация о подарках"""
        debug_info = f"Всего подарков: {len(self.nft_gifts)}\n"
        debug_info += f"Текущий индекс: {self.current_index}\n"
        debug_info += f"Запущен: {self.is_running}\n\n"
        
        for i, gift in enumerate(self.nft_gifts[:10]):  # Показываем первые 10
            debug_info += f"{i+1}. {gift['title']} (ID: {gift['document_id']}, тип: {gift.get('type', 'unknown')})\n"
        
        if len(self.nft_gifts) > 10:
            debug_info += f"... и еще {len(self.nft_gifts) - 10} подарков"
        
        await utils.answer(message, self.strings("debug_info").format(debug_info))

    @loader.command(
        en_doc="Add gift by ID",
        ru_doc="Добавить подарок по ID"
    )
    async def addgift(self, message):
        """Добавить подарок по ID"""
        args = utils.get_args(message)
        if not args:
            await utils.answer(message, "❌ Укажите ID подарка\nПример: .addgift 123456789")
            return
        
        try:
            doc_id = int(args[0])
            title = args[1] if len(args) > 1 else f"Gift {doc_id}"
            
            # Проверяем, есть ли уже такой подарок
            for gift in self.nft_gifts:
                if gift['document_id'] == doc_id:
                    await utils.answer(message, f"❌ Подарок с ID {doc_id} уже есть в списке")
                    return
            
            self.nft_gifts.append({
                'document_id': doc_id,
                'title': title,
                'type': 'manual'
            })
            
            await utils.answer(message, f"✅ Подарок добавлен: {title} (ID: {doc_id})")
            
        except ValueError:
            await utils.answer(message, "❌ Укажите числовой ID")

    async def on_unload(self):
        """Остановка при выгрузке модуля"""
        if self.is_running and self.task:
            self.is_running = False
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
