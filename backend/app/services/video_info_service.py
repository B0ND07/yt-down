"""Service for fetching video information"""
import yt_dlp
import os
from typing import Dict, List

# FFmpeg location
FFMPEG_LOCATION = r"C:\ffmpeg\ffmpeg.exe"
if not os.path.exists(FFMPEG_LOCATION):
    FFMPEG_LOCATION = None

class VideoInfoService:
    """Service for retrieving video metadata"""
    
    @staticmethod
    def get_playlist_info(url: str) -> Dict:
        """Get playlist information and all videos"""
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,  # Don't download, just get metadata
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # Check if it's a playlist
            if 'entries' not in info:
                # It's a single video, return as single-item playlist
                return {
                    'is_playlist': False,
                    'title': info.get('title', 'Unknown'),
                    'videos': [{
                        'id': info.get('id'),
                        'title': info.get('title', 'Unknown'),
                        'url': url,
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
    
    @staticmethod
    def get_video_info(url: str) -> Dict:
        """Get video information and available formats"""
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }
        
        if FFMPEG_LOCATION:
            ydl_opts['ffmpeg_location'] = FFMPEG_LOCATION
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # Extract relevant format information
            formats = []
            seen_qualities = set()
            
            for f in info.get('formats', []):
                has_video = f.get('vcodec') and f.get('vcodec') != 'none'
                has_audio = f.get('acodec') and f.get('acodec') != 'none'
                
                # Include all video formats and audio-only formats
                # yt-dlp will merge video+audio automatically using built-in tools
                if has_video or (not has_video and has_audio):
                    quality_label = f.get('format_note', f.get('quality', 'unknown'))
                    
                    # Better resolution detection
                    height = f.get('height')
                    width = f.get('width')
                    if height and width:
                        resolution = f"{width}x{height}"
                    elif height:
                        resolution = f"{height}p"
                    else:
                        resolution = 'audio only' if not has_video else 'unknown'
                    
                    ext = f.get('ext', 'mp4')
                    filesize = f.get('filesize') or f.get('filesize_approx') or 0
                    fps = f.get('fps')
                    
                    # Always use format_id in the key to ensure uniqueness
                    # This prevents deduplication of different formats with same resolution/fps
                    quality_key = f.get('format_id')
                    
                    # Only add if we haven't seen this exact format_id yet
                    if quality_key not in seen_qualities:
                        formats.append({
                            'format_id': f.get('format_id'),
                            'quality': quality_label,
                            'resolution': resolution,
                            'ext': ext,
                            'filesize': filesize,
                            'fps': fps,
                            'vcodec': f.get('vcodec'),
                            'acodec': f.get('acodec'),
                            'has_video': has_video,
                            'has_audio': has_audio,
                            'height': height,
                        })
                        seen_qualities.add(quality_key)
            
            # Sort formats by resolution (height) and fps
            formats.sort(key=lambda x: (
                x['height'] if x.get('height') else 0,
                x['fps'] if x.get('fps') else 0
            ), reverse=True)
            
            return {
                'title': info.get('title', 'Unknown'),
                'thumbnail': info.get('thumbnail', ''),
                'duration': info.get('duration', 0),
                'formats': formats[:20]  # Limit to top 20 formats for Telegram (limit is 100 buttons)
            }
    
    @staticmethod
    def get_direct_link(url: str, format_id: str = None) -> Dict:
        """Get Direct stream link without downloading to server"""
        format_string = format_id if format_id else 'best'
        
        ydl_opts = {
            'format': format_string,
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
        
        if FFMPEG_LOCATION:
            ydl_opts['ffmpeg_location'] = FFMPEG_LOCATION
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # Get the direct URL
            url_direct = info.get('url')
            
            if not url_direct:
                raise ValueError("Could not get direct link")
            
            return {
                'success': True,
                'direct_url': url_direct,
                'title': info.get('title', 'video'),
                'ext': info.get('ext', 'mp4')
            }
