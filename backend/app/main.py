"""Main application entry point"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import CORS_ORIGINS, DOWNLOADS_DIR, FILE_VALIDITY_DAYS
from .routers import api
from .utils.file_utils import cleanup_old_files
import os

# Create downloads directory
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

# Initialize FastAPI app
app = FastAPI(title="YouTube Downloader API")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(api.router)

# Cleanup old files on startup
cleanup_old_files(DOWNLOADS_DIR, FILE_VALIDITY_DAYS)


if __name__ == "__main__":
    import uvicorn
    from .config import API_HOST, API_PORT
    uvicorn.run(app, host=API_HOST, port=API_PORT)


