#!/usr/bin/env python3
"""
Telegram → MAX Relay
Пересылает входящие сообщения Telegram личного аккаунта в чат бота MAX.
Поддерживает ответы из MAX обратно в Telegram.
Пересылает фото и аудио/голосовые сообщения.

Формат ответа в MAX: #42 Текст ответа
"""
import asyncio
import json
import os
import tempfile
import aiohttp
from telethon import TelegramClient, events
from telethon.tl.types import User

# ─── Конфигурация ─────────────────────────────────────────────────────────────
TG_API_ID   = int(os.environ.get("TG_API_ID",   "0"))
TG_API_HASH = os.environ.get("TG_API_HASH", "")
SESSION     = os.environ.get("TG_SESSION", "tg_session")

def _build_proxy():
    ptype = os.environ.get("PROXY_TYPE", "").lower()
    phost = os.environ.get("PROXY_HOST", "")
    pport = os.environ.get("PROXY_PORT", "")
    if not (ptype and phost and pport):
        return None
    import socks
    kind = socks.SOCKS5 if ptype == "socks5" else socks.HTTP
    return (kind, phost, int(pport),
            True,
            os.environ.get("PROXY_USER") or None,
            os.environ.get("PROXY_PASS") or None)

PROXY = _build_proxy()

MAX_TOKEN   = os.environ.get("MAX_TOKEN", "")
MAX_API     = "https://botapi.max.ru"
MAX_CHAT_ID = int(os.environ.get("MAX_CHAT_ID", "0"))

# Чаты, сообщения из которых НЕ пересылаются в MAX
BLOCKED_CHATS = {
    "U1HOST",
    "Белочка | Юмор",
    "ДАЧНЫЕ ВЕСТИ 🏘️🌳",
    "КУЛИБИН",
    "Канал Игоря Зуевича",
    "Фирсов Александр",
    "Энергоэксперт Фирсов Александр",
}

STATE_FILE = "relay_state.json"

# ─── Состояние ────────────────────────────────────────────────────────────────
_max_chat_id = MAX_CHAT_ID
_max_marker  = 0
_next_msg_id = 1
_id_map: dict[int, int] = {}   # short_id → tg_chat_id
MAX_STORED = 500


def _load_state():
    global _max_chat_id, _max_marker, _next_msg_id, _id_map
    if os.path.exists(STATE_FILE):
        try:
            s = json.load(open(STATE_FILE))
            _max_chat_id = s.get("max_chat_id")
            _max_marker  = s.get("max_marker", 0)
            _next_msg_id = s.get("next_msg_id", 1)
            _id_map      = {int(k): v for k, v in s.get("id_map", {}).items()}
        except Exception:
            pass


def _save_state():
    json.dump({
        "max_chat_id": _max_chat_id,
        "max_marker":  _max_marker,
        "next_msg_id": _next_msg_id,
        "id_map":      _id_map,
    }, open(STATE_FILE, "w"))


def _register(tg_chat_id: int) -> int:
    global _next_msg_id
    sid = _next_msg_id
    _next_msg_id += 1
    if len(_id_map) >= MAX_STORED:
        del _id_map[min(_id_map)]
    _id_map[sid] = tg_chat_id
    _save_state()
    return sid


# ─── MAX API ──────────────────────────────────────────────────────────────────
async def _max_get(session: aiohttp.ClientSession, endpoint: str, params: dict = None):
    headers = {"Authorization": MAX_TOKEN}
    async with session.get(MAX_API + endpoint, params=params, headers=headers) as r:
        return await r.json()


async def _max_post(session: aiohttp.ClientSession, endpoint: str,
                    params: dict = None, body: dict = None):
    headers = {"Authorization": MAX_TOKEN}
    if body:
        headers["Content-Type"] = "application/json"
    async with session.post(MAX_API + endpoint, params=params,
                            json=body, headers=headers) as r:
        return await r.json()


async def send_to_max(session: aiohttp.ClientSession, text: str):
    if not _max_chat_id:
        print("[MAX] Нет активного чата — отправка пропущена")
        return
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
    for chunk in chunks:
        await _max_post(session, "/messages", {"chat_id": _max_chat_id}, {"text": chunk})


