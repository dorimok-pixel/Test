# meta developer: @mofkomodules
# name: FontChanger
__version__ = (1, 0, 0)

import asyncio
import logging

from telethon.tl.types import Message

from .. import loader, utils

logger = logging.getLogger(__name__)


@loader.tds
class FontChanger(loader.Module):
    strings = {
        "name": "FontChanger",
        "enabled": "✅ FontChanger включен",
        "disabled": "❌ FontChanger выключен",
        "already_enabled": "ℹ️ FontChanger уже включен",
        "already_disabled": "ℹ️ FontChanger уже выключен",
        "font_changed": "✅ Шрифт изменен на: {}",
        "available_fonts": "📝 Доступные шрифты: {}",
        "current_font": "📋 Текущий шрифт: {}",
    }

    strings_ru = {
        "enabled": "✅ FontChanger включен",
        "disabled": "❌ FontChanger выключен",
        "already_enabled": "ℹ️ FontChanger уже включен",
        "already_disabled": "ℹ️ FontChanger уже выключен",
        "font_changed": "✅ Шрифт изменен на: {}",
        "available_fonts": "📝 Доступные шрифты: {}",
        "current_font": "📋 Текущий шрифт: {}",
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "font_on",
                True,
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "current_font",
                "greek",
                validator=loader.validators.Choice(["greek", "mathematical", "monospace", "circled", "squared", "fraktur"]),
            ),
        )
        
        self._font_maps = {}
        self._generate_font_maps()
        
        self._cyrillic_map = {
            'А': 'Α', 'В': 'Β', 'Е': 'Ε', 'З': 'Ζ', 'И': 'Ι', 'К': 'Κ',
            'М': 'Μ', 'Н': 'Ν', 'О': 'Ο', 'Р': 'Ρ', 'С': 'Σ', 'Т': 'Τ',
            'У': 'Υ', 'Х': 'Χ', 'Ь': 'ʹ',
            'а': 'α', 'в': 'β', 'е': 'ε', 'з': 'ζ', 'и': 'ι', 'к': 'κ',
            'м': 'μ', 'н': 'ν', 'о': 'ο', 'р': 'ρ', 'с': 'σ', 'т': 'τ',
            'у': 'υ', 'х': 'χ', 'ь': 'ʹ',
        }

    def _generate_font_maps(self):
        greek_map = {}
        for i in range(0x0391, 0x03AA):
            latin_char = chr(ord('A') + (i - 0x0391))
            if latin_char <= 'Z':
                greek_map[latin_char] = chr(i)
        for i in range(0x03B1, 0x03CA):
            latin_char = chr(ord('a') + (i - 0x03B1))
            if latin_char <= 'z':
                greek_map[latin_char] = chr(i)
        self._font_maps["greek"] = greek_map
        
        math_map = {}
        for i in range(0x1D400, 0x1D41A):
            latin_char = chr(ord('A') + (i - 0x1D400))
            math_map[latin_char] = chr(i)
        for i in range(0x1D41A, 0x1D434):
            latin_char = chr(ord('a') + (i - 0x1D41A))
            math_map[latin_char] = chr(i)
        for i in range(0x1D7CE, 0x1D7D8):
            digit = chr(ord('0') + (i - 0x1D7CE))
            math_map[digit] = chr(i)
        self._font_maps["mathematical"] = math_map
        
        mono_map = {}
        for i in range(0x1D670, 0x1D68A):
            latin_char = chr(ord('A') + (i - 0x1D670))
            mono_map[latin_char] = chr(i)
        for i in range(0x1D68A, 0x1D6A4):
            latin_char = chr(ord('a') + (i - 0x1D68A))
            mono_map[latin_char] = chr(i)
        for i in range(0x1D7F6, 0x1D800):
            digit = chr(ord('0') + (i - 0x1D7F6))
            mono_map[digit] = chr(i)
        self._font_maps["monospace"] = mono_map
        
        circled_map = {}
        for i in range(0x24B6, 0x24D0):
            latin_char = chr(ord('A') + (i - 0x24B6))
            circled_map[latin_char] = chr(i)
        for i in range(0x24D0, 0x24EA):
            latin_char = chr(ord('a') + (i - 0x24D0))
            circled_map[latin_char] = chr(i)
        for i in range(10):
            circled_map[str(i)] = chr(0x245F + i + 1)
        self._font_maps["circled"] = circled_map
        
        squared_map = {
            'A': '🄐', 'B': '🄑', 'C': '🄒', 'D': '🄓', 'E': '🄔',
            'F': '🄕', 'G': '🄖', 'H': '🄗', 'I': '🄘', 'J': '🄙',
            'K': '🄚', 'L': '🄛', 'M': '🄜', 'N': '🄝', 'O': '🄞',
            'P': '🄟', 'Q': '🄠', 'R': '🄡', 'S': '🄢', 'T': '🄣',
            'U': '🄤', 'V': '🄥', 'W': '🄦', 'X': '🄧', 'Y': '🄨',
            'Z': '🄩',
            'a': '🄰', 'b': '🄱', 'c': '🄲', 'd': '🄳', 'e': '🄴',
            'f': '🄵', 'g': '🄶', 'h': '🄷', 'i': '🄸', 'j': '🄹',
            'k': '🄺', 'l': '🄻', 'm': '🄼', 'n': '🄽', 'o': '🄾',
            'p': '🄿', 'q': '🅀', 'r': '🅁', 's': '🅂', 't': '🅃',
            'u': '🅄', 'v': '🅅', 'w': '🅆', 'x': '🅇', 'y': '🅈',
            'z': '🅉',
        }
        self._font_maps["squared"] = squared_map
        
        fraktur_map = {}
        for i in range(0x1D504, 0x1D51E):
            latin_char = chr(ord('A') + (i - 0x1D504))
            fraktur_map[latin_char] = chr(i)
        for i in range(0x1D51E, 0x1D538):
            latin_char = chr(ord('a') + (i - 0x1D51E))
            fraktur_map[latin_char] = chr(i)
        self._font_maps["fraktur"] = fraktur_map

    async def client_ready(self, client, db):
        self.client = client
        self.db = db

    def _convert_text(self, text: str, font_map: dict) -> str:
        if not text:
            return text
        
        result = []
        for char in text:
            if char in font_map:
                result.append(font_map[char])
            elif char in self._cyrillic_map:
                result.append(self._cyrillic_map[char])
            else:
                result.append(char)
        
        return ''.join(result)

    @loader.watcher(outgoing=True, only_text=True)
    async def watcher(self, message: Message):
        if not self.config["font_on"]:
            return
        
        original_text = message.raw_text or message.text
        if not original_text:
            return
        
        prefix = self.get_prefix()
        if original_text.startswith(prefix):
            return
        
        font_name = self.config["current_font"]
        if font_name not in self._font_maps:
            return
        
        font_map = self._font_maps[font_name]
        converted_text = self._convert_text(original_text, font_map)
        
        if converted_text == original_text:
            return
        
        try:
            await asyncio.sleep(0.1)
            await message.edit(converted_text)
        except Exception:
            pass

    @loader.command()
    async def fonton(self, message: Message):
        if self.config["font_on"]:
            await utils.answer(message, self.strings["already_enabled"])
            return
        
        self.config["font_on"] = True
        await utils.answer(message, self.strings["enabled"])

    @loader.command()
    async def fontoff(self, message: Message):
        if not self.config["font_on"]:
            await utils.answer(message, self.strings["already_disabled"])
            return
        
        self.config["font_on"] = False
        await utils.answer(message, self.strings["disabled"])

    @loader.command()
    async def fontset(self, message: Message):
        args = utils.get_args_raw(message).lower()
        
        available_fonts = list(self._font_maps.keys())
        
        if not args:
            fonts_list = ", ".join(available_fonts)
            await utils.answer(
                message,
                f"{self.strings['available_fonts'].format(fonts_list)}\n"
                f"{self.strings['current_font'].format(self.config['current_font'])}"
            )
            return
        
        if args not in available_fonts:
            await utils.answer(
                message,
                f"❌ Неверный шрифт. Доступные: {', '.join(available_fonts)}"
            )
            return
        
        self.config["current_font"] = args
        await utils.answer(message, self.strings["font_changed"].format(args))

    @loader.command()
    async def fonttest(self, message: Message):
        args = utils.get_args_raw(message)
        if not args:
            await utils.answer(message, "ℹ️ Введите текст для теста")
            return
        
        font_name = self.config["current_font"]
        if font_name not in self._font_maps:
            await utils.answer(message, "❌ Ошибка: шрифт не найден")
            return
        
        font_map = self._font_maps[font_name]
        converted = self._convert_text(args, font_map)
        
        await utils.answer(
            message,
            f"🔤 Тест шрифта '{font_name}':\n"
            f"Оригинал: {args}\n"
            f"Конвертация: {converted}"
            )
