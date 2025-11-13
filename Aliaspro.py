__version__ = (1, 0, 2)

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
            
            # Разделяем команды и значение
            command_parts = rest.split(" ", 1)
            commands_str = command_parts[0]
            value = command_parts[1] if len(command_parts) > 1 else ""
            
            # Разделяем команды по запятой
            command_list = [cmd.strip() for cmd in commands_str.split(",")]
            
            # Отладочная информация
            await utils.answer(message, f"🔍 Отладка:\nНазвание: {name}\nКоманды: {command_list}\nЗначение: {value}")
            
            self.aliases[name] = {
                "commands": command_list, 
                "value": value.strip()
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
            text += f"  Тип commands: {type(commands)}\n"
            text += f"  Команды: {commands}\n"
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
                
                # Отладочное сообщение
                debug_msg = await self.client.send_message(
                    message.peer_id,
                    f"🔍 Выполняю алиас '{alias}': {len(data['commands'])} команд"
                )
                
                # Удаляем оригинальное сообщение
                await message.delete()
                
                # Отправляем КАЖДУЮ команду отдельным сообщением
                for i, command in enumerate(data["commands"]):
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
                
                # Удаляем отладочное сообщение
                await debug_msg.delete()
                break
