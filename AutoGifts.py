__version__ = (1, 0, 0)

# meta developer: @your_username
# description: Автоматически меняет NFT подарок в статусе

import asyncio
import logging
import re
from .. import loader, utils
from telethon.tl.functions.account import UpdateEmojiStatusRequest
from telethon.tl.types import EmojiStatus

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
        "no_gifts": "❌ Нет добавленных подарков",
        "loading": "💫 Получаю информацию о NFT...",
        "invalid_link": "❌ Неверная ссылка на NFT\nПример: t.me/nft/SwagBag-22090",
        "nft_added": "✅ NFT подарок добавлен: {}\nID: {}",
        "nft_not_found": "❌ Не удалось получить информацию о NFT",
    }
    
    strings_ru = {
        "started": "✅ Автоматическая смена NFT подарков запущена\n⏰ Интервал: {} секунд\n🎁 Найдено подарков: {}",
        "stopped": "✅ Автоматическая смена NFT подарков остановлена", 
        "already_running": "❌ Смена NFT подарков уже запущена",
        "already_stopped": "❌ Смена NFT подарков уже остановлена",
        "no_premium": "❌ Требуется Telegram Premium для использования NFT подарков",
        "no_gifts": "❌ Нет добавленных подарков",
        "loading": "💫 Получаю информацию о NFT...",
        "invalid_link": "❌ Неверная ссылка на NFT\nПример: t.me/nft/SwagBag-22090",
        "nft_added": "✅ NFT подарок добавлен: {}\nID: {}",
        "nft_not_found": "❌ Не удалось получить информацию о NFT",
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
        # Загружаем список подарков из базы данных
        self.nft_gifts = self._db.get(__name__, "nft_gifts", [])
        me = await self._client.get_me()
        if not me.premium:
            logger.warning("Telegram Premium required for NFT gifts")

    def _save_gifts(self):
        """Сохраняет список подарков в базу данных"""
        self._db.set(__name__, "nft_gifts", self.nft_gifts)

    async def _get_nft_from_link(self, link: str):
        """Получает информацию о NFT из ссылки"""
        try:
            # Парсим ссылку формата t.me/nft/SwagBag-22090
            pattern = r"t\.me/nft/([A-Za-z0-9_-]+)"
            match = re.search(pattern, link)
            
            if not match:
                logger.error(f"Invalid link format: {link}")
                return None
            
            nft_slug = match.group(1)
            logger.info(f"Searching for NFT: {nft_slug}")
            
            # Пробуем получить информацию через канал NFT
            try:
                entity = await self._client.get_entity("t.me/nft")
            except Exception as e:
                logger.error(f"Can't access @nft channel: {e}")
                return None
            
            # Ищем сообщения с этим NFT
            async for message in self._client.iter_messages(entity, limit=200):
                if not message.text:
                    continue
                    
                # Ищем упоминание NFT в тексте сообщения
                if nft_slug in message.text:
                    logger.info(f"Found message with NFT: {message.id}")
                    
                    # Пытаемся найти document_id в медиа
                    if message.media:
                        logger.info(f"Message has media: {type(message.media)}")
                        
                        if hasattr(message.media, 'document'):
                            doc_id = message.media.document.id
                            logger.info(f"Found document ID: {doc_id}")
                            return {
                                'document_id': doc_id,
                                'title': nft_slug,
                                'link': link
                            }
                        elif hasattr(message.media, 'webpage'):
                            if hasattr(message.media.webpage, 'document'):
                                doc_id = message.media.webpage.document.id
                                logger.info(f"Found webpage document ID: {doc_id}")
                                return {
                                    'document_id': doc_id,
                                    'title': nft_slug,
                                    'link': link
                                }
            
            logger.warning(f"NFT not found in @nft channel: {nft_slug}")
            return None
            
        except Exception as e:
            logger.error(f"Ошибка при получении NFT из ссылки: {e}")
            return None

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
                logger.info(f"Подарок изменен: {nft_gift['title']}")
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
        en_doc="Add NFT gift by link",
        ru_doc="Добавить NFT подарок по ссылке"
    )
    async def addgift(self, message):
        """Добавить NFT подарок по ссылке"""
        args = utils.get_args(message)
        if not args:
            await utils.answer(message, 
                "❌ Укажите ссылку на NFT\n"
                "📝 Пример:\n"
                ".addgift t.me/nft/SwagBag-22090\n\n"
                "🔗 Как получить ссылку:\n"
                "1. Найдите NFT в канале @nft\n"
                "2. Скопируйте ссылку вида: t.me/nft/Название-NUMBER"
            )
            return
        
        link = args[0].strip()
        
        # Проверяем формат ссылки
        if not link.startswith(('t.me/nft/', 'https://t.me/nft/')):
            await utils.answer(message, self.strings("invalid_link"))
            return
        
        await utils.answer(message, self.strings("loading"))
        
        # Получаем информацию о NFT
        nft_info = await self._get_nft_from_link(link)
        
        if not nft_info:
            await utils.answer(message, self.strings("nft_not_found"))
            return
        
        # Проверяем нет ли уже такого NFT
        for existing_nft in self.nft_gifts:
            if existing_nft['link'] == link:
                await utils.answer(message, f"❌ NFT уже есть в списке: {existing_nft['title']}")
                return
        
        # Добавляем NFT в список
        self.nft_gifts.append(nft_info)
        self._save_gifts()
        
        await utils.answer(message, self.strings("nft_added").format(nft_info['title'], nft_info['document_id']))

    @loader.command(
        en_doc="Remove NFT gift",
        ru_doc="Удалить NFT подарок"
    )
    async def delgift(self, message):
        """Удалить NFT подарок"""
        args = utils.get_args(message)
        if not args:
            # Показываем список для удаления
            if not self.nft_gifts:
                await utils.answer(message, self.strings("no_gifts"))
                return
            
            gifts_list = "\n".join([f"{i+1}. {nft['title']} - {nft['link']}" for i, nft in enumerate(self.nft_gifts)])
            await utils.answer(message, f"🎁 Выберите NFT для удаления:\n{gifts_list}\n\nИспользуйте: .delgift <номер>")
            return
        
        try:
            index = int(args[0]) - 1
            if 0 <= index < len(self.nft_gifts):
                removed_nft = self.nft_gifts.pop(index)
                self._save_gifts()
                # Корректируем текущий индекс если нужно
                if self.current_index >= len(self.nft_gifts) and self.nft_gifts:
                    self.current_index = 0
                await utils.answer(message, f"✅ NFT удален: {removed_nft['title']}")
            else:
                await utils.answer(message, "❌ Неверный номер NFT")
        except ValueError:
            await utils.answer(message, "❌ Укажите номер NFT")

    @loader.command(
        en_doc="List gifts",
        ru_doc="Показать список подарков"
    )
    async def giftslist(self, message):
        """Показать список подарков"""
        if not self.nft_gifts:
            await utils.answer(message, self.strings("no_gifts"))
            return
        
        gifts_text = "\n".join([f"{i+1}. {nft['title']}\n   🔗 {nft['link']}\n   🆔 {nft['document_id']}" for i, nft in enumerate(self.nft_gifts)])
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
        en_doc="Clear all gifts",
        ru_doc="Очистить список подарков"
    )
    async def cleargifts(self, message):
        """Очистить список подарков"""
        if not self.nft_gifts:
            await utils.answer(message, "📭 Список подарков уже пуст")
            return
            
        self.nft_gifts.clear()
        self._save_gifts()
        self.current_index = 0
        await utils.answer(message, "✅ Список подарков очищен")

    @loader.command(
        en_doc="Show current status",
        ru_doc="Показать текущий статус"
    )
    async def giftstatus(self, message):
        """Показать текущий статус"""
        status_text = f"🔄 Статус: {'активен' if self.is_running else 'остановлен'}\n"
        status_text += f"⏰ Интервал: {self.config['interval_seconds']} сек\n"
        status_text += f"🎁 Всего подарков: {len(self.nft_gifts)}\n"
        
        if self.nft_gifts and self.current_index < len(self.nft_gifts):
            current_gift = self.nft_gifts[self.current_index]
            status_text += f"📊 Текущий: {current_gift['title']} ({self.current_index + 1}/{len(self.nft_gifts)})"
        
        await utils.answer(message, status_text)

    @loader.command(
        en_doc="Add gift by ID manually",
        ru_doc="Добавить подарок по ID вручную"
    )
    async def addgiftid(self, message):
        """Добавить подарок по ID вручную"""
        args = utils.get_args(message)
        if len(args) < 2:
            await utils.answer(message, 
                "❌ Укажите ID и название подарка\n"
                "📝 Пример:\n"
                ".addgiftid 123456789 \"Мой NFT\"\n\n"
                "🔧 Как найти ID:\n"
                "1. Используйте другие модули для просмотра ID подарков\n"
                "2. Или найдите ID через отладку"
            )
            return
        
        try:
            doc_id = int(args[0])
            title = args[1]
            link = f"manual_{doc_id}"
            
            # Проверяем нет ли уже такого ID
            for existing_nft in self.nft_gifts:
                if existing_nft['document_id'] == doc_id:
                    await utils.answer(message, f"❌ Подарок с ID {doc_id} уже есть в списке")
                    return
            
            nft_info = {
                'document_id': doc_id,
                'title': title,
                'link': link
            }
            
            self.nft_gifts.append(nft_info)
            self._save_gifts()
            
            await utils.answer(message, f"✅ Подарок добавлен: {title}\nID: {doc_id}")
            
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
