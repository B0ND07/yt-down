# YouTube Downloader

A full-stack YouTube video downloader with FastAPI backend, React frontend, and Telegram bot support.

## Features

- 🎥 Download YouTube videos in multiple qualities (up to 4K)
- 📺 Playlist download support
- 📊 Quality selector with file size information
- 🔗 Direct download link option
- 💾 Server download option
- 🎨 Modern, responsive UI
- ⚡ Fast and reliable
- 📲 **Telegram Bot** - Download videos via Telegram
- 📤 **Large File Support** - Upload files up to 2GB via Pyrogram
- 🐳 **Docker Support** - Easy deployment with Docker

## Tech Stack

### Backend
- FastAPI
- yt-dlp
- Python 3.11+
- python-telegram-bot
- Pyrogram (for large file uploads)
- FFmpeg (for video merging)

### Frontend
- React 18
- Axios
- CSS3

## Installation

### Option 1: Docker (Recommended)

```bash
# Clone the repository
git clone https://github.com/yourusername/yt-down.git
cd yt-down

# Copy and configure environment
cp .env.example .env
# Edit .env with your Telegram credentials

# Run with Docker Compose
docker-compose up -d --build
```

### Option 2: Manual Setup

#### Prerequisites
- Python 3.11 or higher
- Node.js 14 or higher
- FFmpeg installed
- npm or yarn

#### Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install python-telegram-bot pyrogram TgCrypto nest_asyncio

# Run the server
python main.py
```

The backend will start on `http://localhost:8000`

#### Frontend Setup

```bash
cd frontend
npm install
npm start
```

The frontend will start on `http://localhost:3000`

## Telegram Bot Setup

1. Create a bot with [@BotFather](https://t.me/BotFather)
2. Get your API credentials from [my.telegram.org](https://my.telegram.org)
3. Generate a session string using `pyrogram_session_gen.py`
4. Configure environment variables in `backend/app/config.py` or `.env`:

```env
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHANNEL_ID=-1001234567890
TELEGRAM_API_ID=your_api_id
TELEGRAM_API_HASH=your_api_hash
TELEGRAM_SESSION_STRING=your_session_string
```

### Bot Commands
- `/start` - Start the bot
- `/download <url>` - Download a video
- `/info <url>` - Get video info
- `/cancel` - Cancel current download
- `/clean` - Clean downloads folder and session data

## Usage

### Web Interface
1. Open `http://localhost:3000`
2. Paste a YouTube URL
3. Select quality and download

### Telegram Bot
1. Send a YouTube URL to the bot
2. Select quality from the buttons
3. Choose "Send File to Channel" or "Get Download Link"

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/video-info` | Get video information |
| POST | `/api/download` | Download video to server |
| POST | `/api/direct-link` | Get direct download link |
| GET | `/api/download-file/{file_id}` | Download file from server |
| GET | `/api/progress/{file_id}` | Get download progress |

## Project Structure

```
yt-down/
├── backend/
│   ├── app/
│   │   ├── config.py              # Configuration
│   │   └── services/
│   │       ├── telegram_service.py # Telegram bot
│   │       └── video_info_service.py
│   ├── main.py                    # FastAPI app
│   ├── Dockerfile                 # Docker config
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.js
│   │   └── App.css
│   └── package.json
├── docker-compose.yml
└── README.md
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `TELEGRAM_BOT_TOKEN` | Telegram bot token | - |
| `TELEGRAM_CHANNEL_ID` | Channel for large files | - |
| `TELEGRAM_API_ID` | Telegram API ID | - |
| `TELEGRAM_API_HASH` | Telegram API Hash | - |
| `TELEGRAM_SESSION_STRING` | Pyrogram session | - |
| `API_PORT` | Backend port | 8000 |

## License

MIT

## Disclaimer

This tool is for educational purposes only. Please respect YouTube's Terms of Service and copyright laws.