async def _max_upload_image(session: aiohttp.ClientSession, file_path: str) -> str | None:
    """Загружает изображение в MAX, возвращает token."""
    try:
        async with session.post(
            MAX_API + "/uploads", params={"type": "image"},
            headers={"Authorization": MAX_TOKEN}
        ) as r:
            upload_url = (await r.json()).get("url")
        if not upload_url:
            return None

        with open(file_path, "rb") as f:
            data = aiohttp.FormData()
            data.add_field("data", f, filename="photo.jpg", content_type="image/jpeg")
            async with session.post(upload_url, data=data) as r:
                resp = await r.json()

        photos = resp.get("photos", {})
        key = next(iter(photos), None)
        return photos[key]["token"] if key else None
    except Exception as e:
        print(f"[MAX upload image] Ошибка: {e}")
        return None


async def _max_upload_file(session: aiohttp.ClientSession,
                           file_path: str, filename: str, mime: str) -> str | None:
    """Загружает файл в MAX, возвращает token."""
    try:
        async with session.post(
            MAX_API + "/uploads", params={"type": "file"},
            headers={"Authorization": MAX_TOKEN}
        ) as r:
            upload_url = (await r.json()).get("url")
        if not upload_url:
            return None

        with open(file_path, "rb") as f:
            data = aiohttp.FormData()
            data.add_field("file", f, filename=filename, content_type=mime)
            async with session.post(upload_url, data=data) as r:
                resp = await r.json()

        return resp.get("token")
    except Exception as e:
        print(f"[MAX upload file] Ошибка: {e}")
        return None


async def send_image_to_max(session: aiohttp.ClientSession,
                             caption: str, file_path: str):
    """Отправляет текст + изображение в MAX."""
    if not _max_chat_id:
        return
    token = await _max_upload_image(session, file_path)
    if not token:
        await send_to_max(session, caption + "\n⚠️ Фото не удалось загрузить")
        return
    # Текст — отдельным сообщением, фото — вложением
    await send_to_max(session, caption)
    await _max_post(session, "/messages", {"chat_id": _max_chat_id}, {
        "attachments": [{"type": "image", "payload": {"token": token}}]
    })


async def send_file_to_max(session: aiohttp.ClientSession,
                            caption: str, file_path: str,
                            filename: str, mime: str):
    """Отправляет текст + файл (аудио, голосовое) в MAX."""
    if not _max_chat_id:
        return
    token = await _max_upload_file(session, file_path, filename, mime)
    if not token:
        await send_to_max(session, caption + "\n⚠️ Файл не удалось загрузить")
        return
    # Ждём готовности вложения
    await send_to_max(session, caption)
    for attempt in range(5):
        r = await _max_post(session, "/messages", {"chat_id": _max_chat_id}, {
            "attachments": [{"type": "file", "payload": {"token": token, "filename": filename}}]
        })
        if not (r.get("code") == "attachment.not.ready"):
            break
        await asyncio.sleep(2)


# ─── Форматирование сообщений ─────────────────────────────────────────────────
def _sender_name(sender) -> tuple[str, str | None]:
    if sender is None:
        return "Неизвестно", None
    if hasattr(sender, "first_name"):
        name = f"{sender.first_name or ''} {sender.last_name or ''}".strip()
        return name or "Без имени", getattr(sender, "username", None)
    title = getattr(sender, "title", None) or "Группа"
    return title, getattr(sender, "username", None)


def _msg_type_text(msg) -> tuple[str, str]:
    """Возвращает (тип, текст/подпись)."""
    caption = msg.text or msg.message or ""
    if msg.photo:      return "photo",      caption
    if msg.sticker:    return "sticker",    ""
    if msg.voice:      return "voice",      ""
    if msg.video_note: return "video_note", ""
    if msg.video:      return "video",      caption
    if msg.audio:      return "audio",      caption
    if msg.document:
        fname = ""
        for attr in getattr(msg.document, "attributes", []):
            if hasattr(attr, "file_name"):
                fname = attr.file_name
                break
        return "document", fname or caption
    return "text", caption


