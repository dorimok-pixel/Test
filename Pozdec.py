# meta developer: @mofkomodules
# name: RegularM
# requires: aiohttp

import asyncio
import re
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union
from enum import Enum

from .. import loader, utils
from ..inline.types import InlineCall


class PeriodType(Enum):
    DAILY = "d"
    WEEKLY = "w"
    MONTHLY = "m"
    YEARLY = "y"


@loader.tds
class RegularMessagesMod(loader.Module):
    """Модуль для создания регулярных сообщений с гибкой настройкой"""

    strings = {
        "name": "RegularM",
        "config_help": (
            "📅 <b>Регулярные сообщения</b>\n\n"
            "Создавайте сообщения, которые будут отправляться автоматически "
            "в указанное время и период.\n\n"
            "Использование:\n"
            "<code>.regmes день, время, дата_начала, сообщение</code>\n\n"
            "<b>Периоды:</b>\n"
            "• д - каждый день\n"
            "• н - еженедельно\n"
            "• м - ежемесячно\n"
            "• г - ежегодно\n"
            "• день недели (Понедельник, Вторник...)\n"
            "• месяц (Январь, Февраль...)\n\n"
            "<b>Примеры:</b>\n"
            "<code>.regmes Суббота, 20:15, 27.12, Собрание!</code>\n"
            "<code>.regmes д, 09:00, 01.01, Доброе утро!</code>\n"
            "<code>.regmes н, 18:30, 15.01, Отчет за неделю</code>"
        ),
        "success_add": (
            "✅ <b>Регулярное сообщение добавлено</b>\n\n"
            "ID: <code>{id}</code>\n"
            "Период: {period}\n"
            "Время: {time}\n"
            "Начало: {start_date}\n"
            "Чат: {chat_name}\n"
            "Сообщение: {message}"
        ),
        "error_args": "❌ <b>Неверные аргументы</b>\nИспользуйте: <code>.regmes период, время, дата_начала, сообщение</code>",
        "error_time": "❌ <b>Неверный формат времени</b>\nИспользуйте ЧЧ:ММ (24-часовой формат)",
        "error_date": "❌ <b>Неверный формат даты</b>\nИспользуйте ДД.ММ",
        "error_period": "❌ <b>Неверный период</b>\nДоступно: д, н, м, г, дни недели, месяцы",
        "error_chat": "❌ <b>Не удалось определить чат</b>",
        "no_messages": "📭 <b>Нет регулярных сообщений</b>\nИспользуйте <code>.regmes</code> для создания",
        "deleted": "🗑 <b>Регулярное сообщение удалено</b>\nID: <code>{id}</code>",
        "toggled": "🔄 <b>Статус изменен</b>\nID: <code>{id}</code>\nСтатус: {status}",
        "edited": "✏️ <b>Сообщение обновлено</b>\nID: <code>{id}</code>",
        "sending": "⏳ <b>Отправка сообщения...</b>",
        "sent": "✅ <b>Сообщение отправлено</b>\nID: <code>{id}</code>",
        "error_send": "❌ <b>Ошибка отправки</b>\nID: <code>{id}</code>\nПричина: {error}",
    }

    strings_ru = strings

    DAYS_OF_WEEK = {
        "понедельник": 0, "вторник": 1, "среда": 2, 
        "четверг": 3, "пятница": 4, "суббота": 5, "воскресенье": 6,
        "пн": 0, "вт": 1, "ср": 2, "чт": 3, "пт": 4, "сб": 5, "вс": 6
    }

    MONTHS = {
        "январь": 1, "февраль": 2, "март": 3, "апрель": 4,
        "май": 5, "июнь": 6, "июль": 7, "август": 8,
        "сентябрь": 9, "октябрь": 10, "ноябрь": 11, "декабрь": 12
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "check_interval",
                60,
                "Интервал проверки сообщений (в секундах)",
                validator=loader.validators.Integer(minimum=30)
            ),
            loader.ConfigValue(
                "max_messages_per_minute",
                5,
                "Максимальное количество сообщений в минуту",
                validator=loader.validators.Integer(minimum=1, maximum=30)
            ),
            loader.ConfigValue(
                "retry_delay",
                300,
                "Задержка при ошибке отправки (в секундах)",
                validator=loader.validators.Integer(minimum=60)
            ),
        )
        self.messages: Dict[int, dict] = {}
        self.task: Optional[asyncio.Task] = None
        self.last_send_time = 0
        self.send_queue = asyncio.Queue()

    async def client_ready(self, client, db):
        self.client = client
        self.db = db
        self._load_messages()
        
        # Запускаем фоновую задачу для проверки сообщений
        self.task = asyncio.create_task(self._check_messages_loop())

    async def on_unload(self):
        """Остановка фоновой задачи при выгрузке модуля"""
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

    def _load_messages(self):
        """Загрузка сообщений из базы данных"""
        messages = self.db.get(self.strings["name"], "messages", {})
        # Конвертируем ключи строк в int
        self.messages = {int(k): v for k, v in messages.items()}
        
        # Восстанавливаем пропущенные отправления
        asyncio.create_task(self._restore_missed_messages())

    def _save_messages(self):
        """Сохранение сообщений в базу данных"""
        self.db.set(self.strings["name"], "messages", self.messages)

    async def _restore_missed_messages(self):
        """Восстановление пропущенных отправлений при запуске"""
        current_time = time.time()
        for msg_id, msg in list(self.messages.items()):
            if not msg.get("enabled", True):
                continue
                
            next_time = msg.get("next_send", 0)
            if next_time and next_time < current_time:
                # Пересчитываем следующее время отправки
                await self._calculate_next_send(msg)
                self._save_messages()

    def _parse_period(self, period_str: str) -> dict:
        """Парсинг периода из строки"""
        period_str = period_str.strip().lower()
        
        # Проверка простых периодов
        if period_str == "д":
            return {"type": "daily"}
        elif period_str == "н":
            return {"type": "weekly"}
        elif period_str == "м":
            return {"type": "monthly"}
        elif period_str == "г":
            return {"type": "yearly"}
        
        # Проверка дней недели
        if period_str in self.DAYS_OF_WEEK:
            return {"type": "weekly_day", "day": self.DAYS_OF_WEEK[period_str]}
        
        # Проверка месяцев
        if period_str in self.MONTHS:
            return {"type": "monthly_day", "month": self.MONTHS[period_str]}
        
        # Проверка нескольких недель (например, "2 недели")
        match = re.match(r"(\d+)\s*недел[яьи]?", period_str)
        if match:
            weeks = int(match.group(1))
            if 1 <= weeks <= 52:
                return {"type": "weeks", "count": weeks}
        
        raise ValueError("Неверный период")

    def _parse_time(self, time_str: str) -> tuple:
        """Парсинг времени из строки"""
        if not re.match(r"^([01]?[0-9]|2[0-3]):([0-5][0-9])$", time_str):
            raise ValueError("Неверный формат времени")
        
        hours, minutes = map(int, time_str.split(":"))
        return hours, minutes

    def _parse_date(self, date_str: str) -> tuple:
        """Парсинг даты из строки"""
        if not re.match(r"^([0-2]?[0-9]|3[01])\.(0?[1-9]|1[0-2])$", date_str):
            raise ValueError("Неверный формат даты")
        
        day, month = map(int, date_str.split("."))
        
        # Проверка корректности даты
        current_year = datetime.now().year
        try:
            datetime(current_year, month, day)
        except ValueError:
            raise ValueError("Неверная дата")
        
        return day, month

    async def _calculate_next_send(self, msg: dict) -> float:
        """Вычисление следующего времени отправки"""
        now = datetime.now()
        hours, minutes = msg["time"]
        day, month = msg["start_date"]
        
        period = msg["period"]
        period_type = period["type"]
        
        # Создаем базовую дату
        if period_type in ["yearly", "monthly_day"]:
            base_date = datetime(now.year, month, day, hours, minutes)
        else:
            base_date = datetime(now.year, now.month, now.day, hours, minutes)
        
        # Если базовое время уже прошло сегодня, добавляем день
        if base_date < now:
            base_date += timedelta(days=1)
        
        if period_type == "daily":
            next_date = base_date
            
        elif period_type == "weekly":
            # Следующий такой же день недели
            days_ahead = (base_date.weekday() - now.weekday()) % 7
            if days_ahead == 0 and base_date <= now:
                days_ahead = 7
            next_date = now + timedelta(days=days_ahead)
            next_date = next_date.replace(hour=hours, minute=minutes, second=0)
            
        elif period_type == "weekly_day":
            # Конкретный день недели
            target_day = period["day"]
            days_ahead = (target_day - now.weekday()) % 7
            if days_ahead == 0 and base_date <= now:
                days_ahead = 7
            next_date = now + timedelta(days=days_ahead)
            next_date = next_date.replace(hour=hours, minute=minutes, second=0)
            
        elif period_type == "monthly":
            # То же число следующего месяца
            next_date = base_date
            while next_date <= now:
                if next_date.month == 12:
                    next_date = next_date.replace(year=next_date.year + 1, month=1)
                else:
                    next_date = next_date.replace(month=next_date.month + 1)
                    
        elif period_type == "monthly_day":
            # Конкретный месяц и число
            target_month = period["month"]
            next_date = datetime(now.year, target_month, day, hours, minutes)
            if next_date < now:
                next_date = next_date.replace(year=now.year + 1)
                
        elif period_type == "yearly":
            # То же число и месяц следующего года
            next_date = base_date
            if next_date < now:
                next_date = next_date.replace(year=now.year + 1)
                
        elif period_type == "weeks":
            # Несколько недель
            weeks = period["count"]
            next_date = now + timedelta(weeks=weeks)
            next_date = next_date.replace(hour=hours, minute=minutes, second=0)
            
        else:
            next_date = base_date
        
        return next_date.timestamp()

    async def _send_message(self, msg_id: int):
        """Отправка конкретного сообщения"""
        if msg_id not in self.messages:
            return
            
        msg = self.messages[msg_id]
        if not msg.get("enabled", True):
            return
        
        try:
            chat = await self.client.get_entity(msg["chat_id"])
            
            # Отправка сообщения
            if msg.get("is_media", False):
                await self.client.send_file(
                    chat,
                    msg["message"],
                    caption=msg.get("caption", "")
                )
            else:
                await self.client.send_message(
                    chat,
                    msg["message"],
                    parse_mode="HTML"
                )
            
            # Обновляем время следующей отправки
            msg["last_sent"] = time.time()
            msg["next_send"] = await self._calculate_next_send(msg)
            msg["error_count"] = 0
            
            self._save_messages()
            
        except Exception as e:
            # Увеличиваем счетчик ошибок
            msg["error_count"] = msg.get("error_count", 0) + 1
            
            # Если много ошибок - отключаем сообщение
            if msg["error_count"] >= 5:
                msg["enabled"] = False
            
            self._save_messages()
            raise e

    async def _check_messages_loop(self):
        """Фоновая проверка сообщений для отправки"""
        while True:
            try:
                current_time = time.time()
                messages_to_send = []
                
                # Проверяем все сообщения
                for msg_id, msg in list(self.messages.items()):
                    if not msg.get("enabled", True):
                        continue
                        
                    next_send = msg.get("next_send", 0)
                    if next_send and next_send <= current_time:
                        messages_to_send.append(msg_id)
                
                # Отправляем сообщения с ограничением скорости
                for msg_id in messages_to_send:
                    # Проверяем лимит сообщений в минуту
                    time_since_last = current_time - self.last_send_time
                    if time_since_last < 60 / self.config["max_messages_per_minute"]:
                        await asyncio.sleep(60 / self.config["max_messages_per_minute"] - time_since_last)
                    
                    try:
                        await self._send_message(msg_id)
                        self.last_send_time = time.time()
                    except Exception as e:
                        logger.error(f"Ошибка отправки сообщения {msg_id}: {e}")
                        await asyncio.sleep(self.config["retry_delay"])
                
                await asyncio.sleep(self.config["check_interval"])
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ошибка в проверке сообщений: {e}")
                await asyncio.sleep(60)

    @loader.command(ru_doc="Создать регулярное сообщение")
    async def regmes(self, message):
        """Создание регулярного сообщения
        
        Использование:
        .regmes период, время, дата_начала, сообщение
        
        Примеры:
        .regmes Суббота, 20:15, 27.12, Собрание!
        .regmes д, 09:00, 01.01, Доброе утро!
        """
        args = utils.get_args_raw(message)
        
        if not args:
            await utils.answer(message, self.strings["config_help"])
            return
        
        try:
            # Разделяем аргументы
            parts = [p.strip() for p in args.split(",", 3)]
            if len(parts) < 4:
                raise ValueError("Недостаточно аргументов")
            
            period_str, time_str, date_str, message_text = parts
            
            # Проверяем реплай для медиа
            is_media = False
            reply = await message.get_reply_message()
            if reply and reply.media:
                is_media = True
                message_text = reply
            
            # Парсим параметры
            period = self._parse_period(period_str)
            time_tuple = self._parse_time(time_str)
            date_tuple = self._parse_date(date_str)
            
            # Получаем информацию о чате
            chat = await message.get_chat()
            chat_id = utils.get_chat_id(message)
            chat_name = getattr(chat, "title", getattr(chat, "first_name", str(chat_id)))
            
            # Создаем ID для сообщения
            msg_id = int(time.time() * 1000)
            
            # Создаем объект сообщения
            msg_data = {
                "id": msg_id,
                "chat_id": chat_id,
                "chat_name": chat_name,
                "period": period,
                "time": time_tuple,
                "start_date": date_tuple,
                "message": message_text if not is_media else None,
                "is_media": is_media,
                "enabled": True,
                "created": time.time(),
                "last_sent": 0,
                "error_count": 0,
                "next_send": 0
            }
            
            if is_media:
                # Сохраняем медиа
                msg_data["media"] = await self.client.download_media(message_text, bytes)
                msg_data["caption"] = message_text.text or ""
            
            # Вычисляем время первой отправки
            msg_data["next_send"] = await self._calculate_next_send(msg_data)
            
            # Сохраняем сообщение
            self.messages[msg_id] = msg_data
            self._save_messages()
            
            # Отправляем подтверждение
            response = self.strings["success_add"].format(
                id=msg_id,
                period=period_str,
                time=time_str,
                start_date=date_str,
                chat_name=chat_name,
                message=message_text[:50] + "..." if isinstance(message_text, str) and len(message_text) > 50 
                      else (str(message_text)[:50] + "..." if not is_media else "Медиа-сообщение")
            )
            
            await utils.answer(message, response)
            
        except ValueError as e:
            error_msg = str(e)
            if "время" in error_msg:
                await utils.answer(message, self.strings["error_time"])
            elif "дата" in error_msg:
                await utils.answer(message, self.strings["error_date"])
            elif "период" in error_msg:
                await utils.answer(message, self.strings["error_period"])
            else:
                await utils.answer(message, self.strings["error_args"])
        except Exception as e:
            logger.exception("Ошибка создания регулярного сообщения")
            await utils.answer(message, f"❌ Ошибка: {str(e)}")

    @loader.command(ru_doc="Конфигурация регулярных сообщений")
    async def rmcfg(self, message):
        """Открытие конфигурации регулярных сообщений"""
        await self._show_main_menu(message)

    async def _show_main_menu(self, message=None, call=None):
        """Показать главное меню"""
        if not self.messages:
            text = self.strings["no_messages"]
            buttons = [
                [{"text": "➕ Создать", "callback": self._create_new}],
                [{"text": "❌ Закрыть", "action": "close"}]
            ]
        else:
            text = "📅 <b>Регулярные сообщения</b>\n\nВыберите сообщение для редактирования:"
            buttons = []
            
            for msg_id, msg in list(self.messages.items()):
                status = "✅" if msg.get("enabled", True) else "❌"
                period_map = {
                    "daily": "Ежедневно",
                    "weekly": "Еженедельно",
                    "monthly": "Ежемесячно",
                    "yearly": "Ежегодно",
                    "weekly_day": f"По {list(self.DAYS_OF_WEEK.keys())[msg['period'].get('day', 0)]}",
                    "monthly_day": f"Каждый {list(self.MONTHS.keys())[msg['period'].get('month', 1)-1]}",
                    "weeks": f"Каждые {msg['period'].get('count', 1)} недель"
                }
                
                period_text = period_map.get(msg["period"]["type"], "Неизвестно")
                time_str = f"{msg['time'][0]:02d}:{msg['time'][1]:02d}"
                
                btn_text = f"{status} {period_text} {time_str}"
                buttons.append([{
                    "text": btn_text,
                    "callback": self._show_message_menu,
                    "args": (msg_id,)
                }])
            
            buttons.append([{"text": "➕ Создать", "callback": self._create_new}])
            buttons.append([{"text": "❌ Закрыть", "action": "close"}])
        
        if call:
            await call.edit(text, reply_markup=buttons)
        else:
            await self.inline.form(text, message, reply_markup=buttons)

    async def _create_new(self, call):
        """Создание нового сообщения через инлайн"""
        await call.edit(
            "📝 <b>Создание нового регулярного сообщения</b>\n\n"
            "Используйте команду:\n"
            "<code>.regmes период, время, дата, сообщение</code>\n\n"
            "<b>Пример:</b>\n"
            "<code>.regmes Суббота, 20:15, 27.12, Собрание!</code>",
            reply_markup=[
                [{"text": "🔙 Назад", "callback": self._show_main_menu}],
                [{"text": "❌ Закрыть", "action": "close"}]
            ]
        )

    async def _show_message_menu(self, call, msg_id):
        """Показать меню конкретного сообщения"""
        if msg_id not in self.messages:
            await call.answer("Сообщение не найдено")
            await self._show_main_menu(call=call)
            return
        
        msg = self.messages[msg_id]
        
        # Форматируем информацию о сообщении
        status = "✅ Включено" if msg.get("enabled", True) else "❌ Выключено"
        time_str = f"{msg['time'][0]:02d}:{msg['time'][1]:02d}"
        date_str = f"{msg['start_date'][0]:02d}.{msg['start_date'][1]:02d}"
        
        period_map = {
            "daily": "Ежедневно",
            "weekly": "Еженедельно",
            "monthly": "Ежемесячно",
            "yearly": "Ежегодно",
            "weekly_day": f"По {list(self.DAYS_OF_WEEK.keys())[msg['period'].get('day', 0)]}",
            "monthly_day": f"Каждый {list(self.MONTHS.keys())[msg['period'].get('month', 1)-1]}",
            "weeks": f"Каждые {msg['period'].get('count', 1)} недель"
        }
        
        period_text = period_map.get(msg["period"]["type"], "Неизвестно")
        
        next_send_time = msg.get("next_send", 0)
        if next_send_time:
            next_send = datetime.fromtimestamp(next_send_time)
            next_str = next_send.strftime("%d.%m.%Y %H:%M")
        else:
            next_str = "Не рассчитано"
        
        text = (
            f"📝 <b>Регулярное сообщение ID: {msg_id}</b>\n\n"
            f"<b>Статус:</b> {status}\n"
            f"<b>Период:</b> {period_text}\n"
            f"<b>Время:</b> {time_str}\n"
            f"<b>Начало:</b> {date_str}\n"
            f"<b>Следующая отправка:</b> {next_str}\n"
            f"<b>Чат:</b> {msg.get('chat_name', 'Неизвестно')}\n\n"
            f"<b>Сообщение:</b>\n"
        )
        
        if msg.get("is_media", False):
            text += "📎 Медиа-сообщение"
            if msg.get("caption"):
                text += f"\n{msg['caption'][:100]}..."
        else:
            message_preview = str(msg.get("message", ""))[:100]
            text += message_preview
            if len(str(msg.get("message", ""))) > 100:
                text += "..."
        
        buttons = [
            [
                {"text": "🔄 Вкл/Выкл", "callback": self._toggle_message, "args": (msg_id,)},
                {"text": "✏️ Изменить", "callback": self._edit_message_menu, "args": (msg_id,)}
            ],
            [
                {"text": "⏰ Тест отправки", "callback": self._test_send, "args": (msg_id,)},
                {"text": "🗑 Удалить", "callback": self._delete_confirm, "args": (msg_id,)}
            ],
            [{"text": "🔙 Назад", "callback": self._show_main_menu}]
        ]
        
        await call.edit(text, reply_markup=buttons)

    async def _toggle_message(self, call, msg_id):
        """Включить/выключить сообщение"""
        if msg_id in self.messages:
            msg = self.messages[msg_id]
            msg["enabled"] = not msg.get("enabled", True)
            self._save_messages()
            
            status = "✅ Включено" if msg["enabled"] else "❌ Выключено"
            await call.answer(f"Статус изменен: {status}")
            await self._show_message_menu(call, msg_id)

    async def _edit_message_menu(self, call, msg_id):
        """Меню редактирования сообщения"""
        if msg_id not in self.messages:
            await call.answer("Сообщение не найдено")
            return
        
        text = "✏️ <b>Что вы хотите изменить?</b>"
        
        buttons = [
            [
                {"text": "📅 Период", "callback": self._edit_period, "args": (msg_id,)},
                {"text": "⏰ Время", "callback": self._edit_time, "args": (msg_id,)}
            ],
            [
                {"text": "📆 Дата начала", "callback": self._edit_date, "args": (msg_id,)},
                {"text": "💬 Сообщение", "callback": self._edit_text, "args": (msg_id,)}
            ],
            [{"text": "🔙 Назад", "callback": self._show_message_menu, "args": (msg_id,)}]
        ]
        
        await call.edit(text, reply_markup=buttons)

    async def _edit_period(self, call, msg_id):
        """Изменение периода"""
        await call.edit(
            "📅 <b>Введите новый период:</b>\n\n"
            "Доступные варианты:\n"
            "• д - каждый день\n"
            "• н - еженедельно\n"
            "• м - ежемесячно\n"
            "• г - ежегодно\n"
            "• Дни недели (Понедельник, Вторник...)\n"
            "• Месяцы (Январь, Февраль...)\n"
            "• Несколько недель (2 недели, 3 недели...)",
            reply_markup=[
                [{"text": "❌ Отмена", "callback": self._edit_message_menu, "args": (msg_id,)}]
            ]
        )
        
        # Здесь должна быть логика ввода, но в рамках инлайна сложно
        # В реальном модуле нужно использовать инлайн с вводом текста

    async def _edit_time(self, call, msg_id):
        """Изменение времени"""
        await call.edit(
            "⏰ <b>Введите новое время в формате ЧЧ:ММ</b>\n\n"
            "Пример: 14:30, 09:00, 23:45",
            reply_markup=[
                [{"text": "❌ Отмена", "callback": self._edit_message_menu, "args": (msg_id,)}]
            ]
        )

    async def _edit_date(self, call, msg_id):
        """Изменение даты начала"""
        await call.edit(
            "📆 <b>Введите новую дату начала в формате ДД.ММ</b>\n\n"
            "Пример: 27.12, 01.01, 15.06",
            reply_markup=[
                [{"text": "❌ Отмена", "callback": self._edit_message_menu, "args": (msg_id,)}]
            ]
        )

    async def _edit_text(self, call, msg_id):
        """Изменение текста сообщения"""
        await call.edit(
            "💬 <b>Введите новый текст сообщения</b>\n\n"
            "Поддерживается HTML разметка и эмодзи",
            reply_markup=[
                [{"text": "❌ Отмена", "callback": self._edit_message_menu, "args": (msg_id,)}]
            ]
        )

    async def _test_send(self, call, msg_id):
        """Тестовая отправка сообщения"""
        try:
            await self._send_message(msg_id)
            await call.answer("✅ Сообщение отправлено")
        except Exception as e:
            await call.answer(f"❌ Ошибка: {str(e)}")

    async def _delete_confirm(self, call, msg_id):
        """Подтверждение удаления"""
        await call.edit(
            "🗑 <b>Вы уверены, что хотите удалить это регулярное сообщение?</b>\n\n"
            "Это действие невозможно отменить.",
            reply_markup=[
                [
                    {"text": "✅ Да, удалить", "callback": self._delete_message, "args": (msg_id,)},
                    {"text": "❌ Нет, отмена", "callback": self._show_message_menu, "args": (msg_id,)}
                ]
            ]
        )

    async def _delete_message(self, call, msg_id):
        """Удаление сообщения"""
        if msg_id in self.messages:
            del self.messages[msg_id]
            self._save_messages()
            await call.answer("✅ Сообщение удалено")
            await self._show_main_menu(call=call)

    @loader.command(ru_doc="Очистка всех регулярных сообщений")
    async def rmclear(self, message):
        """Очистка всех регулярных сообщений"""
        if not self.messages:
            await utils.answer(message, "📭 Нет регулярных сообщений для очистки")
            return
        
        count = len(self.messages)
        self.messages.clear()
        self._save_messages()
        
        await utils.answer(message, f"🗑 Удалено {count} регулярных сообщений")

    @loader.command(ru_doc="Статистика регулярных сообщений")
    async def rmstats(self, message):
        """Статистика регулярных сообщений"""
        if not self.messages:
            await utils.answer(message, self.strings["no_messages"])
            return
        
        enabled = sum(1 for m in self.messages.values() if m.get("enabled", True))
        disabled = len(self.messages) - enabled
        
        text = (
            f"📊 <b>Статистика регулярных сообщений</b>\n\n"
            f"<b>Всего:</b> {len(self.messages)}\n"
            f"<b>Активных:</b> {enabled}\n"
            f"<b>Отключенных:</b> {disabled}\n\n"
            f"<b>Последние 5 сообщений:</b>\n"
        )
        
        # Показываем последние 5 сообщений
        sorted_msgs = sorted(self.messages.items(), key=lambda x: x[1].get("created", 0), reverse=True)[:5]
        
        for msg_id, msg in sorted_msgs:
            status = "✅" if msg.get("enabled", True) else "❌"
            time_str = f"{msg['time'][0]:02d}:{msg['time'][1]:02d}"
            text += f"\n{status} ID{msg_id} - {time_str} - {msg.get('chat_name', 'Неизвестно')}"
        
        await utils.answer(message, text)
