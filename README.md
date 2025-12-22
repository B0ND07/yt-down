# YouTube Downloader

A full-stack YouTube video downloader with FastAPI backend and React frontend.

## Features

- 🎥 Download YouTube videos in multiple qualities
- 📊 Quality selector with file size information
- 🔗 Direct download link option
- 💾 Server download option
- 🎨 Modern, responsive UI
- ⚡ Fast and reliable

## Tech Stack

### Backend
- FastAPI
- yt-dlp
- Python 3.8+

### Frontend
- React 18
- Axios
- CSS3

## Installation

### Prerequisites
- Python 3.8 or higher
- Node.js 14 or higher
- npm or yarn

### Backend Setup

1. Navigate to the backend directory:
```bash
cd backend
```

2. Create a virtual environment (optional but recommended):
```bash
python -m venv venv
# On Windows
venv\Scripts\activate
# On macOS/Linux
source venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Run the backend server:
```bash
python main.py
```

The backend will start on `http://localhost:8000`

### Frontend Setup

1. Navigate to the frontend directory:
```bash
cd frontend
```

2. Install dependencies:
```bash
npm install
```

3. Start the development server:
```bash
npm start
```

The frontend will start on `http://localhost:3000`

## Usage

1. Start both backend and frontend servers
2. Open your browser and go to `http://localhost:3000`
3. Paste a YouTube URL in the input field
4. Click "Get Video Info" to fetch available qualities
5. Select your preferred quality from the grid
6. Choose download method:
   - **Direct Download Link**: Opens the video stream URL directly (faster)
   - **Download via Server**: Downloads to server first, then to your device (more reliable)

## API Endpoints

### POST /api/video-info
Get video information and available formats
```json
{
  "url": "https://youtube.com/watch?v=..."
}
```

### POST /api/download
Download video to server
```json
{
  "url": "https://youtube.com/watch?v=...",
  "quality": "1080p",
  "format_id": "137"
}
```

### POST /api/direct-link
Get direct download link
```json
{
  "url": "https://youtube.com/watch?v=...",
  "quality": "1080p",
  "format_id": "137"
}
```

### GET /api/download-file/{file_id}
Download file from server

## Project Structure

```
yt-down/
├── backend/
│   ├── main.py           # FastAPI application
│   ├── requirements.txt  # Python dependencies
│   └── downloads/        # Downloaded files (auto-created)
├── frontend/
│   ├── public/
│   │   └── index.html
│   ├── src/
│   │   ├── App.js       # Main React component
│   │   ├── App.css      # Styles
│   │   ├── index.js     # Entry point
│   │   └── index.css    # Global styles
│   └── package.json     # Node dependencies
└── README.md
```

## Notes

- Downloaded files are stored in `backend/downloads/` directory
- The direct download link may expire after some time (YouTube limitation)
- Server downloads are more reliable but consume server storage
- Make sure both servers are running for the application to work

## License

MIT

## Disclaimer

This tool is for educational purposes only. Please respect YouTube's Terms of Service and copyright laws.
