#!/usr/bin/env python3
"""
Авторизация второго TG аккаунта (ИП Варфоломеев).
Запустить один раз: PROXY_TYPE=socks5 PROXY_HOST=127.0.0.1 PROXY_PORT=7891 venv/bin/python auth2.py
"""
import os
from telethon.sync import TelegramClient

TG_API_ID   = int(os.environ.get("TG_API_ID2", "0"))
TG_API_HASH = os.environ.get("TG_API_HASH2", "")


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

with TelegramClient("tg_session2", TG_API_ID, TG_API_HASH, proxy=proxy) as client:
    client.start()
    me = client.get_me()
    print(f"\n Авторизован как: {me.first_name} (@{me.username})")
    print("Файл tg_session2.session создан. Запускайте tg-relay2.service")
