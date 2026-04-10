#!/usr/bin/env python3
"""
Одноразовая авторизация Telegram-сессии.
Запустить один раз на сервере: python3 auth.py
Создаёт файл tg_session.session — больше запускать не нужно.

Настройка прокси — через переменные окружения:
  PROXY_TYPE=socks5 PROXY_HOST=1.2.3.4 PROXY_PORT=1080 python3 auth.py
"""
import os
from telethon.sync import TelegramClient

TG_API_ID   = int(os.environ.get("TG_API_ID", "0"))
TG_API_HASH = os.environ.get("TG_API_HASH", "")


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


proxy = _build_proxy()
if proxy:
    print(f"Использую прокси: {os.environ.get('PROXY_TYPE')} {os.environ.get('PROXY_HOST')}:{os.environ.get('PROXY_PORT')}")

with TelegramClient("tg_session", TG_API_ID, TG_API_HASH, proxy=proxy) as client:
    client.start()
    me = client.get_me()
    print(f"\n✅ Авторизован как: {me.first_name} (@{me.username})")
    print("Файл tg_session.session создан. Теперь запускайте relay.py")
