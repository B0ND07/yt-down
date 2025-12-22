from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
import yt_dlp
import os
import uuid
from typing import List, Optional
import json
import zipfile
import shutil
import threading

app = FastAPI(title="YouTube Downloader API")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create downloads directory
DOWNLOADS_DIR = "downloads"
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

# Progress tracking
progress_tracker = {}


class VideoURL(BaseModel):
    url: str


class DownloadRequest(BaseModel):
    url: str
    quality: Optional[str] = None
    format_id: Optional[str] = None


class BatchDownloadRequest(BaseModel):
    urls: List[str]
    quality: Optional[str] = None
    format_id: Optional[str] = None


class CreateZipRequest(BaseModel):
    file_ids: List[str]


class VideoInfo(BaseModel):
    title: str
    thumbnail: str
    duration: int
    formats: List[dict]


@app.get("/")
async def root():
    return {"message": "YouTube Downloader API"}


@app.post("/api/playlist-info")
async def get_playlist_info(video: VideoURL):
    """Get playlist information and all videos"""
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,  # Don't download, just get metadata
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video.url, download=False)
            
            # Check if it's a playlist
            if 'entries' not in info:
                # It's a single video, return as single-item playlist
                return {
                    'is_playlist': False,
                    'title': info.get('title', 'Unknown'),
                    'videos': [{
                        'id': info.get('id'),
                        'title': info.get('title', 'Unknown'),
                        'url': video.url,
                        'thumbnail': info.get('thumbnail', ''),
                        'duration': info.get('duration', 0),
                    }]
                }
            
            # It's a playlist
            videos = []
            for entry in info['entries']:
                if entry:  # Some entries might be None
                    videos.append({
                        'id': entry.get('id'),
                        'title': entry.get('title', 'Unknown'),
                        'url': f"https://www.youtube.com/watch?v={entry.get('id')}",
                        'thumbnail': entry.get('thumbnails', [{}])[0].get('url', '') if entry.get('thumbnails') else '',
                        'duration': entry.get('duration', 0),
                    })
            
            return {
                'is_playlist': True,
                'title': info.get('title', 'Playlist'),
                'video_count': len(videos),
                'videos': videos
            }
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/video-info")
async def get_video_info(video: VideoURL):
    """Get video information and available formats"""
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video.url, download=False)
            
            # Extract relevant format information
            formats = []
            seen_qualities = set()
            
            for f in info.get('formats', []):
                # Prioritize formats with both video and audio (no ffmpeg needed)
                has_video = f.get('vcodec') and f.get('vcodec') != 'none'
                has_audio = f.get('acodec') and f.get('acodec') != 'none'
                
                # Only include formats that have both audio and video, or audio-only
                if (has_video and has_audio) or (not has_video and has_audio):
                    quality_label = f.get('format_note', f.get('quality', 'unknown'))
                    resolution = f.get('resolution', 'audio only')
                    ext = f.get('ext', 'mp4')
                    filesize = f.get('filesize') or f.get('filesize_approx') or 0
                    
                    # Create a unique key for this quality
                    quality_key = f"{resolution}_{ext}"
                    
                    # Only add if we haven't seen this quality yet
                    if quality_key not in seen_qualities:
                        formats.append({
                            'format_id': f.get('format_id'),
                            'quality': quality_label,
                            'resolution': resolution,
                            'ext': ext,
                            'filesize': filesize,
                            'fps': f.get('fps'),
                            'vcodec': f.get('vcodec'),
                            'acodec': f.get('acodec'),
                            'has_video': has_video,
                            'has_audio': has_audio,
                        })
                        seen_qualities.add(quality_key)
            
            # Sort formats by resolution
            formats.sort(key=lambda x: (
                x['resolution'] != 'audio only',
                int(x['resolution'].split('x')[0]) if 'x' in x['resolution'] else 0
            ), reverse=True)
            
            return {
                'title': info.get('title', 'Unknown'),
                'thumbnail': info.get('thumbnail', ''),
                'duration': info.get('duration', 0),
                'formats': formats[:15]  # Limit to top 15 formats
            }
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/download")
async def download_video(request: DownloadRequest):
    """Download video and return file ID immediately"""
    # Generate unique filename
    file_id = str(uuid.uuid4())
    
    # Initialize progress tracking
    progress_tracker[file_id] = {
        'status': 'starting',
        'downloaded_bytes': 0,
        'total_bytes': 0,
        'percentage': 0,
        'speed': 0,
        'eta': 0,
        'filename': '',
        'ext': 'mp4',
        'filesize': 0
    }
    
    def download_in_background():
        try:
            def progress_hook(d):
                if d['status'] == 'downloading':
                    total = d.get('total_bytes', 0) or d.get('total_bytes_estimate', 0) or 1
                    downloaded = d.get('downloaded_bytes', 0)
                    progress_tracker[file_id].update({
                        'status': 'downloading',
                        'downloaded_bytes': downloaded,
                        'total_bytes': total,
                        'percentage': (downloaded * 100) / total if total > 0 else 0,
                        'speed': d.get('speed', 0) or 0,
                        'eta': d.get('eta', 0) or 0
                    })
                elif d['status'] == 'finished':
                    progress_tracker[file_id]['status'] = 'finished'
            
            # Use simple format selection to avoid ffmpeg requirement
            if request.format_id:
                format_string = request.format_id
            else:
                format_string = 'best'
            
            ydl_opts = {
                'format': format_string,
                'outtmpl': os.path.join(DOWNLOADS_DIR, f'{file_id}.%(ext)s'),
                'quiet': True,
                'no_warnings': True,
                'progress_hooks': [progress_hook],
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(request.url, download=True)
                ext = info.get('ext', 'mp4')
                filename = info.get('title', 'video') + '.' + ext
                filepath = os.path.join(DOWNLOADS_DIR, f'{file_id}.{ext}')
                
                # Get file size
                filesize = 0
                if os.path.exists(filepath):
                    filesize = os.path.getsize(filepath)
                
                # Update final info
                progress_tracker[file_id].update({
                    'status': 'completed',
                    'filename': filename,
                    'ext': ext,
                    'filesize': filesize,
                    'percentage': 100
                })
        except Exception as e:
            progress_tracker[file_id].update({
                'status': 'error',
                'error': str(e)
            })
    
    # Start download in background thread
    thread = threading.Thread(target=download_in_background)
    thread.daemon = True
    thread.start()
    
    # Return file_id immediately
    return {
        'success': True,
        'file_id': file_id,
        'message': 'Download started'
    }


@app.get("/api/progress/{file_id}")
async def get_progress(file_id: str):
    """Get download progress for a file"""
    if file_id in progress_tracker:
        return progress_tracker[file_id]
    return {'status': 'unknown', 'percentage': 0}


@app.get("/api/download-file/{file_id}")
async def download_file(file_id: str):
    """Serve the downloaded file"""
    try:
        # Find the file with this ID
        files = [f for f in os.listdir(DOWNLOADS_DIR) if f.startswith(file_id)]
        
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


@app.post("/api/direct-link")
async def get_direct_link(request: DownloadRequest):
    """Get direct download link without downloading to server"""
    try:
        # Use simpler format selection to avoid needing ffmpeg for direct links
        if request.format_id:
            format_string = request.format_id
        else:
            format_string = 'best'
        
        ydl_opts = {
            'format': format_string,
            'quiet': True,
            'no_warnings': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(request.url, download=False)
            
            # Get the direct URL
            url = info.get('url')
            
            if not url:
                raise HTTPException(status_code=400, detail="Could not get direct link")
            
            return {
                'success': True,
                'direct_url': url,
                'title': info.get('title', 'video'),
                'ext': info.get('ext', 'mp4')
            }
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/batch-download")
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
                if request.format_id:
                    format_string = request.format_id
                else:
                    format_string = 'best'
                
                ydl_opts = {
                    'format': format_string,
                    'outtmpl': os.path.join(DOWNLOADS_DIR, f'{file_id}.%(ext)s'),
                    'quiet': True,
                    'no_warnings': True,
                }
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(video_url, download=True)
                    ext = info.get('ext', 'mp4')
                    filename = f'{file_id}.{ext}'
                    filepath = os.path.join(DOWNLOADS_DIR, filename)
                    
                    # Verify file exists
                    if not os.path.exists(filepath):
                        # Try to find the file with this ID
                        files = [f for f in os.listdir(DOWNLOADS_DIR) if f.startswith(file_id)]
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
            zip_id = str(uuid.uuid4())
            zip_path = os.path.join(DOWNLOADS_DIR, f'{zip_id}.zip')
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file_info in downloaded_files:
                    if os.path.exists(file_info['path']):
                        zipf.write(file_info['path'], arcname=file_info['name'])
        
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
        
        return {
            'total': len(request.urls),
            'successful': len([r for r in results if r.get('success')]),
            'failed': len([r for r in results if not r.get('success')]),
            'results': results
        }
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/create-zip")
async def create_zip(request: CreateZipRequest):
    """Create a ZIP file from downloaded files"""
    try:
        zip_id = str(uuid.uuid4())
        zip_path = os.path.join(DOWNLOADS_DIR, f'{zip_id}.zip')
        
        files_added = 0
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_id in request.file_ids:
                # Find the file with this ID
                files = [f for f in os.listdir(DOWNLOADS_DIR) if f.startswith(file_id)]
                
                if files:
                    filepath = os.path.join(DOWNLOADS_DIR, files[0])
                    if os.path.exists(filepath):
                        # Use a cleaner filename in the zip
                        zipf.write(filepath, arcname=files[0])
                        files_added += 1
        
        if files_added == 0:
            # Remove empty zip
            if os.path.exists(zip_path):
                os.remove(zip_path)
            raise HTTPException(status_code=404, detail="No files found to zip")
        
        return {
            'success': True,
            'zip_id': zip_id,
            'zip_url': f'/api/download-file/{zip_id}',
            'files_count': files_added
        }
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
