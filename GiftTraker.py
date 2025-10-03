__version__ = (1, 0, 0)

# meta developer: @your_username
# description: Умные уведомления о подарках и звездах

import asyncio
import logging
from datetime import datetime, timedelta
from collections import defaultdict
from .. import loader, utils
from telethon.tl.functions.payments import (
    GetSavedStarGiftsRequest,
    GetStarGiftsRequest
)
from telethon.tl.types import (
    SavedStarGift,
    StarGiftUnique,
    StarGift
)

logger = logging.getLogger(__name__)

@loader.tds
class GiftNotifier(loader.Module):
    """Умные уведомления о подарках"""
    
    strings = {
        "name": "GiftNotifier",
        "started": "✅ GiftNotifier запущен\n📊 Отслеживаю: {}",
        "stopped": "✅ GiftNotifier остановлен",
        "settings": "⚙️ Настройки уведомлений:\n{}",
        "no_tracking": "❌ Не выбрано ни одного типа уведомлений",
        "stats": "📈 Статистика за сегодня:\n{}",
    }
    
    strings_ru = {
        "started": "✅ GiftNotifier запущен\n📊 Отслеживаю: {}",
        "stopped": "✅ GiftNotifier остановлен", 
        "settings": "⚙️ Настройки уведомлений:\n{}",
        "no_tracking": "❌ Не выбрано ни одного типа уведомлений",
        "stats": "📈 Статистика за сегодня:\n{}",
    }
    
    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "check_interval",
                300,
                "Интервал проверки в секундах",
                validator=loader.validators.Integer(minimum=60)
            ),
            loader.ConfigValue(
                "track_personal_gifts",
                True,
                "Отслеживать личные подарки",
                validator=loader.validators.Boolean()
            ),
            loader.ConfigValue(
                "track_new_gifts",
                True,
                "Отслеживать новые подарки",
                validator=loader.validators.Boolean()
            ),
            loader.ConfigValue(
                "notify_to_me",
                True,
                "Отправлять уведомления себе в лс",
                validator=loader.validators.Boolean()
            )
        )
        
        self.is_running = False
        self.task = None
        self.personal_gifts_cache = set()
        self.star_gifts_cache = set()
        self.notification_stats = defaultdict(int)
        self.last_stats_reset = datetime.now()
        self.me = None

    async def client_ready(self, client, db):
        self._client = client
        self._db = db
        self.me = await self._client.get_me()
        self._load_cache()

    def _load_cache(self):
        """Загружает кэш из базы данных"""
        self.personal_gifts_cache = set(self._db.get(__name__, "personal_gifts_cache", []))
        self.star_gifts_cache = set(self._db.get(__name__, "star_gifts_cache", []))

    def _save_cache(self):
        """Сохраняет кэш в базу данных"""
        self._db.set(__name__, "personal_gifts_cache", list(self.personal_gifts_cache))
        self._db.set(__name__, "star_gifts_cache", list(self.star_gifts_cache))

    async def _send_notification(self, title: str, message: str):
        """Отправляет уведомление"""
        try:
            full_message = f"🎯 **{title}**\n\n{message}"
            
            if self.config["notify_to_me"] and self.me:
                await self._client.send_message(self.me.id, full_message)
            else:
                # Если уведомления отключены, просто логируем
                logger.info(f"Notification: {title} - {message}")
                
        except Exception as e:
            logger.error(f"Error sending notification: {e}")

    async def _get_saved_star_gifts(self):
        """Получает сохраненные подарки"""
        try:
            # Правильные параметры для GetSavedStarGiftsRequest
            result = await self._client(GetSavedStarGiftsRequest(
                peer=self.me,
                offset="",
                limit=100
            ))
            return result
        except Exception as e:
            logger.error(f"Error getting saved gifts: {e}")
            return None

    async def _get_star_gifts(self):
        """Получает доступные подарки"""
        try:
            # Для GetStarGiftsRequest нужен hash, используем 0
            result = await self._client(GetStarGiftsRequest(
                hash=0
            ))
            return result
        except Exception as e:
            logger.error(f"Error getting star gifts: {e}")
            return None

    async def _check_personal_gifts(self):
        """Проверяет личные подарки"""
        if not self.config["track_personal_gifts"]:
            return

        try:
            result = await self._get_saved_star_gifts()
            if not result or not hasattr(result, 'gifts'):
                return

            current_gifts = set()
            new_gifts = []

            for gift in result.gifts:
                if isinstance(gift, SavedStarGift) and hasattr(gift, 'msg_id'):
                    gift_id = gift.msg_id
                    current_gifts.add(gift_id)

                    # Проверяем новый ли это подарок
                    if gift_id not in self.personal_gifts_cache:
                        gift_title = "Неизвестный подарок"
                        gift_type = "Обычный"
                        
                        if hasattr(gift, 'gift'):
                            if isinstance(gift.gift, StarGiftUnique):
                                gift_type = "NFT"
                                if hasattr(gift.gift, 'title'):
                                    gift_title = gift.gift.title
                            elif isinstance(gift.gift, StarGift):
                                gift_type = "Звездный"
                                if hasattr(gift.gift, 'title'):
                                    gift_title = gift.gift.title
                        
                        new_gifts.append({
                            'title': gift_title,
                            'type': gift_type,
                            'id': gift_id
                        })

            # Отправляем уведомления о новых подарках
            for new_gift in new_gifts:
                message = (
                    f"🎁 **{new_gift['title']}**\n"
                    f"💎 Тип: {new_gift['type']}\n"
                    f"🆔 ID: {new_gift['id']}\n"
                    f"✅ Добавлен в вашу коллекцию"
                )
                await self._send_notification("Новый личный подарок", message)
                self.notification_stats["personal"] += 1

            # Обновляем кэш
            self.personal_gifts_cache = current_gifts
            self._save_cache()

        except Exception as e:
            logger.error(f"Error checking personal gifts: {e}")

    async def _check_new_gifts(self):
        """Проверяет новые подарки в каталоге"""
        if not self.config["track_new_gifts"]:
            return

        try:
            result = await self._get_star_gifts()
            if not result or not hasattr(result, 'gifts'):
                return

            current_gifts = set()
            new_gifts = []

            for gift in result.gifts:
                if hasattr(gift, 'id'):
                    gift_id = gift.id
                    current_gifts.add(gift_id)

                    # Проверяем новый ли это подарок
                    if gift_id not in self.star_gifts_cache:
                        gift_title = getattr(gift, 'title', f'Подарок #{gift_id}')
                        gift_type = type(gift).__name__
                        
                        new_gifts.append({
                            'title': gift_title,
                            'type': gift_type,
                            'id': gift_id
                        })

            # Отправляем уведомления о новых подарках
            for new_gift in new_gifts:
                message = (
                    f"🎁 **{new_gift['title']}**\n"
                    f"💎 Тип: {new_gift['type']}\n"
                    f"🆔 ID: {new_gift['id']}\n"
                    f"⭐ Доступен для покупки"
                )
                await self._send_notification("Новый подарок в каталоге", message)
                self.notification_stats["new"] += 1

            # Обновляем кэш
            self.star_gifts_cache = current_gifts
            self._save_cache()

        except Exception as e:
            logger.error(f"Error checking new gifts: {e}")

    async def _monitoring_loop(self):
        """Основной цикл мониторинга"""
        while self.is_running:
            try:
                logger.info("Starting monitoring cycle...")
                
                # Выполняем проверки
                if self.config["track_personal_gifts"]:
                    await self._check_personal_gifts()
                
                if self.config["track_new_gifts"]:
                    await self._check_new_gifts()
                
                # Сбрасываем статистику каждый день
                if datetime.now() - self.last_stats_reset > timedelta(days=1):
                    self.notification_stats.clear()
                    self.last_stats_reset = datetime.now()
                
                await asyncio.sleep(self.config["check_interval"])
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(60)

    @loader.command(
        en_doc="Start gift notifications",
        ru_doc="Запустить уведомления о подарках"
    )
    async def giftnotifystart(self, message):
        """Запустить уведомления о подарках"""
        if self.is_running:
            await utils.answer(message, "❌ GiftNotifier уже запущен")
            return
        
        # Проверяем что хотя бы один тип уведомлений включен
        enabled_trackers = []
        if self.config["track_personal_gifts"]:
            enabled_trackers.append("🎯 Личные подарки")
        if self.config["track_new_gifts"]:
            enabled_trackers.append("🎁 Новые подарки")
        
        if not enabled_trackers:
            await utils.answer(message, self.strings("no_tracking"))
            return
        
        self.is_running = True
        self.task = asyncio.create_task(self._monitoring_loop())
        
        trackers_text = "\n".join([f"• {tracker}" for tracker in enabled_trackers])
        await utils.answer(message, self.strings("started").format(trackers_text))

    @loader.command(
        en_doc="Stop gift notifications",
        ru_doc="Остановить уведомления о подарках"
    )
    async def giftnotifystop(self, message):
        """Остановить уведомления о подарках"""
        if not self.is_running:
            await utils.answer(message, "❌ GiftNotifier уже остановлен")
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
        en_doc="Show notification settings",
        ru_doc="Показать настройки уведомлений"
    )
    async def giftnotifysettings(self, message):
        """Показать настройки уведомлений"""
        settings_text = (
            f"⏰ Интервал проверки: {self.config['check_interval']} сек\n"
            f"🎯 Личные подарки: {'✅' if self.config['track_personal_gifts'] else '❌'}\n"
            f"🎁 Новые подарки: {'✅' if self.config['track_new_gifts'] else '❌'}\n"
            f"📢 Уведомления в лс: {'✅' if self.config['notify_to_me'] else '❌'}"
        )
        
        await utils.answer(message, self.strings("settings").format(settings_text))

    @loader.command(
        en_doc="Show notification statistics",
        ru_doc="Показать статистику уведомлений"
    )
    async def giftnotifystats(self, message):
        """Показать статистику уведомлений"""
        if not self.notification_stats:
            await utils.answer(message, "📊 Статистика пуста")
            return
        
        stats_text = "\n".join([
            f"🎯 Личные подарки: {self.notification_stats.get('personal', 0)}",
            f"🎁 Новые подарки: {self.notification_stats.get('new', 0)}",
            f"📅 Всего сегодня: {sum(self.notification_stats.values())}"
        ])
        
        await utils.answer(message, self.strings("stats").format(stats_text))

    @loader.command(
        en_doc="Clear notification cache",
        ru_doc="Очистить кэш уведомлений"
    )
    async def giftnotifyclear(self, message):
        """Очистить кэш уведомлений"""
        self.personal_gifts_cache.clear()
        self.star_gifts_cache.clear()
        self._save_cache()
        
        await utils.answer(message, "✅ Кэш уведомлений очищен")

    @loader.command(
        en_doc="Test notification",
        ru_doc="Тестовое уведомление"
    )
    async def giftnotifytest(self, message):
        """Тестовое уведомление"""
        test_message = (
            f"🎯 **Тестовое уведомление**\n\n"
            f"✅ Модуль GiftNotifier работает корректно\n"
            f"⏰ Время: {datetime.now().strftime('%H:%M:%S')}\n"
            f"📊 Статус: {'Активен' if self.is_running else 'Остановлен'}"
        )
        
        if self.config["notify_to_me"] and self.me:
            await self._client.send_message(self.me.id, test_message)
            await utils.answer(message, "✅ Тестовое уведомление отправлено в лс")
        else:
            await utils.answer(message, test_message)

    async def on_unload(self):
        """Остановка при выгрузке модуля"""
        if self.is_running and self.task:
            self.is_running = False
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        self._save_cache()
