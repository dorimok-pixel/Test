__version__ = (1, 0, 1)

# meta developer: @mofkomodules 
# name: AliasPro

from herokutl.types import Message
from .. import loader, utils
import asyncio

@loader.tds
class AliasProMod(loader.Module):
    """Модуль для создания алиаса сразу для нескольких команд. 
Применение:
.addaliasfor поиск limoka, fheta, hetsu
.поиск ChatModule - Найдёт ChatModule по трём поисковым командам."""
    
    strings = {"name": "AliasPro"}

    def __init__(self):
        self.aliases = {}

    async def client_ready(self, client, db):
        self.client = client
        self._db = db
        self.aliases = self._db.get("AliasPro", "aliases", {})

    def save_aliases(self):
        self._db.set("AliasPro", "aliases", self.aliases)

    @loader.command(
        ru_doc="<название> <команды через запятую> [значение] - Добавить алиас для команд."
    )
    async def addaliasfor(self, message: Message):
        args = utils.get_args_raw(message)
        if not args:
            return await utils.answer(message, "<emoji document_id=6012681561286122335>🤤</emoji> Чот не то, делай так: <название> <команды через запятую> [значение]")
        
        try:
            # Разделяем на название и остальное
            parts = args.split(" ", 1)
            if len(parts) < 2:
                await utils.answer(message, "<emoji document_id=6012681561286122335>🤤</emoji> Мало аргументов")
                return
                
            name = parts[0]
            rest = parts[1]
            
            # Разделяем команды и значение
            if " " in rest:
                commands_part, value = rest.split(" ", 1)
            else:
                commands_part = rest
                value = ""
                
            command_list = [cmd.strip() for cmd in commands_part.split(",") if cmd.strip()]
            
            self.aliases[name] = {"commands": command_list, "value": value.strip()}
            self.save_aliases()
            
            await utils.answer(message, f"<emoji document_id=6012543830274873468>☺️</emoji> Алиас <code>{name}</code> готов!")
            
        except Exception:
            await utils.answer(message, "<emoji document_id=6012681561286122335>🤤</emoji> Хрень сморозил")

    @loader.command(
        ru_doc="<название> - Удалить алиас"
    )
    async def dalias(self, message: Message):
        args = utils.get_args_raw(message)
        if not args:
            return await utils.answer(message, "<emoji document_id=6012681561286122335>🤤</emoji> Укажите название алиаса")
        
        if args in self.aliases:
            del self.aliases[args]
            self.save_aliases()
            await utils.answer(message, f"<emoji document_id=6012543830274873468>☺️</emoji> Алиас <code>{args}</code> убран")
        else:
            await utils.answer(message, "<emoji document_id=6012681561286122335>🤤</emoji> Хрень сморозил")

    @loader.watcher()
    async def watcher(self, message: Message):
        if not message.out or not message.text:
            return
            
        text = message.text
        prefix = self.get_prefix()
        
        for alias, data in self.aliases.items():
            alias_with_prefix = prefix + alias
            
            if text.startswith(alias_with_prefix):
                search_query = text[len(alias_with_prefix):].strip()
                
                # Удаляем оригинальное сообщение
                await message.delete()
                
                # Отправляем КАЖДУЮ команду ОТДЕЛЬНЫМ сообщением
                for command in data["commands"]:
                    clean_command = command.strip()
                    
                    # Формируем команду для КАЖДОЙ отдельно
                    if data["value"]:
                        full_command = f"{prefix}{clean_command} {data['value']} {search_query}"
                    else:
                        full_command = f"{prefix}{clean_command} {search_query}"
                    
                    # Отправляем отдельное сообщение для каждой команды
                    await self.client.send_message(
                        message.peer_id,
                        full_command.strip()
                    )
                    
                    # Небольшая задержка между сообщениями
                    await asyncio.sleep(0.3)
                
                break
