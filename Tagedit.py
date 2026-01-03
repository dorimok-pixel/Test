# meta developer: @mofkomodules
# name: MTagEditor
# desc: Редактор тегов MP3 файлов

import asyncio
import io
import logging
import os
import tempfile
from pathlib import Path

try:
    from mutagen import File as MutagenFile
    from mutagen.id3 import ID3, APIC, TIT2, TPE1, TALB, TDRC, TRCK, TCON, TCOM, TPE2, TPOS, USLT, COMM
    from mutagen.mp3 import MP3
    from mutagen.easyid3 import EasyID3
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False

from telethon.tl.types import Message, DocumentAttributeFilename
from telethon.utils import get_display_name

from .. import loader, utils

logger = logging.getLogger(__name__)


@loader.tds
class MTagEditor(loader.Module):
    strings = {"name": "MTagEditor"}
    strings_ru = strings

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "default_genre",
                "",
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "auto_fill_from_filename",
                True,
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "filename_pattern",
                "{artist} - {title}",
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "cover_quality",
                2,
                validator=loader.validators.Integer(minimum=0, maximum=2),
            ),
        )
        self.current_files = {}
        self._lock = asyncio.Lock()

    async def client_ready(self, client, db):
        self._client = client
        self._db = db
        self.me = await client.get_me()
        if not MUTAGEN_AVAILABLE:
            logger.error("Mutagen не установлен!")
        else:
            EasyID3.RegisterTextKey('albumartist', 'TPE2')
            EasyID3.RegisterTextKey('discnumber', 'TPOS')
            EasyID3.RegisterTextKey('lyrics', 'USLT')

    def _format_duration(self, seconds):
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}:{secs:02d}"

    def _format_size(self, size):
        for unit in ['B', 'KB', 'MB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} GB"

    async def _download_file(self, message):
        temp_file = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp:
                temp_file = tmp.name
            await message.download_media(temp_file)
            file_info = os.stat(temp_file)
            return temp_file, {'size': file_info.st_size, 'path': temp_file}
        except Exception as e:
            if temp_file and os.path.exists(temp_file):
                os.remove(temp_file)
            raise e

    def _read_tags(self, filepath):
        try:
            audio = MP3(filepath, ID3=ID3)
        except Exception:
            try:
                audio = EasyID3(filepath)
            except Exception as e:
                raise Exception(f"Не удалось прочитать теги: {e}")

        tags = {
            'artist': '', 'title': '', 'album': '', 'genre': '', 'year': '',
            'track': '', 'total_tracks': '', 'album_artist': '', 'disc': '',
            'total_discs': '', 'lyrics': '', 'comment': '',
            'bitrate': getattr(audio.info, 'bitrate', 0) // 1000 if hasattr(audio.info, 'bitrate') else 0,
            'duration': self._format_duration(audio.info.length) if hasattr(audio.info, 'length') else '0:00',
        }

        if isinstance(audio, EasyID3):
            for key in tags:
                if key in audio:
                    tags[key] = ', '.join(audio[key]) if isinstance(audio[key], list) else str(audio[key])
        else:
            id3 = ID3(filepath)
            if 'TPE1' in id3:
                tags['artist'] = str(id3['TPE1'])
            if 'TIT2' in id3:
                tags['title'] = str(id3['TIT2'])
            if 'TALB' in id3:
                tags['album'] = str(id3['TALB'])
            if 'TDRC' in id3:
                tags['year'] = str(id3['TDRC'])[:4]
            if 'TRCK' in id3:
                track = str(id3['TRCK'])
                if '/' in track:
                    tags['track'], tags['total_tracks'] = track.split('/', 1)
                else:
                    tags['track'] = track
            if 'TCON' in id3:
                tags['genre'] = str(id3['TCON'])
            if 'TPE2' in id3:
                tags['album_artist'] = str(id3['TPE2'])
            if 'TPOS' in id3:
                disc = str(id3['TPOS'])
                if '/' in disc:
                    tags['disc'], tags['total_discs'] = disc.split('/', 1)
                else:
                    tags['disc'] = disc
            if 'USLT' in id3:
                tags['lyrics'] = str(id3['USLT'])
            if 'COMM' in id3:
                tags['comment'] = str(id3['COMM'])

        return tags

    def _get_cover_info(self, filepath):
        try:
            id3 = ID3(filepath)
            if 'APIC:' in id3:
                apic = id3['APIC:']
                return {'data': apic.data, 'mime': apic.mime, 'width': 0, 'height': 0}
            for key in id3.keys():
                if key.startswith('APIC'):
                    apic = id3[key]
                    return {'data': apic.data, 'mime': apic.mime, 'width': 0, 'height': 0}
        except Exception:
            pass
        return None

    def _extract_filename_tags(self, filename):
        result = {}
        name = os.path.splitext(filename)[0]
        import re
        patterns = [
            r'^(?P<artist>.+?) - (?P<title>.+?)$',
            r'^(?P<artist>.+?) – (?P<title>.+?)$',
            r'^(?P<track>\d+)\.?\s*(?P<artist>.+?) - (?P<title>.+?)$',
            r'^(?P<title>.+?)$',
        ]
        for pattern in patterns:
            match = re.match(pattern, name)
            if match:
                result.update(match.groupdict())
                break
        return result

    @loader.command(ru_doc="[reply] - Показать теги MP3 файла")
    async def mtag(self, message):
        if not MUTAGEN_AVAILABLE:
            await utils.answer(message, "❗️ <b>Библиотека mutagen не установлена!</b>\nУстановите: <code>pip install mutagen</code>")
            return

        reply = await message.get_reply_message()
        if not reply or not reply.document:
            await utils.answer(message, "❗️ <b>Ответьте на MP3 файл!</b>")
            return

        mime_type = getattr(reply.document, 'mime_type', '')
        filename = next(
            (attr.file_name for attr in reply.document.attributes 
             if isinstance(attr, DocumentAttributeFilename)), None)
        
        if not filename or not filename.lower().endswith('.mp3'):
            if not mime_type or 'audio/mpeg' not in mime_type:
                await utils.answer(message, "❗️ <b>Файл не является MP3!</b>")
                return

        status_msg = await utils.answer(message, "⏳ <b>Обработка файла...</b>")
        
        try:
            async with self._lock:
                temp_file, file_info = await self._download_file(reply)
                
                try:
                    tags = self._read_tags(temp_file)
                    cover_info = self._get_cover_info(temp_file)
                    
                    tags_display = (
                        "🎵 <b>Теги MP3 файла:</b>\n"
                        "<b>─────────────────</b>\n"
                        "🎤 <b>Артист:</b> {artist}\n"
                        "📝 <b>Название:</b> {title}\n"
                        "💿 <b>Альбом:</b> {album}\n"
                        "🎼 <b>Жанр:</b> {genre}\n"
                        "📅 <b>Год:</b> {year}\n"
                        "🔢 <b>Трек:</b> {track}/{total_tracks}\n"
                        "👥 <b>Альбомный артист:</b> {album_artist}\n"
                        "📁 <b>Диск:</b> {disc}/{total_discs}\n"
                        "📊 <b>Битрейт:</b> {bitrate} kbps\n"
                        "⏱ <b>Длительность:</b> {duration}\n"
                        "📏 <b>Размер:</b> {size}\n"
                        "<b>─────────────────</b>"
                    ).format(
                        artist=tags['artist'] or 'Не указан',
                        title=tags['title'] or 'Не указано',
                        album=tags['album'] or 'Не указан',
                        genre=tags['genre'] or 'Не указан',
                        year=tags['year'] or 'Не указан',
                        track=tags['track'] or '0',
                        total_tracks=tags['total_tracks'] or '0',
                        album_artist=tags['album_artist'] or 'Не указан',
                        disc=tags['disc'] or '0',
                        total_discs=tags['total_discs'] or '0',
                        bitrate=tags['bitrate'],
                        duration=tags['duration'],
                        size=self._format_size(file_info['size']),
                    )
                    
                    cover_text = ""
                    if cover_info:
                        cover_text = f"\n\n📸 <b>Текущая обложка:</b>\nРазмер: ?x?"
                    else:
                        cover_text = f"\n\n📸 <b>Обложка отсутствует</b>"
                    
                    buttons = [
                        [
                            {"text": "✏️ Редактировать теги", "callback": self._edit_tags_menu, "args": (reply.id, temp_file)},
                            {"text": "🖼 Извлечь обложку", "callback": self._extract_cover, "args": (reply.id, temp_file)},
                        ],
                        [
                            {"text": "🖼 Установить обложку", "callback": self._set_cover, "args": (reply.id, temp_file)},
                            {"text": "🤖 Автозаполнение", "callback": self._auto_fill_tags, "args": (reply.id, temp_file)},
                        ],
                        [
                            {"text": "🗑 Очистить теги", "callback": self._clear_tags, "args": (reply.id, temp_file)},
                        ]
                    ]
                    
                    await utils.answer(status_msg, tags_display + cover_text, reply_markup=buttons)
                    
                    self.current_files[reply.id] = {
                        'path': temp_file,
                        'original_message': reply.id,
                        'tags': tags,
                        'cover': cover_info
                    }
                    
                except Exception as e:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                    raise e
                    
        except Exception as e:
            logger.error(f"Error reading tags: {e}")
            await utils.answer(status_msg, f"❗️ <b>Ошибка чтения файла:</b>\n<code>{str(e)}</code>")

    async def _edit_tags_menu(self, call, message_id, filepath):
        if message_id not in self.current_files:
            await call.answer("Файл не найден!", show_alert=True)
            return
        
        buttons = [
            [
                {"text": "🎤 Артист", "callback": self._edit_tag, "args": (message_id, 'artist')},
                {"text": "📝 Название", "callback": self._edit_tag, "args": (message_id, 'title')},
            ],
            [
                {"text": "💿 Альбом", "callback": self._edit_tag, "args": (message_id, 'album')},
                {"text": "🎼 Жанр", "callback": self._edit_tag, "args": (message_id, 'genre')},
            ],
            [
                {"text": "📅 Год", "callback": self._edit_tag, "args": (message_id, 'year')},
                {"text": "🔢 Номер трека", "callback": self._edit_tag, "args": (message_id, 'track')},
            ],
            [
                {"text": "👥 Альбомный артист", "callback": self._edit_tag, "args": (message_id, 'album_artist')},
                {"text": "📁 Номер диска", "callback": self._edit_tag, "args": (message_id, 'disc')},
            ],
            [
                {"text": "📝 Текст песни", "callback": self._edit_tag, "args": (message_id, 'lyrics')},
                {"text": "💬 Комментарий", "callback": self._edit_tag, "args": (message_id, 'comment')},
            ],
            [
                {"text": "🔙 Назад", "callback": self._show_tags, "args": (message_id,)},
                {"text": "💾 Сохранить файл", "callback": self._save_file, "args": (message_id,)},
            ]
        ]
        
        await call.edit("✏️ <b>Редактирование тегов:</b>\nВыберите тег для редактирования", reply_markup=buttons)

    async def _edit_tag(self, call, message_id, tag):
        if message_id not in self.current_files:
            await call.answer("Файл не найден!", show_alert=True)
            return
        
        current_value = self.current_files[message_id]['tags'].get(tag, '')
        
        await call.edit(
            f"✍️ Введите значение для <b>{tag}</b>:",
            reply_markup=[
                [
                    {
                        "text": "✍️ Ввести значение",
                        "input": f"Введите значение для {tag}",
                        "handler": self._update_tag,
                        "kwargs": {"message_id": message_id, "tag": tag, "current": current_value}
                    }
                ],
                [
                    {"text": "🔙 Назад", "callback": self._edit_tags_menu, "args": (message_id, self.current_files[message_id]['path'])}
                ]
            ]
        )

    async def _update_tag(self, call, query, message_id, tag, current):
        if message_id not in self.current_files:
            await call.answer("Файл не найден!", show_alert=True)
            return
        
        if tag == 'track':
            if query and '/' in query:
                track_parts = query.split('/')
                if len(track_parts) == 2 and track_parts[0].isdigit() and track_parts[1].isdigit():
                    self.current_files[message_id]['tags']['track'] = track_parts[0]
                    self.current_files[message_id]['tags']['total_tracks'] = track_parts[1]
                else:
                    await call.answer("❗️ <b>Неверный формат номера трека!</b>\nИспользуйте: номер/всего", show_alert=True)
                    return
            elif query.isdigit():
                self.current_files[message_id]['tags']['track'] = query
            elif query:
                await call.answer("❗️ <b>Неверный формат номера трека!</b>\nИспользуйте: номер/всего", show_alert=True)
                return
        elif tag == 'disc':
            if query and '/' in query:
                disc_parts = query.split('/')
                if len(disc_parts) == 2 and disc_parts[0].isdigit() and disc_parts[1].isdigit():
                    self.current_files[message_id]['tags']['disc'] = disc_parts[0]
                    self.current_files[message_id]['tags']['total_discs'] = disc_parts[1]
                else:
                    await call.answer("❗️ <b>Неверный формат номера диска!</b>\nИспользуйте: номер/всего", show_alert=True)
                    return
            elif query.isdigit():
                self.current_files[message_id]['tags']['disc'] = query
            elif query:
                await call.answer("❗️ <b>Неверный формат номера диска!</b>\nИспользуйте: номер/всего", show_alert=True)
                return
        else:
            self.current_files[message_id]['tags'][tag] = query
        
        await self._apply_tags_to_file(message_id)
        
        await call.edit(
            f"✅ <b>{tag} обновлен:</b> {query}",
            reply_markup=[
                [
                    {"text": "🔙 Назад", "callback": self._edit_tags_menu, "args": (message_id, self.current_files[message_id]['path'])}
                ]
            ]
        )

    async def _apply_tags_to_file(self, message_id):
        if message_id not in self.current_files:
            return
        
        file_info = self.current_files[message_id]
        tags = file_info['tags']
        
        try:
            audio = MP3(file_info['path'], ID3=ID3)
            audio.delete()
            
            if tags['artist']:
                audio['TPE1'] = TPE1(encoding=3, text=tags['artist'])
            if tags['title']:
                audio['TIT2'] = TIT2(encoding=3, text=tags['title'])
            if tags['album']:
                audio['TALB'] = TALB(encoding=3, text=tags['album'])
            if tags['year']:
                audio['TDRC'] = TDRC(encoding=3, text=tags['year'])
            if tags['track'] or tags['total_tracks']:
                track_str = f"{tags['track'] or 0}/{tags['total_tracks'] or 0}"
                audio['TRCK'] = TRCK(encoding=3, text=track_str)
            if tags['genre']:
                audio['TCON'] = TCON(encoding=3, text=tags['genre'])
            if tags['album_artist']:
                audio['TPE2'] = TPE2(encoding=3, text=tags['album_artist'])
            if tags['disc'] or tags['total_discs']:
                disc_str = f"{tags['disc'] or 0}/{tags['total_discs'] or 0}"
                audio['TPOS'] = TPOS(encoding=3, text=disc_str)
            if tags['lyrics']:
                audio['USLT'] = USLT(encoding=3, text=tags['lyrics'])
            if tags['comment']:
                audio['COMM'] = COMM(encoding=3, text=tags['comment'])
            
            audio.save()
            
        except Exception as e:
            logger.error(f"Error saving tags: {e}")

    async def _show_tags(self, call, message_id):
        if message_id not in self.current_files:
            await call.answer("Файл не найден!", show_alert=True)
            return
        
        file_info = self.current_files[message_id]
        tags = file_info['tags']
        
        tags_display = (
            "🎵 <b>Теги MP3 файла:</b>\n"
            "<b>─────────────────</b>\n"
            "🎤 <b>Артист:</b> {artist}\n"
            "📝 <b>Название:</b> {title}\n"
            "💿 <b>Альбом:</b> {album}\n"
            "🎼 <b>Жанр:</b> {genre}\n"
            "📅 <b>Год:</b> {year}\n"
            "🔢 <b>Трек:</b> {track}/{total_tracks}\n"
            "👥 <b>Альбомный артист:</b> {album_artist}\n"
            "📁 <b>Диск:</b> {disc}/{total_discs}\n"
            "<b>─────────────────</b>"
        ).format(
            artist=tags['artist'] or 'Не указан',
            title=tags['title'] or 'Не указано',
            album=tags['album'] or 'Не указан',
            genre=tags['genre'] or 'Не указан',
            year=tags['year'] or 'Не указан',
            track=tags['track'] or '0',
            total_tracks=tags['total_tracks'] or '0',
            album_artist=tags['album_artist'] or 'Не указан',
            disc=tags['disc'] or '0',
            total_discs=tags['total_discs'] or '0',
        )
        
        buttons = [
            [
                {"text": "✏️ Редактировать теги", "callback": self._edit_tags_menu, "args": (message_id, file_info['path'])},
                {"text": "🖼 Извлечь обложку", "callback": self._extract_cover, "args": (message_id, file_info['path'])},
            ],
            [
                {"text": "🖼 Установить обложку", "callback": self._set_cover, "args": (message_id, file_info['path'])},
                {"text": "🤖 Автозаполнение", "callback": self._auto_fill_tags, "args": (message_id, file_info['path'])},
            ],
            [
                {"text": "🗑 Очистить теги", "callback": self._clear_tags, "args": (message_id, file_info['path'])},
            ]
        ]
        
        await call.edit(tags_display, reply_markup=buttons)

    async def _extract_cover(self, call, message_id, filepath):
        if message_id not in self.current_files:
            await call.answer("Файл не найден!", show_alert=True)
            return
        
        cover_info = self._get_cover_info(filepath)
        if not cover_info:
            await call.answer("Обложка не найдена!", show_alert=True)
            return
        
        try:
            await self._client.send_file(
                call.chat_id,
                file=io.BytesIO(cover_info['data']),
                caption="✅ <b>Обложка извлечена и отправлена!</b>",
                reply_to=call.message_id
            )
        except Exception as e:
            logger.error(f"Error sending cover: {e}")
            await call.answer("Ошибка отправки обложки!", show_alert=True)

    async def _set_cover(self, call, message_id, filepath):
        if message_id not in self.current_files:
            await call.answer("Файл не найден!", show_alert=True)
            return
        
        await call.edit(
            "📸 <b>Ответьте на изображение для установки обложки</b>",
            reply_markup=[
                [
                    {"text": "🔙 Назад", "callback": self._show_tags, "args": (message_id,)}
                ]
            ]
        )

    async def _auto_fill_tags(self, call, message_id, filepath):
        if message_id not in self.current_files:
            await call.answer("Файл не найден!", show_alert=True)
            return
        
        if not self.config["auto_fill_from_filename"]:
            await call.answer("Автозаполнение отключено в конфиге!", show_alert=True)
            return
        
        reply = await self._client.get_messages(
            self.current_files[message_id]['original_message'].chat_id,
            ids=self.current_files[message_id]['original_message']
        )
        
        filename = next(
            (attr.file_name for attr in reply.document.attributes 
             if isinstance(attr, DocumentAttributeFilename)),
            "unknown.mp3"
        )
        
        extracted = self._extract_filename_tags(filename)
        
        if extracted.get('artist'):
            self.current_files[message_id]['tags']['artist'] = extracted['artist']
        if extracted.get('title'):
            self.current_files[message_id]['tags']['title'] = extracted['title']
        if extracted.get('track'):
            self.current_files[message_id]['tags']['track'] = extracted['track']
        
        if self.config["default_genre"]:
            self.current_files[message_id]['tags']['genre'] = self.config["default_genre"]
        
        await self._apply_tags_to_file(message_id)
        await call.answer("✅ <b>Автозаполнение завершено!</b>", show_alert=True)
        await self._show_tags(call, message_id)

    async def _clear_tags(self, call, message_id, filepath):
        if message_id not in self.current_files:
            await call.answer("Файл не найден!", show_alert=True)
            return
        
        for key in self.current_files[message_id]['tags']:
            if key not in ['bitrate', 'duration']:
                self.current_files[message_id]['tags'][key] = ''
        
        await self._apply_tags_to_file(message_id)
        await call.answer("✅ <b>Все теги очищены!</b>", show_alert=True)
        await self._show_tags(call, message_id)

    async def _save_file(self, call, message_id):
        if message_id not in self.current_files:
            await call.answer("Файл не найден!", show_alert=True)
            return
        
        file_info = self.current_files[message_id]
        
        try:
            with open(file_info['path'], 'rb') as f:
                file_data = f.read()
            
            file_io = io.BytesIO(file_data)
            file_io.name = "edited_" + os.path.basename(file_info['path'])
            
            await self._client.send_file(
                call.chat_id,
                file=file_io,
                caption="💾 <b>Файл сохранен!</b>",
                reply_to=call.message_id
            )
        except Exception as e:
            logger.error(f"Error saving file: {e}")
            await call.answer("Ошибка сохранения файла!", show_alert=True)
