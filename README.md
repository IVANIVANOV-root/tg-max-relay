# Telegram → MAX Relay / Ретранслятор Telegram в MAX

A Python service that bridges a personal Telegram account with a MAX (Mail.ru) bot chat. All incoming Telegram messages (text, photos, voice, audio, stickers) are forwarded to MAX in real time. Replies sent from MAX in the format `#42 text` are delivered back to the original Telegram chat.

---

Python-сервис для пересылки входящих сообщений личного аккаунта Telegram в чат бота MAX (Mail.ru). Поддерживает текст, фото, голосовые, аудио и стикеры. Ответ из MAX в формате `#42 текст` пересылается обратно в нужный чат Telegram.

## Features / Возможности

- **Full message relay** — text, photos, voice messages, audio files, stickers
- **Reply from MAX** — respond to any Telegram chat using `#42 Reply text` syntax
- **Blocked chats** — configurable list of chats to ignore
- **State persistence** — chat ID mapping survives restarts (`relay_state.json`)
- **SOCKS5/HTTP proxy** — optional proxy support via env vars
- **systemd service** — production-ready `.service` files included

## Tech Stack

- **Python 3.11+**, asyncio
- **Telethon** — Telegram MTProto client
- **aiohttp** — async HTTP for MAX Bot API
- **MAX Bot API** — `https://botapi.max.ru`

## Setup

### 1. Install dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Get credentials

- **Telegram API**: [my.telegram.org](https://my.telegram.org) → API development tools → get `api_id` and `api_hash`
- **MAX Bot Token**: create a bot at [max.ru](https://max.ru) and get the token

### 3. Authorize Telegram session (one time)

```bash
export TG_API_ID=your_api_id
export TG_API_HASH=your_api_hash
python auth.py
# Enter your phone number and confirmation code
```

This creates `tg_session.session` — keep it safe, never commit it.

### 4. Run the relay

```bash
export TG_API_ID=your_api_id
export TG_API_HASH=your_api_hash
export MAX_TOKEN=your_max_bot_token
python relay.py
```

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `TG_API_ID` | Telegram app ID from my.telegram.org | Yes |
| `TG_API_HASH` | Telegram app hash | Yes |
| `MAX_TOKEN` | MAX bot token | Yes |
| `MAX_CHAT_ID` | Target MAX chat ID (auto-detected on first message) | No |
| `TG_SESSION` | Session file name (default: `tg_session`) | No |
| `PROXY_TYPE` | Proxy type: `socks5` or `http` | No |
| `PROXY_HOST` | Proxy host | No |
| `PROXY_PORT` | Proxy port | No |

## Systemd Deploy

```bash
sudo cp tg-relay.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tg-relay
```

## Reply Syntax

From MAX bot, send: `#42 Your reply text`

Where `42` is the short message ID shown at the bottom of each forwarded message.
