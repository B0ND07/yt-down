# Quick Telegram Bot Setup Guide

## Step 1: Get Bot Token

1. Open Telegram
2. Search for `@BotFather`
3. Send `/newbot`
4. Follow instructions to create your bot
5. Copy the bot token (e.g., `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

## Step 2: Configure Environment

### Windows (PowerShell)
```powershell
$env:TELEGRAM_BOT_TOKEN="your_bot_token_here"
$env:TELEGRAM_BOT_ENABLED="true"
```

### Linux/Mac
```bash
export TELEGRAM_BOT_TOKEN="your_bot_token_here"
export TELEGRAM_BOT_ENABLED="true"
```

### Using .env file (recommended)
Create `backend/.env`:
```
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_BOT_ENABLED=true
```

## Step 3: Install Dependencies

```bash
cd backend
pip install -r requirements.txt
```

## Step 4: Run the Bot

```bash
python bot.py
```

You should see:
```
🤖 Starting Telegram bot...
✅ Telegram bot is running!
```

## Step 5: Test

1. Open Telegram
2. Find your bot (search for the username you gave it)
3. Send `/start`
4. Send a YouTube URL
5. Select quality
6. Wait for download!

## Troubleshooting

**Bot not responding?**
- Check if token is correct
- Verify `TELEGRAM_BOT_ENABLED=true`
- Check console for errors

**Downloads failing?**
- Make sure `yt-dlp` is updated: `pip install --upgrade yt-dlp`
- Check internet connection
- Verify YouTube URL is accessible

**File too large?**
- Telegram has 50MB limit for bots
- Try lower quality format
- Use web interface for larger files


