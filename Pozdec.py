# meta developer: @mofkomodules
# name: RegularM
# requires: aiohttp

import asyncio
import re
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import logging

from .. import loader, utils
from ..inline.types import InlineCall

logger = logging.getLogger(__name__)

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
            "<code>.regmes период, [время], дата_начала, сообщение</code>\n\n"
            "<b>Абсолютные периоды (требуют время):</b>\n"
            "• д - каждый день\n"
            "• н - еженедельно\n"
            "• м - ежемесячно\n"
            "• г - ежегодно\n"
            "• день недели (Понедельник, Вторник...)\n"
            "• месяц (Январь, Февраль...)\n"
            "• несколько недель (2 недели, 3 недели...)\n\n"
            "<b>Интервальные периоды (время не требуется):</b>\n"
            "• 2ч15м - каждые 2 часа 15 минут\n"
            "• 30м - каждые 30 минут\n"
            "• 1ч - каждый час\n"
            "• 1д - каждый день (отсчет с даты начала)\n\n"
            "<b>Примеры:</b>\n"
            "<code>.regmes Суббота, 20:15, 27.12, Собрание!</code>\n"
            "<code>.regmes д, 09:00, 01.01, Доброе утро!</code>\n"
            "<code>.regmes 2ч15м, 27.12, Напоминание!</code>\n"
            "<code>.regmes 30м, , Постоянное напоминание</code>"
        ),
        "success_add": (
            "✅ <b>Регулярное сообщение добавлено</b>\n\n"
            "ID: <code>{id}</code>\n"
            "Период: {period}\n"
            "{time_info}"
            "Начало: {start_date}\n"
            "Чат: {chat_name}\n"
            "Сообщение: {message}"
        ),
        "error_args": "❌ <b>Неверные аргументы</b>\nИспользуйте: <code>.regmes период, [время], дата_начала, сообщение</code>",
        "error_time": "❌ <b>Неверный формат времени</b>\nИспользуйте ЧЧ:ММ (24-часовой формат)",
        "error_date": "❌ <b>Неверный формат даты</b>\nИспользуйте ДД.ММ или оставьте пустым",
        "error_period": "❌ <b>Неверный период</b>",
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

    # Словари для преобразования
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

    async def client_ready(self, client, db):
        self.client = client
        self.db = db
        self._load_messages()
        self.task = asyncio.create_task(self._check_messages_loop())

    async def on_unload(self):
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

    def _load_messages(self):
        messages = self.db.get(self.strings["name"], "messages", {})
        self.messages = {int(k): v for k, v in messages.items()}
        asyncio.create_task(self._restore_missed_messages())

    def _save_messages(self):
        self.db.set(self.strings["name"], "messages", self.messages)

    async def _restore_missed_messages(self):
        current_time = time.time()
        for msg_id, msg in list(self.messages.items()):
            if not msg.get("enabled", True):
                continue
                
            next_time = msg.get("next_send", 0)
            if next_time and next_time < current_time:
                await self._calculate_next_send(msg)
                self._save_messages()

    def _parse_period(self, period_str: str) -> dict:
        """Парсинг периода из строки, поддерживает интервалы (2ч15м) и абсолютные периоды"""
        period_str = period_str.strip().lower()
        
        # Проверка на интервальный период (содержит ч, м, д с цифрами)
        if re.match(r'^\d+[чмд](\d+[чмд])*$', period_str) or re.match(r'^\d+[чмд]\s*\d+[чмд]$', period_str.replace(' ', '')):
            return self._parse_interval_period(period_str)
        
        # Простые абсолютные периоды
        if period_str == "д":
            return {"type": "daily"}
        elif period_str == "н":
            return {"type": "weekly"}
        elif period_str == "м":
            return {"type": "monthly"}
        elif period_str == "г":
            return {"type": "yearly"}
        
        # Дни недели
        if period_str in self.DAYS_OF_WEEK:
            return {"type": "weekly_day", "day": self.DAYS_OF_WEEK[period_str]}
        
        # Месяцы
        if period_str in self.MONTHS:
            return {"type": "monthly_day", "month": self.MONTHS[period_str]}
        
        # Несколько недель
        match = re.match(r'(\d+)\s*недел[яьи]?', period_str)
        if match:
            weeks = int(match.group(1))
            if 1 <= weeks <= 52:
                return {"type": "weeks", "count": weeks}
        
        raise ValueError("Неверный период")

    def _parse_interval_period(self, period_str: str) -> dict:
        """Парсинг интервального периода типа 2ч15м, 30м, 1ч, 1д"""
        period_str = period_str.replace(' ', '').lower()
        
        total_seconds = 0
        # Регулярное выражение для поиска компонентов: цифры + единица измерения
        pattern = re.compile(r'(\d+)([чмд])')
        
        for match in pattern.finditer(period_str):
            value = int(match.group(1))
            unit = match.group(2)
            
            if unit == 'д':
                total_seconds += value * 24 * 3600  # дни в секундах
            elif unit == 'ч':
                total_seconds += value * 3600  # часы в секундах
            elif unit == 'м':
                total_seconds += value * 60  # минуты в секундах
        
        if total_seconds == 0:
            raise ValueError("Неверный интервальный период")
        
        return {"type": "interval", "seconds": total_seconds}

    def _parse_time(self, time_str: str) -> Optional[Tuple[int, int]]:
        """Парсинг времени из строки, возвращает None если пусто"""
        if not time_str or time_str.strip() == '':
            return None
        
        time_str = time_str.strip()
        if not re.match(r'^([01]?[0-9]|2[0-3]):([0-5][0-9])$', time_str):
            raise ValueError("Неверный формат времени")
        
        hours, minutes = map(int, time_str.split(':'))
        return hours, minutes

    def _parse_date(self, date_str: str) -> Tuple[int, int]:
        """Парсинг даты из строки, если пусто - использует текущую дату"""
        if not date_str or date_str.strip() == '':
            now = datetime.now()
            return now.day, now.month
        
        date_str = date_str.strip()
        if not re.match(r'^([0-2]?[0-9]|3[01])\.(0?[1-9]|1[0-2])$', date_str):
            raise ValueError("Неверный формат даты")
        
        day, month = map(int, date_str.split('.'))
        
        current_year = datetime.now().year
        try:
            datetime(current_year, month, day)
        except ValueError:
            raise ValueError("Неверная дата")
        
        return day, month

    async def _calculate_next_send(self, msg: dict) -> float:
        """Вычисление следующего времени отправки для разных типов периодов"""
        now = datetime.now()
        period = msg["period"]
        period_type = period["type"]
        
        if period_type == "interval":
            # Интервальный период: прибавляем интервал к последней отправке или времени создания
            last_sent = msg.get("last_sent", 0)
            if last_sent > 0:
                # Используем время последней отправки
                next_time = last_sent + period["seconds"]
            else:
                # Первая отправка: используем дату начала + интервал
                day, month = msg["start_date"]
                current_year = now.year
                
                try:
                    start_date = datetime(current_year, month, day)
                    # Если дата в прошлом, берем следующее вхождение
                    if start_date < now:
                        if period["seconds"] >= 86400:  # Если интервал больше дня
                            # Ищем следующую дату с учетом интервала
                            while start_date < now:
                                start_date += timedelta(seconds=period["seconds"])
                        else:
                            # Для коротких интервалов начинаем с текущего времени
                            start_date = now
                    
                    next_time = start_date.timestamp()
                except ValueError:
                    # Если дата невалидна (например, 30 февраля), используем текущее время
                    next_time = now.timestamp() + period["seconds"]
            
            # Убедимся, что следующее время в будущем
            while next_time <= time.time():
                next_time += period["seconds"]
                
            return next_time
        
        else:
            # Абсолютные периоды (требуют время)
            time_tuple = msg.get("time")
            if time_tuple is None:
                # Если время не указано для абсолютного периода, используем текущее время
                hours, minutes = now.hour, now.minute
            else:
                hours, minutes = time_tuple
            
            day, month = msg["start_date"]
            
            # Базовое время с учетом даты начала
            current_year = now.year
            try:
                base_date = datetime(current_year, month, day, hours, minutes)
            except ValueError:
                # Если дата невалидна для текущего года
                base_date = datetime(current_year + 1, month, day, hours, minutes)
            
            # Если базовое время уже прошло в этом году, корректируем
            if base_date < now:
                if period_type == "yearly":
                    base_date = base_date.replace(year=current_year + 1)
                elif period_type == "monthly_day":
                    base_date = base_date.replace(year=current_year + 1)
                else:
                    # Для остальных периодов используем текущую дату как отправную точку
                    base_date = now.replace(hour=hours, minute=minutes, second=0, microsecond=0)
                    if base_date < now:
                        base_date += timedelta(days=1)
            
            # Обработка разных типов периодов
            if period_type == "daily":
                # Уже установлено на сегодня/завтра с нужным временем
                pass
                
            elif period_type == "weekly":
                # День недели такой же как в базовой дате
                pass
                
            elif period_type == "weekly_day":
                target_day = period["day"]
                days_ahead = (target_day - base_date.weekday()) % 7
                if days_ahead == 0 and base_date <= now:
                    days_ahead = 7
                base_date += timedelta(days=days_ahead)
                
            elif period_type == "monthly":
                # То же число следующего месяца
                if base_date <= now:
                    if base_date.month == 12:
                        base_date = base_date.replace(year=base_date.year + 1, month=1)
                    else:
                        base_date = base_date.replace(month=base_date.month + 1)
                        
            elif period_type == "monthly_day":
                target_month = period["month"]
                base_date = base_date.replace(month=target_month)
                if base_date < now:
                    base_date = base_date.replace(year=base_date.year + 1)
                    
            elif period_type == "yearly":
                # Уже установлено на следующий год если прошло
                pass
                
            elif period_type == "weeks":
                weeks = period["count"]
                if base_date <= now:
                    base_date += timedelta(weeks=weeks)
                    
            else:
                # По умолчанию - ежедневно
                if base_date <= now:
                    base_date += timedelta(days=1)
            
            return base_date.timestamp()

    async def _send_message(self, msg_id: int):
        if msg_id not in self.messages:
            return
            
        msg = self.messages[msg_id]
        if not msg.get("enabled", True):
            return
        
        try:
            chat = await self.client.get_entity(msg["chat_id"])
            
            # Отправка сообщения
            if msg.get("is_media", False):
                media_data = msg.get("media_data", {})
                if media_data.get("type") == "photo":
                    await self.client.send_file(
                        chat,
                        media_data["bytes"],
                        caption=msg.get("message", ""),
                        parse_mode="HTML"
                    )
                else:
                    await self.client.send_message(
                        chat,
                        msg.get("message", ""),
                        parse_mode="HTML"
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
            msg["error_count"] = msg.get("error_count", 0) + 1
            if msg["error_count"] >= 5:
                msg["enabled"] = False
                logger.error(f"Сообщение {msg_id} отключено из-за ошибок: {e}")
            
            self._save_messages()
            raise e

    async def _check_messages_loop(self):
        while True:
            try:
                current_time = time.time()
                messages_to_send = []
                
                for msg_id, msg in list(self.messages.items()):
                    if not msg.get("enabled", True):
                        continue
                        
                    next_send = msg.get("next_send", 0)
                    if next_send and next_send <= current_time:
                        messages_to_send.append(msg_id)
                
                # Отправляем с ограничением скорости
                for msg_id in messages_to_send:
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
        .regmes период, [время], дата_начала, сообщение
        
        Примеры:
        .regmes Суббота, 20:15, 27.12, Собрание!
        .regmes д, 09:00, 01.01, Доброе утро!
        .regmes 2ч15м, 27.12, Напоминание!
        .regmes 30м, , Постоянное напоминание
        """
        args = utils.get_args_raw(message)
        
        if not args:
            await utils.answer(message, self.strings["config_help"])
            return
        
        try:
            # Разделяем аргументы с учетом пустых значений
            parts = []
            current_part = []
            in_quotes = False
            
            for char in args:
                if char == '"' or char == "'":
                    in_quotes = not in_quotes
                    current_part.append(char)
                elif char == ',' and not in_quotes:
                    parts.append(''.join(current_part).strip())
                    current_part = []
                else:
                    current_part.append(char)
            
            # Добавляем последнюю часть
            if current_part:
                parts.append(''.join(current_part).strip())
            
            # Проверяем количество частей
            if len(parts) < 3 or len(parts) > 4:
                raise ValueError("Неверное количество аргументов")
            
            # Определяем тип периода и парсим аргументы
            period_str = parts[0]
            period = self._parse_period(period_str)
            
            is_interval = period["type"] == "interval"
            
            if is_interval:
                # Интервальный период: период, [дата], сообщение
                if len(parts) == 3:
                    # период, дата, сообщение
                    date_str, message_text = parts[1], parts[2]
                    time_tuple = None
                elif len(parts) == 4:
                    # период, время (игнорируется), дата, сообщение
                    time_str, date_str, message_text = parts[1], parts[2], parts[3]
                    time_tuple = self._parse_time(time_str) if time_str else None
                else:
                    raise ValueError("Неверное количество аргументов для интервального периода")
            else:
                # Абсолютный период: период, время, дата, сообщение
                if len(parts) != 4:
                    raise ValueError("Абсолютный период требует 4 аргумента")
                
                time_str, date_str, message_text = parts[1], parts[2], parts[3]
                time_tuple = self._parse_time(time_str) if time_str else None
            
            # Проверяем реплай для медиа
            is_media = False
            media_data = None
            reply = await message.get_reply_message()
            
            if reply and reply.media:
                is_media = True
                if reply.photo:
                    media_bytes = await reply.download_media(bytes)
                    media_data = {
                        "type": "photo",
                        "bytes": media_bytes
                    }
                    message_text = reply.message or message_text
                else:
                    message_text = f"📎 Медиа-сообщение: {reply.message or ''}"
            
            # Парсим дату
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
                "message": message_text,
                "is_media": is_media,
                "media_data": media_data,
                "enabled": True,
                "created": time.time(),
                "last_sent": 0,
                "error_count": 0
            }
            
            # Вычисляем время первой отправки
            msg_data["next_send"] = await self._calculate_next_send(msg_data)
            
            # Сохраняем сообщение
            self.messages[msg_id] = msg_data
            self._save_messages()
            
            # Форматируем ответ
            message_preview = message_text
            if len(message_text) > 50:
                message_preview = message_text[:50] + "..."
            
            # Форматируем период для отображения
            if period["type"] == "interval":
                seconds = period["seconds"]
                if seconds >= 86400:
                    days = seconds // 86400
                    hours = (seconds % 86400) // 3600
                    minutes = (seconds % 3600) // 60
                    period_display = f"{days}д {hours}ч {minutes}м"
                elif seconds >= 3600:
                    hours = seconds // 3600
                    minutes = (seconds % 3600) // 60
                    period_display = f"{hours}ч {minutes}м"
                else:
                    minutes = seconds // 60
                    period_display = f"{minutes}м"
            else:
                period_display = parts[0]
            
            # Форматируем информацию о времени
            if time_tuple:
                time_info = f"Время: {time_tuple[0]:02d}:{time_tuple[1]:02d}\n"
            else:
                time_info = ""
            
            response = self.strings["success_add"].format(
                id=msg_id,
                period=period_display,
                time_info=time_info,
                start_date=f"{date_tuple[0]:02d}.{date_tuple[1]:02d}" if date_tuple else "сегодня",
                chat_name=chat_name,
                message=message_preview
            )
            
            await utils.answer(message, response)
            
        except ValueError as e:
            error_msg = str(e)
            if "время" in error_msg:
                await utils.answer(message, self.strings["error_time"])
            elif "дата" in error_msg:
                await utils.answer(message, self.strings["error_date"])
            elif "период" in error_msg or "интервал" in error_msg:
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
                
                # Форматируем период для отображения
                period = msg["period"]
                period_type = period["type"]
                
                if period_type == "interval":
                    seconds = period["seconds"]
                    if seconds >= 86400:
                        days = seconds // 86400
                        hours = (seconds % 86400) // 3600
                        minutes = (seconds % 3600) // 60
                        period_text = f"{days}д{hours}ч{minutes}м"
                    elif seconds >= 3600:
                        hours = seconds // 3600
                        minutes = (seconds % 3600) // 60
                        period_text = f"{hours}ч{minutes}м"
                    else:
                        minutes = seconds // 60
                        period_text = f"{minutes}м"
                elif period_type == "daily":
                    period_text = "Ежедневно"
                elif period_type == "weekly":
                    period_text = "Еженедельно"
                elif period_type == "weekly_day":
                    day_num = period.get("day", 0)
                    day_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
                    period_text = f"По {day_names[day_num]}"
                elif period_type == "monthly":
                    period_text = "Ежемесячно"
                elif period_type == "monthly_day":
                    month_num = period.get("month", 1) - 1
                    month_names = list(self.MONTHS.keys())
                    period_text = f"Каждый {month_names[month_num][:3]}"
                elif period_type == "yearly":
                    period_text = "Ежегодно"
                elif period_type == "weeks":
                    weeks = period.get("count", 1)
                    period_text = f"Каждые {weeks} нед"
                else:
                    period_text = "Неизвестно"
                
                # Добавляем время для абсолютных периодов
                if period_type != "interval" and msg.get("time"):
                    time_str = f"{msg['time'][0]:02d}:{msg['time'][1]:02d}"
                    btn_text = f"{status} {period_text} {time_str}"
                else:
                    btn_text = f"{status} {period_text}"
                
                if len(btn_text) > 30:
                    btn_text = btn_text[:27] + "..."
                
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
        await call.edit(
            "📝 <b>Создание нового регулярного сообщения</b>\n\n"
            "Используйте команду:\n"
            "<code>.regmes период, [время], дата, сообщение</code>\n\n"
            "<b>Примеры:</b>\n"
            "<code>.regmes Суббота, 20:15, 27.12, Собрание!</code>\n"
            "<code>.regmes д, 09:00, 01.01, Доброе утро!</code>\n"
            "<code>.regmes 2ч15м, 27.12, Напоминание!</code>\n"
            "<code>.regmes 30м, , Постоянное напоминание</code>",
            reply_markup=[
                [{"text": "🔙 Назад", "callback": self._show_main_menu}],
                [{"text": "❌ Закрыть", "action": "close"}]
            ]
        )

    async def _show_message_menu(self, call, msg_id):
        if msg_id not in self.messages:
            await call.answer("Сообщение не найдено")
            await self._show_main_menu(call=call)
            return
        
        msg = self.messages[msg_id]
        
        # Форматируем информацию
        status = "✅ Включено" if msg.get("enabled", True) else "❌ Выключено"
        
        # Форматируем период
        period = msg["period"]
        period_type = period["type"]
        
        if period_type == "interval":
            seconds = period["seconds"]
            if seconds >= 86400:
                days = seconds // 86400
                hours = (seconds % 86400) // 3600
                minutes = (seconds % 3600) // 60
                period_text = f"Каждые {days}д {hours}ч {minutes}м"
            elif seconds >= 3600:
                hours = seconds // 3600
                minutes = (seconds % 3600) // 60
                period_text = f"Каждые {hours}ч {minutes}м"
            else:
                minutes = seconds // 60
                period_text = f"Каждые {minutes} минут"
        elif period_type == "daily":
            period_text = "Ежедневно"
        elif period_type == "weekly":
            period_text = "Еженедельно"
        elif period_type == "weekly_day":
            day_num = period.get("day", 0)
            day_names = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
            period_text = f"По {day_names[day_num]}"
        elif period_type == "monthly":
            period_text = "Ежемесячно"
        elif period_type == "monthly_day":
            month_num = period.get("month", 1) - 1
            month_names = list(self.MONTHS.keys())
            period_text = f"Каждый {month_names[month_num]}"
        elif period_type == "yearly":
            period_text = "Ежегодно"
        elif period_type == "weeks":
            weeks = period.get("count", 1)
            period_text = f"Каждые {weeks} недель"
        else:
            period_text = "Неизвестно"
        
        # Время для абсолютных периодов
        time_info = ""
        if period_type != "interval" and msg.get("time"):
            time_str = f"{msg['time'][0]:02d}:{msg['time'][1]:02d}"
            time_info = f"<b>Время:</b> {time_str}\n"
        
        date_str = f"{msg['start_date'][0]:02d}.{msg['start_date'][1]:02d}"
        
        # Время следующей отправки
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
            f"{time_info}"
            f"<b>Начало:</b> {date_str}\n"
            f"<b>Следующая отправка:</b> {next_str}\n"
            f"<b>Чат:</b> {msg.get('chat_name', 'Неизвестно')}\n\n"
            f"<b>Сообщение:</b>\n"
        )
        
        if msg.get("is_media", False):
            text += "📎 Медиа-сообщение\n"
        
        message_preview = str(msg.get("message", ""))[:200]
        text += message_preview
        if len(str(msg.get("message", ""))) > 200:
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
        if msg_id in self.messages:
            msg = self.messages[msg_id]
            msg["enabled"] = not msg.get("enabled", True)
            self._save_messages()
            
            status = "✅ Включено" if msg["enabled"] else "❌ Выключено"
            await call.answer(f"Статус изменен: {status}")
            await self._show_message_menu(call, msg_id)

    async def _edit_message_menu(self, call, msg_id):
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
        await call.edit(
            "📅 <b>Введите новый период:</b>\n\n"
            "<b>Абсолютные периоды (требуют время):</b>\n"
            "• д, н, м, г\n"
            "• Дни недели (Понедельник, Вторник...)\n"
            "• Месяцы (Январь, Февраль...)\n"
            "• Несколько недель (2 недели, 3 недели...)\n\n"
            "<b>Интервальные периоды (время не требуется):</b>\n"
            "• 2ч15м - каждые 2 часа 15 минут\n"
            "• 30м - каждые 30 минут\n"
            "• 1ч - каждый час\n"
            "• 1д - каждый день",
            reply_markup=[
                [{"text": "❌ Отмена", "callback": self._edit_message_menu, "args": (msg_id,)}]
            ]
        )

    async def _edit_time(self, call, msg_id):
        msg = self.messages.get(msg_id)
        if not msg:
            await call.answer("Сообщение не найдено")
            return
        
        period_type = msg["period"]["type"]
        if period_type == "interval":
            await call.answer("⚠️ Для интервальных периодов время не требуется")
            return
        
        await call.edit(
            "⏰ <b>Введите новое время в формате ЧЧ:ММ</b>\n\n"
            "Пример: 14:30, 09:00, 23:45\n\n"
            "Или оставьте пустым для текущего времени",
            reply_markup=[
                [{"text": "❌ Отмена", "callback": self._edit_message_menu, "args": (msg_id,)}]
            ]
        )

    async def _edit_date(self, call, msg_id):
        await call.edit(
            "📆 <b>Введите новую дату начала в формате ДД.ММ</b>\n\n"
            "Пример: 27.12, 01.01, 15.06\n\n"
            "Или оставьте пустым для текущей даты",
            reply_markup=[
                [{"text": "❌ Отмена", "callback": self._edit_message_menu, "args": (msg_id,)}]
            ]
        )

    async def _edit_text(self, call, msg_id):
        await call.edit(
            "💬 <b>Введите новый текст сообщения</b>\n\n"
            "Поддерживается HTML разметка и эмодзи\n\n"
            "Или ответьте реплаем на медиа-сообщение",
            reply_markup=[
                [{"text": "❌ Отмена", "callback": self._edit_message_menu, "args": (msg_id,)}]
            ]
        )

    async def _test_send(self, call, msg_id):
        try:
            await self._send_message(msg_id)
            await call.answer("✅ Сообщение отправлено")
        except Exception as e:
            await call.answer(f"❌ Ошибка: {str(e)}")

    async def _delete_confirm(self, call, msg_id):
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
        if msg_id in self.messages:
            del self.messages[msg_id]
            self._save_messages()
            await call.answer("✅ Сообщение удалено")
            await self._show_main_menu(call=call)

    @loader.command(ru_doc="Очистка всех регулярных сообщений")
    async def rmclear(self, message):
        if not self.messages:
            await utils.answer(message, "📭 Нет регулярных сообщений для очистки")
            return
        
        count = len(self.messages)
        self.messages.clear()
        self._save_messages()
        
        await utils.answer(message, f"🗑 Удалено {count} регулярных сообщений")

    @loader.command(ru_doc="Статистика регулярных сообщений")
    async def rmstats(self, message):
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
            f"<b>По типам периодов:</b>\n"
        )
        
        # Статистика по типам периодов
        type_counts = {}
        for msg in self.messages.values():
            period_type = msg["period"]["type"]
            type_counts[period_type] = type_counts.get(period_type, 0) + 1
        
        type_names = {
            "interval": "Интервальные",
            "daily": "Ежедневные",
            "weekly": "Еженедельные",
            "weekly_day": "По дням недели",
            "monthly": "Ежемесячные",
            "monthly_day": "По месяцам",
            "yearly": "Ежегодные",
            "weeks": "По несколько недель"
        }
        
        for period_type, count in type_counts.items():
            type_name = type_names.get(period_type, period_type)
            text += f"  {type_name}: {count}\n"
        
        text += f"\n<b>Последние 5 сообщений:</b>\n"
        
        sorted_msgs = sorted(self.messages.items(), key=lambda x: x[1].get("created", 0), reverse=True)[:5]
        
        for msg_id, msg in sorted_msgs:
            status = "✅" if msg.get("enabled", True) else "❌"
            period_type = msg["period"]["type"]
            
            if period_type == "interval":
                seconds = msg["period"]["seconds"]
                if seconds >= 3600:
                    period_display = f"{seconds//3600}ч"
                else:
                    period_display = f"{seconds//60}м"
            else:
                period_display = period_type[:3]
            
            text += f"\n{status} ID{msg_id} - {period_display} - {msg.get('chat_name', 'Неизвестно')}"
        
        await utils.answer(message, text)

    @loader.command(ru_doc="Принудительная проверка сообщений")
    async def rmcheck(self, message):
        if not self.messages:
            await utils.answer(message, "📭 Нет регулярных сообщений")
            return
        
        count = 0
        current_time = time.time()
        
        for msg_id, msg in list(self.messages.items()):
            if not msg.get("enabled", True):
                continue
                
            next_send = msg.get("next_send", 0)
            if next_send and next_send <= current_time:
                count += 1
                
        if count == 0:
            await utils.answer(message, "⏳ Нет сообщений для отправки")
        else:
            await utils.answer(message, f"🔍 Найдено {count} сообщений для отправки")
            # Запускаем проверку
            if self.task:
                self.task.cancel()
            self.task = asyncio.create_task(self._check_messages_loop())

    @loader.command(ru_doc="Пересчитать время отправки для всех сообщений")
    async def rmrecalc(self, message):
        if not self.messages:
            await utils.answer(message, "📭 Нет регулярных сообщений")
            return
        
        count = 0
        for msg_id, msg in list(self.messages.items()):
            try:
                msg["next_send"] = await self._calculate_next_send(msg)
                count += 1
            except Exception as e:
                logger.error(f"Ошибка пересчета сообщения {msg_id}: {e}")
        
        self._save_messages()
        await utils.answer(message, f"🔄 Пересчитано {count} сообщений")
