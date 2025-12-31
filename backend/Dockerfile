FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies (ffmpeg for video merging)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install additional dependencies for Telegram bot
RUN pip install --no-cache-dir \
    python-telegram-bot==20.7 \
    pyrogram==2.0.106 \
    TgCrypto==1.2.5 \
    nest_asyncio==1.6.0

# Copy application code
COPY . .

# Create downloads directory
RUN mkdir -p downloads

# Expose port
EXPOSE 8000

# Environment variables (can be overridden)
ENV DOWNLOADS_DIR=/app/downloads
ENV API_HOST=0.0.0.0
ENV API_PORT=8000
ENV TELEGRAM_BOT_ENABLED=true

# Run the application
CMD ["python", "server.py"]
