"""API routes"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from typing import List
import os
import uuid
import yt_dlp
import sys

from ..models.schemas import (
    VideoURL,
    DownloadRequest,
    BatchDownloadRequest,
    CreateZipRequest
)
from ..services.download_service import DownloadService
from ..services.video_info_service import VideoInfoService
from ..services.zip_service import ZipService
from ..config import DOWNLOADS_DIR
from ..utils.file_utils import find_files_by_id, cleanup_old_files, cleanup_all_files

# Progress tracking (in-memory, could be moved to Redis in production)
progress_tracker = {}

# Initialize services
download_service = DownloadService(progress_tracker)
video_info_service = VideoInfoService()
zip_service = ZipService()

router = APIRouter(prefix="/api", tags=["api"])


@router.get("/")
async def root():
    return {"message": "YouTube Downloader API"}


@router.post("/playlist-info")
async def get_playlist_info(video: VideoURL):
    """Get playlist information and all videos"""
    try:
        return video_info_service.get_playlist_info(video.url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/video-info")
async def get_video_info(video: VideoURL):
    """Get video information and available formats"""
    try:
        # Force flush to ensure logs appear immediately
        print(f"DEBUG WEB API: Requesting video info for URL: {video.url[:100]}...", flush=True)
        sys.stdout.flush()
        result = video_info_service.get_video_info(video.url)
        formats_count = len(result.get('formats', []))
        print(f"DEBUG WEB API: Returning {formats_count} formats", flush=True)
        print(f"DEBUG WEB API: Format details (first 10):", flush=True)
        for idx, fmt in enumerate(result.get('formats', [])[:10], 1):
            fmt_id = fmt.get('format_id', 'NO_ID')
            fmt_size = fmt.get('filesize') or 'NO_SIZE'
            print(f"  Format {idx}: {fmt.get('resolution')} {fmt.get('ext')} id={fmt_id} size={fmt_size} has_video={fmt.get('has_video')} has_audio={fmt.get('has_audio')}", flush=True)
        sys.stdout.flush()
        return result
    except Exception as e:
        print(f"DEBUG WEB API: Error getting video info: {e}", flush=True)
        import traceback
        traceback.print_exc()
        sys.stdout.flush()
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/download")
async def download_video(request: DownloadRequest):
    """Download video and return file ID immediately"""
    
    # Cleanup: remove all previous files before new download
    cleanup_all_files(DOWNLOADS_DIR)
    
    # Also cleanup old files (3+ days old)
    cleanup_old_files(DOWNLOADS_DIR, 3)
    
    # Start download
    file_id = download_service.start_download(
        url=request.url,
        format_id=request.format_id
    )
    
    return {
        'success': True,
        'file_id': file_id,
        'message': 'Download started'
    }


@router.get("/progress/{file_id}")
async def get_progress(file_id: str):
    """Get download progress for a file"""
    return download_service.get_progress(file_id)


@router.post("/cancel/{file_id}")
async def cancel_download(file_id: str):
    """Cancel a download in progress"""
    success = download_service.cancel_download(file_id)
    if success:
        return {'success': True, 'message': 'Download cancelled'}
    return {'success': False, 'message': 'Download not found'}


@router.post("/cleanup")
async def manual_cleanup():
    """Manually cleanup old files"""
    cleanup_old_files(DOWNLOADS_DIR, 3)
    return {'success': True, 'message': 'Cleanup completed'}


@router.get("/download-file/{file_id}")
async def download_file(file_id: str):
    """Serve the downloaded file"""
    try:
        # Find the file with this ID
        files = find_files_by_id(DOWNLOADS_DIR, file_id)
        
        if not files:
            raise HTTPException(status_code=404, detail="File not found")
        
        filepath = os.path.join(DOWNLOADS_DIR, files[0])
        
        return FileResponse(
            filepath,
            media_type='application/octet-stream',
            filename=files[0]
        )
    
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/direct-link")
async def get_direct_link(request: DownloadRequest):
    """Get Direct stream link without downloading to server"""
    try:
        return video_info_service.get_direct_link(
            url=request.url,
            format_id=request.format_id
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/batch-download")
async def batch_download(request: BatchDownloadRequest):
    """Download multiple videos and create a zip file"""
    try:
        results = []
        downloaded_files = []
        
        for video_url in request.urls:
            try:
                # Generate unique filename
                file_id = str(uuid.uuid4())
                
                # Use simple format selection
                format_string = request.format_id if request.format_id else 'best'
                
                ydl_opts = {
                    'format': format_string,
                    'outtmpl': os.path.join(DOWNLOADS_DIR, f'{file_id}.%(ext)s'),
                    'quiet': True,
                    'no_warnings': True,
                    # Add headers to avoid 403 errors
                    'http_headers': {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                        'Accept-Language': 'en-us,en;q=0.5',
                        'Accept-Encoding': 'gzip, deflate',
                        'Connection': 'keep-alive',
                        'Referer': 'https://www.youtube.com/',
                    },
                    # Additional options to avoid blocking - try multiple player clients
                    'extractor_args': {
                        'youtube': {
                            'player_client': ['android', 'ios', 'web'],
                            'player_skip': ['webpage', 'configs'],
                        }
                    },
                    # Retry options
                    'retries': 10,
                    'fragment_retries': 10,
                }
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(video_url, download=True)
                    ext = info.get('ext', 'mp4')
                    filename = f'{file_id}.{ext}'
                    filepath = os.path.join(DOWNLOADS_DIR, filename)
                    
                    # Verify file exists
                    if not os.path.exists(filepath):
                        # Try to find the file with this ID
                        files = find_files_by_id(DOWNLOADS_DIR, file_id)
                        if files:
                            filename = files[0]
                            filepath = os.path.join(DOWNLOADS_DIR, filename)
                    
                    if os.path.exists(filepath):
                        safe_title = "".join(c for c in info.get('title', 'video') if c.isalnum() or c in (' ', '-', '_')).strip()
                        results.append({
                            'success': True,
                            'url': video_url,
                            'file_id': file_id,
                            'filename': safe_title + '.' + ext,
                            'download_url': f'/api/download-file/{file_id}',
                            'title': info.get('title', 'video'),
                            'ext': ext,
                            'filepath': filepath,
                            'original_filename': safe_title + '.' + ext
                        })
                        downloaded_files.append({
                            'path': filepath,
                            'name': safe_title + '.' + ext
                        })
                    else:
                        raise Exception(f"File not found after download: {filepath}")
            except Exception as e:
                results.append({
                    'success': False,
                    'url': video_url,
                    'error': str(e)
                })
        
        # Create a zip file if there are successful downloads
        zip_id = None
        if downloaded_files:
            zip_id = zip_service.create_batch_zip(downloaded_files)
        
        return {
            'total': len(request.urls),
            'successful': len([r for r in results if r.get('success')]),
            'failed': len([r for r in results if not r.get('success')]),
            'results': results,
            'zip_available': zip_id is not None,
            'zip_id': zip_id,
            'zip_url': f'/api/download-file/{zip_id}' if zip_id else None
        }
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/create-zip")
async def create_zip(request: CreateZipRequest):
    """Create a ZIP file from downloaded files"""
    try:
        result = zip_service.create_zip(request.file_ids)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