TYPE_EMOJI = {
    "photo":      "🖼",
    "sticker":    "🎭",
    "voice":      "🎤",
    "video_note": "⭕️",
    "video":      "🎥",
    "audio":      "🎵",
    "document":   "📎",
    "text":       "",
}

# Типы медиа которые скачиваем и пересылаем
MEDIA_DOWNLOAD = {"photo", "voice", "audio", "sticker"}


def format_message(name, username, chat_title, is_group,
                   msg_type, content, short_id) -> str:
    uname = f" (@{username})" if username else ""
    header = f"📢 {chat_title}" if is_group else "💬 Личный чат"
    sender = f"👤 {name}{uname}"
    div = "─" * 22

    emoji = TYPE_EMOJI.get(msg_type, "")
    if msg_type == "text":
        body = content or "(пустое сообщение)"
    elif content:
        body = f"{emoji} {content}"
    else:
        body = emoji + " " + {
            "photo": "Фотография", "sticker": "Стикер",
            "voice": "Голосовое", "video_note": "Видеосообщение",
            "video": "Видео", "audio": "Аудио", "document": "Файл",
        }.get(msg_type, msg_type)

    return f"{header}\n{sender}\n{div}\n{body}\n\n[#{short_id}]"


# ─── MAX polling loop ─────────────────────────────────────────────────────────
async def poll_max(tg_client: TelegramClient, session: aiohttp.ClientSession):
    global _max_chat_id, _max_marker

    while True:
        try:
            params = {"timeout": 25}
            if _max_marker:
                params["marker"] = _max_marker
            data = await _max_get(session, "/updates", params)
            if data.get("marker"):
                _max_marker = data["marker"]
                _save_state()
            updates = data.get("updates", [])

            for upd in updates:
                if upd.get("update_type") != "message_created":
                    continue

                msg     = upd.get("message", {})
                body    = msg.get("body", {})
                text    = body.get("text", "").strip()
                chat    = msg.get("recipient", {})
                chat_id = chat.get("chat_id")

                if chat_id:
                    _max_chat_id = chat_id
                    _save_state()

                if not text:
                    continue

                if text in ("/start", "/help"):
                    await send_to_max(session,
                        "👋 Telegram Relay активен!\n\n"
                        "Все входящие сообщения из Telegram появляются здесь.\n"
                        "Пересылаются: текст, фото, аудио, голосовые.\n\n"
                        "Чтобы ответить:\n"
                        "#42 Текст ответа\n\n"
                        "Где 42 — номер в конце сообщения от TG.")
                    continue

                if text.startswith("#"):
                    parts = text[1:].split(" ", 1)
                    if parts[0].isdigit() and len(parts) == 2:
                        sid   = int(parts[0])
                        reply = parts[1]
                        tg_chat = _id_map.get(sid)
                        if tg_chat:
                            try:
                                await tg_client.send_message(tg_chat, reply)
                                await send_to_max(session, f"✅ Ответ отправлен [#{sid}]")
                            except Exception as e:
                                await send_to_max(session, f"❌ Ошибка: {e}")
                        else:
                            await send_to_max(session,
                                f"❌ Чат #{sid} не найден — история очищена или ID неверный")
                        continue

        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[MAX poll] Ошибка: {e}")
            await asyncio.sleep(5)


