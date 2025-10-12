# meta developer: @mofkomodules
# name: MusicRecognizer

__version__ = (1, 0, 1)

import asyncio
import logging
from typing import Optional

from .. import loader, utils
from telethon.tl.types import Message, DocumentAttributeVideo, DocumentAttributeFilename

logger = logging.getLogger(__name__)

@loader.tds
class MusicRecognizerMod(loader.Module):
    strings = {
        "name": "MusicRecognizer",
        "processing": "🎵 Обрабатываю видео...",
        "no_video": "❌ Ответьте на видео сообщение",
        "recognition_failed": "❌ Не удалось распознать музыку",
        "recognition_success": "🎶 <b>Найдено:</b>\n\n<code>{title}</code>\n<code>{artist}</code>\n\n🔗 <b>Ссылки:</b>\n{links}",
        "downloading": "📥 Скачиваю видео...",
        "file_too_large": "❌ Файл слишком большой (макс. {max_size} МБ)",
        "wait_cooldown": "⏳ Подождите {} секунд",
        "extracting": "🔧 Извлекаю аудио..."
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "cooldown",
                15,
                "Задержка между запросами (секунды)",
                validator=loader.validators.Integer(minimum=10, maximum=60),
            ),
            loader.ConfigValue(
                "max_file_size",
                100,
                "Максимальный размер файла (МБ)",
                validator=loader.validators.Integer(minimum=20, maximum=500),
            ),
        )
        self.last_request = 0

    async def client_ready(self, client, db):
        self.client = client
        self.db = db

    def is_video_message(self, message: Message) -> bool:
        if not message.media:
            return False
        
        if hasattr(message.media, 'document'):
            doc = message.media.document
            if any(isinstance(attr, DocumentAttributeVideo) for attr in doc.attributes):
                return True
            
            filename_attr = next((attr for attr in doc.attributes if isinstance(attr, DocumentAttributeFilename)), None)
            if filename_attr:
                ext = filename_attr.file_name.split('.')[-1].lower()
                return ext in ['mp4', 'avi', 'mov', 'mkv', 'webm', 'm4v', '3gp']
        
        return False

    async def check_cooldown(self) -> bool:
        current_time = asyncio.get_event_loop().time()
        if current_time - self.last_request < self.config["cooldown"]:
            return False
        self.last_request = current_time
        return True

    async def extract_audio_from_video(self, video_path: str) -> Optional[bytes]:
        try:
            import subprocess
            import tempfile
            import os
            
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as temp_audio:
                audio_path = temp_audio.name
            
            cmd = [
                'ffmpeg', '-i', video_path, '-vn', '-acodec', 'libmp3lame',
                '-ab', '128k', '-ac', '2', '-ar', '44100', '-y', audio_path
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            await process.communicate()
            
            if process.returncode == 0 and os.path.exists(audio_path):
                with open(audio_path, 'rb') as f:
                    audio_data = f.read()
                os.unlink(audio_path)
                os.unlink(video_path)
                return audio_data
            
            if os.path.exists(audio_path):
                os.unlink(audio_path)
            if os.path.exists(video_path):
                os.unlink(video_path)
            return None
            
        except Exception as e:
            logger.error(f"Ошибка извлечения аудио: {e}")
            if os.path.exists(video_path):
                os.unlink(video_path)
            return None

    async def download_video(self, message: Message) -> Optional[str]:
        try:
            if not self.is_video_message(message):
                return None

            if hasattr(message.media, 'document'):
                file_size = message.media.document.size / (1024 * 1024)
                if file_size > self.config["max_file_size"]:
                    return None

            video_path = await message.download_media()
            return video_path

        except Exception as e:
            logger.error(f"Ошибка скачивания: {e}")
            return None

    async def recognize_song(self, audio_data: bytes) -> Optional[dict]:
        try:
            import aiohttp
            
            async with aiohttp.ClientSession() as session:
                form_data = aiohttp.FormData()
                form_data.add_field('audio', audio_data, filename='audio.mp3', content_type='audio/mpeg')
                
                async with session.post(
                    'https://api.audd.io/',
                    data=form_data,
                    params={'api_token': 'test'}  # Демо-режим
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        if result.get('status') == 'success' and result.get('result'):
                            music = result['result']
                            return {
                                'title': music.get('title', 'Неизвестно'),
                                'artist': music.get('artist', 'Неизвестно'),
                                'album': music.get('album', ''),
                                'links': self.format_links(music)
                            }
            return None

        except Exception as e:
            logger.error(f"Ошибка распознавания: {e}")
            return None

    def format_links(self, music_info: dict) -> str:
        links = []
        title = music_info.get('title', '')
        artist = music_info.get('artist', '')
        
        if title and artist:
            search_query = f"{artist} {title}".replace(' ', '+')
            
            yandex_url = f"https://music.yandex.ru/search?text={search_query}"
            links.append(f"🎵 <a href='{yandex_url}'>Яндекс Музыка</a>")
            
            youtube_url = f"https://www.youtube.com/results?search_query={search_query}"
            links.append(f"📺 <a href='{youtube_url}'>YouTube</a>")
            
            spotify_url = f"https://open.spotify.com/search/{search_query}"
            links.append(f"🎧 <a href='{spotify_url}'>Spotify</a>")
            
            soundcloud_url = f"https://soundcloud.com/search?q={search_query}"
            links.append(f"☁️ <a href='{soundcloud_url}'>SoundCloud</a>")
        
        return '\n'.join(links) if links else "Ссылки не найдены"

    @loader.command()
    async def song(self, message: Message):
        """Распознать музыку из видео"""
        reply = await message.get_reply_message()
        
        if not reply:
            await utils.answer(message, self.strings["no_video"])
            return

        if not await self.check_cooldown():
            wait_time = self.config["cooldown"] - int(asyncio.get_event_loop().time() - self.last_request)
            await utils.answer(message, self.strings["wait_cooldown"].format(wait_time))
            return

        if not self.is_video_message(reply):
            await utils.answer(message, self.strings["no_video"])
            return

        status_msg = await utils.answer(message, self.strings["downloading"])
        video_path = await self.download_video(reply)
        
        if not video_path:
            await utils.answer(status_msg, self.strings["file_too_large"].format(max_size=self.config["max_file_size"]))
            return

        await utils.answer(status_msg, self.strings["extracting"])
        audio_data = await self.extract_audio_from_video(video_path)
        
        if not audio_data:
            await utils.answer(status_msg, self.strings["recognition_failed"])
            return

        await utils.answer(status_msg, self.strings["processing"])
        
        result = await self.recognize_song(audio_data)
        
        if result:
            response = self.strings["recognition_success"].format(
                title=result['title'],
                artist=result['artist'],
                links=result['links']
            )
            await utils.answer(status_msg, response)
        else:
            await utils.answer(status_msg, self.strings["recognition_failed"])
