"""Download service for handling YouTube downloads"""
import os
import uuid
import threading
import yt_dlp
from typing import Dict, Optional
from ..config import DOWNLOADS_DIR
from ..utils.file_utils import find_files_by_id


class DownloadService:
    """Service for managing video downloads"""
    
    def __init__(self, progress_tracker: Dict):
        self.progress_tracker = progress_tracker
        self.downloads_dir = DOWNLOADS_DIR
    
    def start_download(
        self,
        url: str,
        format_id: Optional[str] = None,
        file_id: Optional[str] = None
    ) -> str:
        """Start a download and return file_id"""
        if file_id is None:
            file_id = str(uuid.uuid4())
        
        # Initialize progress tracking
        self.progress_tracker[file_id] = {
            'status': 'starting',
            'downloaded_bytes': 0,
            'total_bytes': 0,
            'percentage': 0,
            'speed': 0,
            'eta': 0,
            'filename': '',
            'ext': 'mp4',
            'filesize': 0,
            'cancelled': False
        }
        
        # Start download in background thread
        thread = threading.Thread(
            target=self._download_in_background,
            args=(file_id, url, format_id)
        )
        thread.daemon = True
        thread.start()
        
        return file_id
    
    def _download_in_background(
        self,
        file_id: str,
        url: str,
        format_id: Optional[str]
    ) -> None:
        """Download video in background thread"""
        try:
            def progress_hook(d):
                # Check if cancelled
                if self.progress_tracker[file_id].get('cancelled', False):
                    raise Exception('Download cancelled by user')
                
                if d['status'] == 'downloading':
                    total = d.get('total_bytes', 0) or d.get('total_bytes_estimate', 0) or 1
                    downloaded = d.get('downloaded_bytes', 0)
                    self.progress_tracker[file_id].update({
                        'status': 'downloading',
                        'downloaded_bytes': downloaded,
                        'total_bytes': total,
                        'percentage': (downloaded * 100) / total if total > 0 else 0,
                        'speed': d.get('speed', 0) or 0,
                        'eta': d.get('eta', 0) or 0
                    })
                elif d['status'] == 'finished':
                    self.progress_tracker[file_id]['status'] = 'finished'
            
            # Use simple format selection to avoid ffmpeg requirement
            format_string = format_id if format_id else 'best'
            
            ydl_opts = {
                'format': format_string,
                'outtmpl': os.path.join(self.downloads_dir, f'{file_id}.%(ext)s'),
                'quiet': True,
                'no_warnings': True,
                'progress_hooks': [progress_hook],
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
                info = ydl.extract_info(url, download=True)
                ext = info.get('ext', 'mp4')
                filename = info.get('title', 'video') + '.' + ext
                filepath = os.path.join(self.downloads_dir, f'{file_id}.{ext}')
                
                # Get file size
                filesize = 0
                if os.path.exists(filepath):
                    filesize = os.path.getsize(filepath)
                
                # Update final info
                self.progress_tracker[file_id].update({
                    'status': 'completed',
                    'filename': filename,
                    'ext': ext,
                    'filesize': filesize,
                    'percentage': 100
                })
        except Exception as e:
            # Cleanup partial download
            for f in os.listdir(self.downloads_dir):
                if f.startswith(file_id):
                    try:
                        os.remove(os.path.join(self.downloads_dir, f))
                    except:
                        pass
            
            if self.progress_tracker[file_id].get('cancelled', False):
                self.progress_tracker[file_id].update({
                    'status': 'cancelled',
                    'error': 'Download cancelled'
                })
            else:
                self.progress_tracker[file_id].update({
                    'status': 'error',
                    'error': str(e)
                })
    
    def cancel_download(self, file_id: str) -> bool:
        """Cancel a download in progress"""
        if file_id in self.progress_tracker:
            self.progress_tracker[file_id]['cancelled'] = True
            return True
        return False
    
    def get_progress(self, file_id: str) -> Dict:
        """Get download progress for a file"""
        if file_id in self.progress_tracker:
            return self.progress_tracker[file_id]
        return {'status': 'unknown', 'percentage': 0}