# ─── Telegram listener ────────────────────────────────────────────────────────
async def main():
    _load_state()

    tg = TelegramClient(SESSION, TG_API_ID, TG_API_HASH, proxy=PROXY)
    await tg.start()

    me = await tg.get_me()
    print(f"[TG] Авторизован как {me.first_name} (@{me.username})")

    async with aiohttp.ClientSession() as http:
        bot_info = await _max_get(http, "/me")
        print(f"[MAX] Бот: {bot_info.get('name', '?')}")
        if _max_chat_id:
            print(f"[MAX] Чат с пользователем: {_max_chat_id}")
        else:
            print("[MAX] Ожидаю первое сообщение от пользователя в MAX боте...")

        @tg.on(events.NewMessage(incoming=True))
        async def on_new(event):
            try:
                msg    = event.message
                sender = await event.get_sender()
                chat   = await event.get_chat()

                if getattr(sender, "bot", False):
                    return

                name, username = _sender_name(sender)
                is_group   = not isinstance(chat, User)
                chat_title = getattr(chat, "title", name)

                if chat_title in BLOCKED_CHATS:
                    return

                msg_type, content = _msg_type_text(msg)
                short_id = _register(msg.chat_id)

                caption = format_message(
                    name, username, chat_title,
                    is_group, msg_type, content, short_id
                )

                # ── Фото ──────────────────────────────────────────────────────
                if msg_type == "photo":
                    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                        tmp_path = tmp.name
                    try:
                        await tg.download_media(msg, file=tmp_path)
                        await send_image_to_max(http, caption, tmp_path)
                        print(f"[TG→MAX] #{short_id} фото от {name}")
                    finally:
                        try: os.unlink(tmp_path)
                        except: pass
                    return

                # ── Голосовое сообщение ───────────────────────────────────────
                elif msg_type == "voice":
                    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
                        tmp_path = tmp.name
                    try:
                        await tg.download_media(msg, file=tmp_path)
                        await send_file_to_max(http, caption, tmp_path,
                                               f"voice_{short_id}.ogg", "audio/ogg")
                        print(f"[TG→MAX] #{short_id} голосовое от {name}")
                    finally:
                        try: os.unlink(tmp_path)
                        except: pass
                    return

                # ── Аудио файл ────────────────────────────────────────────────
                elif msg_type == "audio":
                    # Определяем имя файла из атрибутов
                    fname = f"audio_{short_id}.mp3"
                    for attr in getattr(msg.audio, "attributes", []):
                        if hasattr(attr, "file_name") and attr.file_name:
                            fname = attr.file_name
                            break
                    ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else "mp3"
                    mime_map = {"mp3": "audio/mpeg", "m4a": "audio/mp4",
                                "ogg": "audio/ogg", "flac": "audio/flac",
                                "wav": "audio/wav"}
                    mime = mime_map.get(ext, "audio/mpeg")
                    with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
                        tmp_path = tmp.name
                    try:
                        await tg.download_media(msg, file=tmp_path)
                        await send_file_to_max(http, caption, tmp_path, fname, mime)
                        print(f"[TG→MAX] #{short_id} аудио от {name}: {fname}")
                    finally:
                        try: os.unlink(tmp_path)
                        except: pass
                    return

                # ── Стикер → как изображение ──────────────────────────────────
                elif msg_type == "sticker":
                    with tempfile.NamedTemporaryFile(suffix=".webp", delete=False) as tmp:
                        tmp_path = tmp.name
                    try:
                        await tg.download_media(msg, file=tmp_path)
                        # Конвертируем webp → jpg через Pillow если доступен
                        jpg_path = tmp_path.replace(".webp", ".jpg")
                        converted = False
                        try:
                            from PIL import Image
                            img = Image.open(tmp_path).convert("RGBA")
                            bg = Image.new("RGB", img.size, (255, 255, 255))
                            bg.paste(img, mask=img.split()[3])
                            bg.save(jpg_path, "JPEG")
                            converted = True
                        except Exception:
                            pass
                        send_path = jpg_path if converted else tmp_path
                        if converted:
                            await send_image_to_max(http, caption, send_path)
                        else:
                            await send_to_max(http, caption)
                        print(f"[TG→MAX] #{short_id} стикер от {name}")
                    finally:
                        for p in [tmp_path, tmp_path.replace(".webp", ".jpg")]:
                            try: os.unlink(p)
                            except: pass
                    return

                # ── Всё остальное (текст, видео, документ) ────────────────────
                else:
                    await send_to_max(http, caption)
                    print(f"[TG→MAX] #{short_id} от {name}: {content[:60]}")

            except Exception as e:
                print(f"[TG→MAX] Ошибка: {e}")

        poll_task = asyncio.create_task(poll_max(tg, http))
        print("[RELAY] Запущен. Ctrl+C для остановки.")
        await tg.run_until_disconnected()
        poll_task.cancel()


if __name__ == "__main__":
    asyncio.run(main())
