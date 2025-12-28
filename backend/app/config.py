"""Application configuration"""
import os

# Downloads directory
DOWNLOADS_DIR = os.getenv("DOWNLOADS_DIR", "downloads")

# File validity in days
FILE_VALIDITY_DAYS = int(os.getenv("FILE_VALIDITY_DAYS", "3"))

# CORS settings
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")

# API settings
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))

# Telegram Bot settings
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_BOT_ENABLED = os.getenv("TELEGRAM_BOT_ENABLED", "true").lower() == "true"
# Channel ID for sending large files (up to 2GB)
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")

# MTProto settings for large files (up to 2GB)
TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH")
TELEGRAM_SESSION_STRING = os.getenv("TELEGRAM_SESSION_STRING")
# Default to localhost if API_HOST is 0.0.0.0 (for local development)
default_host = "localhost" if API_HOST == "0.0.0.0" else API_HOST
TELEGRAM_API_BASE_URL = os.getenv("TELEGRAM_API_BASE_URL", f"http://{default_host}:{API_PORT}")

