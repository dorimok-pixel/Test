# meta developer: @mofkomodules
# name: MusicRecognizer

__version__ = (1, 0, 3)

import asyncio
import logging
import hashlib
from typing import Optional, List, Dict

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
        "extracting": "🔧 Извлекаю аудио...",
        "no_api_keys": "❌ API ключи не настроены\n\nДобавьте ключи в конфиг",
        "api_error": "❌ Ошибка {service}: {error}"
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
            loader.ConfigValue(
                "acrcloud_keys",
                "",
                "ACRCloud ключи в формате: access_key|secret_key\nПолучить: https://www.acrcloud.com",
                validator=loader.validators.Hidden(),
            ),
            loader.ConfigValue(
                "musixmatch_keys",
                "",
                "Musixmatch API ключи через запятую\nПолучить: https://developer.musixmatch.com",
                validator=loader.validators.Hidden(),
            ),
            loader.ConfigValue(
                "audd_keys",
                "",
                "Audd.io API ключи через запятую\nПолучить: https://audd.io",
                validator=loader.validators.Hidden(),
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

    async def recognize_acrcloud(self, audio_data: bytes) -> Optional[Dict]:
        try:
            import aiohttp
            import base64
            import time
            import hmac
            
            if not self.config["acrcloud_keys"]:
                return None
                
            keys = self.config["acrcloud_keys"].split('|')
            if len(keys) != 2:
                return None
                
            access_key, secret_key = keys[0].strip(), keys[1].strip()
            
            timestamp = str(int(time.time()))
            signature_version = '1'
            string_to_sign = f'POST\n/v1/identify\n{access_key}\n{signature_version}\n{timestamp}'
            
            signature = hmac.new(
                secret_key.encode(),
                string_to_sign.encode(),
                hashlib.sha1
            ).digest()
            
            signature = base64.b64encode(signature).decode()
            
            audio_b64 = base64.b64encode(audio_data).decode()
            
            data = {
                'access_key': access_key,
                'sample_bytes': len(audio_data),
                'sample': audio_b64,
                'timestamp': timestamp,
                'signature': signature,
                'data_type': 'audio',
                'signature_version': signature_version
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    'https://identify-eu-west-1.acrcloud.com/v1/identify',
                    json=data
                ) as response:
                    result = await response.json()
                    
                    if result.get('status', {}).get('code') == 0:
                        music = result.get('metadata', {}).get('music', [{}])[0]
                        return {
                            'title': music.get('title', 'Неизвестно'),
                            'artist': music.get('artists', [{}])[0].get('name', 'Неизвестно'),
                            'album': music.get('album', {}).get('name', ''),
                            'service': 'ACRCloud'
                        }
            return None
            
        except Exception as e:
            logger.error(f"ACRCloud error: {e}")
            return None

    async def recognize_musixmatch(self, audio_data: bytes) -> Optional[Dict]:
        try:
            import aiohttp
            
            if not self.config["musixmatch_keys"]:
                return None
                
            keys = [k.strip() for k in self.config["musixmatch_keys"].split(',') if k.strip()]
            if not keys:
                return None
            
            # Для Musixmatch нужно сначала получить fingerprint
            fingerprint = await self.get_audio_fingerprint(audio_data)
            if not fingerprint:
                return None
                
            for api_key in keys:
                async with aiohttp.ClientSession() as session:
                    params = {
                        'apikey': api_key,
                        'q_track': fingerprint.get('title', ''),
                        'q_artist': fingerprint.get('artist', ''),
                        'format': 'json',
                        'f_has_lyrics': 1
                    }
                    
                    async with session.get(
                        'https://api.musixmatch.com/ws/1.1/matcher.track.get',
                        params=params
                    ) as response:
                        result = await response.json()
                        
                        if result.get('message', {}).get('header', {}).get('status_code') == 200:
                            track = result.get('message', {}).get('body', {}).get('track')
                            if track:
                                return {
                                    'title': track.get('track_name', 'Неизвестно'),
                                    'artist': track.get('artist_name', 'Неизвестно'),
                                    'album': track.get('album_name', ''),
                                    'service': 'Musixmatch'
                                }
            return None
            
        except Exception as e:
            logger.error(f"Musixmatch error: {e}")
            return None

    async def recognize_audd(self, audio_data: bytes) -> Optional[Dict]:
        try:
            import aiohttp
            
            if not self.config["audd_keys"]:
                return None
                
            keys = [k.strip() for k in self.config["audd_keys"].split(',') if k.strip()]
            if not keys:
                return None
            
            for api_key in keys:
                async with aiohttp.ClientSession() as session:
                    form_data = aiohttp.FormData()
                    form_data.add_field('file', audio_data, filename='audio.mp3', content_type='audio/mpeg')
                    form_data.add_field('api_token', api_key)
                    form_data.add_field('return', 'spotify,youtube')
                    
                    async with session.post('https://api.audd.io/', data=form_data) as response:
                        result = await response.json()
                        
                        if result.get('status') == 'success' and result.get('result'):
                            music = result['result']
                            return {
                                'title': music.get('title', 'Неизвестно'),
                                'artist': music.get('artist', 'Неизвестно'),
                                'album': music.get('album', ''),
                                'service': 'Audd.io'
                            }
            return None
            
        except Exception as e:
            logger.error(f"Audd.io error: {e}")
            return None

    async def get_audio_fingerprint(self, audio_data: bytes) -> Optional[Dict]:
        # Упрощенный метод для получения базовой информации об аудио
        # В реальности нужно использовать библиотеки для анализа аудио
        return {'title': '', 'artist': ''}

    def format_links(self, music_info: Dict) -> str:
        links = []
        title = music_info.get('title', '')
        artist = music_info.get('artist', '')
        
        if title and artist:
            search_query = f"{artist} {title}".replace(' ', '+')
            
            # Яндекс Музыка
            yandex_url = f"https://music.yandex.ru/search?text={search_query}"
            links.append(f"🎵 <a href='{yandex_url}'>Яндекс Музыка</a>")
            
            # YouTube
            youtube_url = f"https://www.youtube.com/results?search_query={search_query}"
            links.append(f"📺 <a href='{youtube_url}'>YouTube</a>")
            
            # Spotify
            spotify_url = f"https://open.spotify.com/search/{search_query}"
            links.append(f"🎧 <a href='{spotify_url}'>Spotify</a>")
            
            # SoundCloud
            soundcloud_url = f"https://soundcloud.com/search?q={search_query}"
            links.append(f"☁️ <a href='{soundcloud_url}'>SoundCloud</a>")
        
        return '\n'.join(links) if links else "Ссылки не найдены"

    async def recognize_song(self, audio_data: bytes) -> Optional[Dict]:
        # Пробуем все сервисы по очереди
        services = [
            self.recognize_acrcloud,
            self.recognize_musixmatch, 
            self.recognize_audd
        ]
        
        for service in services:
            try:
                result = await service(audio_data)
                if result:
                    result['links'] = self.format_links(result)
                    return result
                await asyncio.sleep(1)  # Задержка между запросами
            except Exception as e:
                logger.error(f"Service error: {e}")
                continue
                
        return None

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

        # Проверяем наличие ключей
        has_keys = any([
            self.config["acrcloud_keys"],
            self.config["musixmatch_keys"], 
            self.config["audd_keys"]
        ])
        
        if not has_keys:
            await utils.answer(message, self.strings["no_api_keys"])
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
            response += f"\n\n🔍 <i>Распознано через {result['service']}</i>"
            await utils.answer(status_msg, response)
        else:
            await utils.answer(status_msg, self.strings["recognition_failed"])
