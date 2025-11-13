__version__ = (1, 0, 3)

# meta developer: @mofkomodules 
# name: AliasPro

from herokutl.types import Message
from .. import loader, utils
import asyncio

@loader.tds
class AliasProMod(loader.Module):
    """Модуль для создания алиаса сразу для нескольких команд."""
    
    strings = {"name": "AliasPro"}

    def __init__(self):
        self.aliases = {}

    async def client_ready(self, client, db):
        self.client = client
        self._db = db
        self.aliases = self._db.get("AliasPro", "aliases", {})

    def save_aliases(self):
        self._db.set("AliasPro", "aliases", self.aliases)

    @loader.command()
    async def addaliasfor(self, message: Message):
        """<название> <команды через запятую> [значение] - Добавить алиас"""
        args = utils.get_args_raw(message)
        if not args:
            return await utils.answer(message, "❌ Формат: .addaliasfor название команда1,команда2,команда3 [значение]")
        
        try:
            # Разделяем название и остальное
            parts = args.split(" ", 1)
            if len(parts) < 2:
                return await utils.answer(message, "❌ Недостаточно аргументов")
                
            name = parts[0].strip()
            rest = parts[1].strip()
            
            # Находим где заканчиваются команды (последняя запятая)
            last_comma = rest.rfind(",")
            if last_comma == -1:
                return await utils.answer(message, "❌ Команды должны быть через запятую")
            
            # Команды - всё до последней запятой + следующее слово
            commands_part = rest[:last_comma + 1].strip()
            # Значение - всё после последней запятой
            value_part = rest[last_comma + 1:].strip()
            
            # Разделяем команды по запятой
            command_list = [cmd.strip() for cmd in commands_part.split(",") if cmd.strip()]
            
            # Добавляем последнюю команду из value_part (первое слово)
            if value_part:
                first_word = value_part.split(" ", 1)[0]
                command_list.append(first_word)
                # Оставшееся - это настоящее значение
                value = value_part[len(first_word):].strip() if len(value_part) > len(first_word) else ""
            else:
                value = ""
            
            await utils.answer(message, f"🔍 Отладка:\nНазвание: {name}\nКоманды: {command_list}\nЗначение: '{value}'")
            
            self.aliases[name] = {
                "commands": command_list, 
                "value": value
            }
            self.save_aliases()
            
        except Exception as e:
            await utils.answer(message, f"❌ Ошибка: {e}")

    @loader.command()
    async def addaliasfor2(self, message: Message):
        """АЛЬТЕРНАТИВНЫЙ СПОСОБ: .addaliasfor2 название команда1 команда2 команда3 :: значение"""
        args = utils.get_args_raw(message)
        if not args:
            return await utils.answer(message, "❌ Формат: .addaliasfor2 название команда1 команда2 команда3 :: значение")
        
        try:
            # Разделяем по ::
            if "::" not in args:
                return await utils.answer(message, "❌ Используйте :: для разделения команд и значения")
            
            commands_part, value = args.split("::", 1)
            commands_part = commands_part.strip()
            value = value.strip()
            
            # Разделяем название и команды
            parts = commands_part.split(" ", 1)
            if len(parts) < 2:
                return await utils.answer(message, "❌ Недостаточно аргументов")
                
            name = parts[0].strip()
            commands_str = parts[1].strip()
            
            # Команды разделены пробелами
            command_list = [cmd.strip() for cmd in commands_str.split() if cmd.strip()]
            
            await utils.answer(message, f"✅ Алиас создан:\nНазвание: {name}\nКоманды: {command_list}\nЗначение: '{value}'")
            
            self.aliases[name] = {
                "commands": command_list, 
                "value": value
            }
            self.save_aliases()
            
        except Exception as e:
            await utils.answer(message, f"❌ Ошибка: {e}")

    @loader.command()
    async def dalias(self, message: Message):
        """<название> - Удалить алиас"""
        args = utils.get_args_raw(message)
        if not args:
            return await utils.answer(message, "❌ Укажите название алиаса")
        
        if args in self.aliases:
            del self.aliases[args]
            self.save_aliases()
            await utils.answer(message, f"✅ Алиас <code>{args}</code> удален")
        else:
            await utils.answer(message, "❌ Алиас не найден")

    @loader.command()
    async def debugalias(self, message: Message):
        """Показать отладочную информацию об алиасах"""
        if not self.aliases:
            await utils.answer(message, "📝 Нет алиасов")
            return
            
        text = "🔍 <b>Отладочная информация:</b>\n\n"
        for alias, data in self.aliases.items():
            commands = data["commands"]
            value = data["value"]
            text += f"• <code>{alias}</code>\n"
            text += f"  Команды ({len(commands)}): {commands}\n"
            text += f"  Значение: '{value}'\n\n"
            
        await utils.answer(message, text)

    @loader.watcher()
    async def watcher(self, message: Message):
        if not message.out or not message.text:
            return
            
        text = message.text.strip()
        prefix = self.get_prefix()
        
        for alias, data in self.aliases.items():
            alias_with_prefix = prefix + alias
            
            if text.startswith(alias_with_prefix):
                search_query = text[len(alias_with_prefix):].strip()
                
                # Удаляем оригинальное сообщение
                await message.delete()
                
                # Отправляем КАЖДУЮ команду отдельным сообщением
                for command in data["commands"]:
                    # Формируем команду
                    if data["value"]:
                        full_command = f"{prefix}{command} {data['value']} {search_query}"
                    else:
                        full_command = f"{prefix}{command} {search_query}"
                    
                    # Отправляем отдельное сообщение
                    await self.client.send_message(
                        message.peer_id,
                        full_command.strip()
                    )
                    
                    # Задержка
                    await asyncio.sleep(0.5)
                
                break
