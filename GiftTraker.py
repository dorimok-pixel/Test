__version__ = (2, 0, 0)

# meta developer: @your_username
# description: Умные уведомления о подарках и звездах

import asyncio
import logging
import time
from datetime import datetime, timedelta
from collections import defaultdict
from .. import loader, utils
from telethon.tl.functions.payments import (
    GetSavedStarGiftsRequest,
    GetResaleStarGiftsRequest,
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
        "notification": "🎯 {}\n\n{}",
        "no_tracking": "❌ Не выбрано ни одного типа уведомлений",
        "stats": "📈 Статистика за сегодня:\n{}",
        "price_alert": "💸 Изменение цены: {}",
        "new_gift": "🎁 Новый подарок: {}",
        "collection_update": "🆕 Обновление коллекции: {}",
        "giveaway_start": "🎉 Новый розыгрыш: {}",
    }
    
    strings_ru = {
        "started": "✅ GiftNotifier запущен\n📊 Отслеживаю: {}",
        "stopped": "✅ GiftNotifier остановлен", 
        "settings": "⚙️ Настройки уведомлений:\n{}",
        "notification": "🎯 {}\n\n{}",
        "no_tracking": "❌ Не выбрано ни одного типа уведомлений",
        "stats": "📈 Статистика за сегодня:\n{}",
        "price_alert": "💸 Изменение цены: {}",
        "new_gift": "🎁 Новый подарок: {}",
        "collection_update": "🆕 Обновление коллекции: {}",
        "giveaway_start": "🎉 Новый розыгрыш: {}",
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
                "track_price_changes",
                True,
                "Отслеживать изменение цен",
                validator=loader.validators.Boolean()
            ),
            loader.ConfigValue(
                "track_new_gifts",
                True,
                "Отслеживать новые подарки",
                validator=loader.validators.Boolean()
            ),
            loader.ConfigValue(
                "track_personal_gifts",
                True,
                "Отслеживать личные подарки",
                validator=loader.validators.Boolean()
            ),
            loader.ConfigValue(
                "min_price_change_percent",
                10,
                "Минимальное изменение цены для уведомления (%)",
                validator=loader.validators.Integer(minimum=1, maximum=1000)
            ),
            loader.ConfigValue(
                "notify_channel",
                "",
                "ID канала для уведомлений (оставьте пустым для текущего чата)",
                validator=loader.validators.String()
            )
        )
        
        self.is_running = False
        self.task = None
        self.price_history = {}
        self.gift_cache = set()
        self.personal_gifts_cache = set()
        self.notification_stats = defaultdict(int)
        self.last_stats_reset = datetime.now()

    async def client_ready(self, client, db):
        self._client = client
        self._db = db
        # Загружаем кэш из базы данных
        self._load_cache()

    def _load_cache(self):
        """Загружает кэш из базы данных"""
        self.gift_cache = set(self._db.get(__name__, "gift_cache", []))
        self.personal_gifts_cache = set(self._db.get(__name__, "personal_gifts_cache", []))

    def _save_cache(self):
        """Сохраняет кэш в базу данных"""
        self._db.set(__name__, "gift_cache", list(self.gift_cache))
        self._db.set(__name__, "personal_gifts_cache", list(self.personal_gifts_cache))

    async def _send_notification(self, title: str, message: str, alert_type: str = "info"):
        """Отправляет уведомление"""
        try:
            self.notification_stats[alert_type] += 1
            
            # Создаем форматированное сообщение
            notification_text = self.strings("notification").format(title, message)
            
            # Добавляем эмодзи в зависимости от типа
            emoji_map = {
                "price": "💸",
                "new": "🎁", 
                "personal": "🎯",
                "info": "ℹ️"
            }
            
            emoji = emoji_map.get(alert_type, "🔔")
            final_message = f"{emoji} {notification_text}"
            
            # Отправляем в указанный канал или текущий чат
            if self.config["notify_channel"]:
                await self._client.send_message(int(self.config["notify_channel"]), final_message)
            else:
                await utils.answer(message, final_message)
                
            logger.info(f"Notification sent: {title}")
            
        except Exception as e:
            logger.error(f"Error sending notification: {e}")

    async def _check_price_changes(self):
        """Проверяет изменения цен на подарки"""
        if not self.config["track_price_changes"]:
            return

        try:
            # Получаем текущие цены на перепродажу
            resale_gifts = await self._client(GetResaleStarGiftsRequest())
            
            current_prices = {}
            for gift in getattr(resale_gifts, 'gifts', []):
                if hasattr(gift, 'id') and hasattr(gift, 'price'):
                    current_prices[gift.id] = gift.price

            # Сравниваем с историей цен
            for gift_id, current_price in current_prices.items():
                if gift_id in self.price_history:
                    old_price = self.price_history[gift_id]
                    if old_price > 0:
                        change_percent = ((current_price - old_price) / old_price) * 100
                        
                        if abs(change_percent) >= self.config["min_price_change_percent"]:
                            direction = "📈 вырос" if change_percent > 0 else "📉 упал"
                            message = (
                                f"Подарок #{gift_id}\n"
                                f"💰 Было: {old_price} звезд\n"
                                f"💵 Стало: {current_price} звезд\n"
                                f"📊 Изменение: {change_percent:+.1f}%"
                            )
                            await self._send_notification(
                                f"Цена {direction}",
                                message,
                                "price"
                            )

                # Обновляем историю цен
                self.price_history[gift_id] = current_price

        except Exception as e:
            logger.error(f"Error checking price changes: {e}")

    async def _check_new_gifts(self):
        """Проверяет новые подарки в каталоге"""
        if not self.config["track_new_gifts"]:
            return

        try:
            star_gifts = await self._client(GetStarGiftsRequest())
            
            current_gifts = set()
            for gift in getattr(star_gifts, 'gifts', []):
                if hasattr(gift, 'id'):
                    current_gifts.add(gift.id)
                    
                    # Проверяем новый ли это подарок
                    if gift.id not in self.gift_cache:
                        gift_title = getattr(gift, 'title', f'Подарок #{gift.id}')
                        message = (
                            f"🎁 {gift_title}\n"
                            f"💎 Тип: {type(gift).__name__}\n"
                            f"⭐ Доступен для покупки"
                        )
                        await self._send_notification(
                            "Новый подарок в каталоге",
                            message,
                            "new"
                        )

            # Обновляем кэш
            self.gift_cache = current_gifts
            self._save_cache()

        except Exception as e:
            logger.error(f"Error checking new gifts: {e}")

    async def _check_personal_gifts(self):
        """Проверяет личные подарки"""
        if not self.config["track_personal_gifts"]:
            return

        try:
            saved_gifts = await self._client(GetSavedStarGiftsRequest(peer="me", offset="", limit=100))
            
            current_personal = set()
            for gift in getattr(saved_gifts, 'gifts', []):
                if isinstance(gift, SavedStarGift) and hasattr(gift, 'msg_id'):
                    current_personal.add(gift.msg_id)
                    
                    # Проверяем новый ли это подарок
                    if gift.msg_id not in self.personal_gifts_cache:
                        gift_type = "NFT" if isinstance(gift.gift, StarGiftUnique) else "Обычный"
                        gift_title = getattr(gift.gift, 'title', 'Неизвестный подарок')
                        message = (
                            f"🎁 {gift_title}\n"
                            f"💎 Тип: {gift_type}\n"
                            f"✅ Добавлен в вашу коллекцию"
                        )
                        await self._send_notification(
                            "Новый личный подарок",
                            message,
                            "personal"
                        )

            # Обновляем кэш
            self.personal_gifts_cache = current_personal
            self._save_cache()

        except Exception as e:
            logger.error(f"Error checking personal gifts: {e}")

    async def _monitoring_loop(self):
        """Основной цикл мониторинга"""
        while self.is_running:
            try:
                logger.info("Starting monitoring cycle...")
                
                # Выполняем все проверки
                await asyncio.gather(
                    self._check_price_changes(),
                    self._check_new_gifts(),
                    self._check_personal_gifts(),
                    return_exceptions=True
                )
                
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
        if self.config["track_price_changes"]:
            enabled_trackers.append("💰 Цены")
        if self.config["track_new_gifts"]:
            enabled_trackers.append("🎁 Новые подарки")
        if self.config["track_personal_gifts"]:
            enabled_trackers.append("🎯 Личные подарки")
        
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
            f"💰 Отслеживать цены: {'✅' if self.config['track_price_changes'] else '❌'}\n"
            f"🎁 Новые подарки: {'✅' if self.config['track_new_gifts'] else '❌'}\n"
            f"🎯 Личные подарки: {'✅' if self.config['track_personal_gifts'] else '❌'}\n"
            f"📊 Мин. изменение цены: {self.config['min_price_change_percent']}%\n"
            f"📢 Канал уведомлений: {self.config['notify_channel'] or 'Текущий чат'}"
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
            f"💸 Изменения цен: {self.notification_stats.get('price', 0)}",
            f"🎁 Новые подарки: {self.notification_stats.get('new', 0)}",
            f"🎯 Личные подарки: {self.notification_stats.get('personal', 0)}",
            f"ℹ️ Прочие: {self.notification_stats.get('info', 0)}",
            f"📅 Всего сегодня: {sum(self.notification_stats.values())}"
        ])
        
        await utils.answer(message, self.strings("stats").format(stats_text))

    @loader.command(
        en_doc="Clear notification cache",
        ru_doc="Очистить кэш уведомлений"
    )
    async def giftnotifyclear(self, message):
        """Очистить кэш уведомлений"""
        self.gift_cache.clear()
        self.personal_gifts_cache.clear()
        self.price_history.clear()
        self._save_cache()
        
        await utils.answer(message, "✅ Кэш уведомлений очищен")

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
