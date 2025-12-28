"""Telegram bot service for handling YouTube downloads via Telegram"""
import os
import uuid
import asyncio
import base64
from typing import Dict, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)
import yt_dlp
try:
    from pyrogram import Client as PyrogramClient
    from pyrogram.enums import ParseMode as PyrogramParseMode
    HAS_PYROGRAM = True
except ImportError:
    HAS_PYROGRAM = False

from ..config import (
    DOWNLOADS_DIR, 
    TELEGRAM_API_BASE_URL, 
    TELEGRAM_CHANNEL_ID, 
    TELEGRAM_API_ID,
    TELEGRAM_API_HASH,
    TELEGRAM_SESSION_STRING
)
from ..utils.file_utils import find_files_by_id
from ..services.video_info_service import VideoInfoService

# FFmpeg location
FFMPEG_LOCATION = r"C:\ffmpeg\ffmpeg.exe"
if not os.path.exists(FFMPEG_LOCATION):
    FFMPEG_LOCATION = None


class ProgressReader:
    """Wrapper for file object to track read progress"""
    def __init__(self, filename, callback):
        self._filename = filename
        self._callback = callback
        self._f = open(filename, 'rb')
        self._total_size = os.path.getsize(filename)
        self._bytes_read = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def read(self, size=-1):
        data = self._f.read(size)
        if data:
            self._bytes_read += len(data)
            if self._callback:
                try:
                    self._callback(self._bytes_read, self._total_size)
                except:
                    pass
        return data

    def close(self):
        if self._f:
            self._f.close()
            self._f = None

    def __getattr__(self, name):
        return getattr(self._f, name)


# Helper functions for upload progress and file handling
def format_bytes(bytes_size):
    """Format bytes to human readable format"""
    if bytes_size < 1024:
        return f"{bytes_size}B"
    elif bytes_size < 1024 * 1024:
        return f"{bytes_size/1024:.1f}KB"
    elif bytes_size < 1024 * 1024 * 1024:
        return f"{bytes_size/(1024*1024):.2f}MB"
    else:
        return f"{bytes_size/(1024*1024*1024):.2f}GB"


def create_progress_bar(percentage, length=20):
    """Create a visual progress bar"""
    filled = int(length * percentage / 100)
    empty = length - filled
    return f"[{'█' * filled}{'░' * empty}]"


def split_file(file_path, chunk_size=int(1.95 * 1024 * 1024 * 1024)):
    """
    Split a large file into chunks.
    
    Args:
        file_path: Path to the file to split
        chunk_size: Size of each chunk in bytes (default 1.95GB)
    
    Returns:
        List of chunk file paths
    """
    MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB in bytes
    file_size = os.path.getsize(file_path)
    
    if file_size <= MAX_FILE_SIZE:
        # File is small enough, no splitting needed
        return [file_path]
    
    # Calculate number of parts needed
    num_parts = (file_size + chunk_size - 1) // chunk_size
    
    chunk_files = []
    base_name = os.path.basename(file_path)
    file_name, file_ext = os.path.splitext(base_name)
    
    print(f"Splitting file {base_name} ({format_bytes(file_size)}) into {num_parts} parts...")
    
    with open(file_path, 'rb') as source_file:
        for part_num in range(num_parts):
            # Create chunk filename
            chunk_filename = f"{file_name}.part{part_num + 1:03d}{file_ext}"
            chunk_path = os.path.join(os.path.dirname(file_path), chunk_filename)
            
            # Read and write chunk
            bytes_to_read = min(chunk_size, file_size - (part_num * chunk_size))
            
            with open(chunk_path, 'wb') as chunk_file:
                bytes_written = 0
                while bytes_written < bytes_to_read:
                    # Read in smaller blocks for memory efficiency
                    block_size = min(8192, bytes_to_read - bytes_written)
                    data = source_file.read(block_size)
                    if not data:
                        break
                    chunk_file.write(data)
                    bytes_written += len(data)
            
            chunk_files.append(chunk_path)
            print(f"Created chunk {part_num + 1}/{num_parts}: {chunk_filename} ({format_bytes(bytes_written)})")
    
    return chunk_files


class TelegramService:
    """Service for managing Telegram bot interactions"""
    
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.downloads_dir = DOWNLOADS_DIR
        self.api_base_url = TELEGRAM_API_BASE_URL
        self.channel_id = TELEGRAM_CHANNEL_ID  # Channel for sending large files (up to 2GB)
        self.video_info_service = VideoInfoService()
        self.active_downloads: Dict[str, Dict] = {}  # {user_id: {file_id, url, status}}
        self.completed_downloads: Dict[str, Dict] = {}  # {file_id: {filename, filesize, ext, user_id}}
        self.pending_downloads: Dict[str, str] = {}  # {download_id: url} - Store URLs for callback
        self.application = None
        self.pyrogram_client = None
        
        # Progress tracking for file uploads
        self.current_file_progress = {"uploaded": 0, "total": 0, "percentage": 0}
        self.current_file_name = "Unknown"
        self.progress_message = None
        self.progress_start_time = None
        self.last_progress_update = None
        
        # Initialize Pyrogram client if config is available
        if HAS_PYROGRAM and TELEGRAM_API_ID and TELEGRAM_API_HASH and TELEGRAM_SESSION_STRING:
            try:
                self.pyrogram_client = PyrogramClient(
                    "yt_down_userbot",
                    api_id=int(TELEGRAM_API_ID),
                    api_hash=TELEGRAM_API_HASH,
                    session_string=TELEGRAM_SESSION_STRING,
                    no_updates=True,  # We only need it for uploading
                    in_memory=True # Avoid disk lock issues
                )
                print("✅ Pyrogram Client (Userbot) configured")
            except Exception as e:
                print(f"⚠️ Failed to configure Pyrogram Client: {e}")
    
    def _cleanup_downloads(self):
        """Remove all files from downloads directory"""
        try:
            for filename in os.listdir(self.downloads_dir):
                filepath = os.path.join(self.downloads_dir, filename)
                if os.path.isfile(filepath):
                    os.remove(filepath)
            print("🧹 Cleaned up previous downloads")
        except Exception as e:
            print(f"Error during cleanup: {e}")
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command"""
        print(f"📨 Received /start command from user {update.effective_user.id}")
        try:
            welcome_message = (
                "🎬 Welcome to YouTube Downloader Bot!\n\n"
                "📋 Available commands:\n"
                "/start - Show this help message\n"
                "/download <url> - Download a YouTube video\n"
                "/info <url> - Get video information\n"
                "/cancel - Cancel current download\n\n"
                "💡 You can also just send me a YouTube URL directly!\n\n"
                "📥 After download, choose:\n"
                "• Send file via Telegram (for files < 50MB)\n"
                "• Get download link (for any file size)"
            )
            await update.message.reply_text(welcome_message)
            print(f"✅ Sent welcome message to user {update.effective_user.id}")
        except Exception as e:
            print(f"❌ Error in start_command: {e}")
            import traceback
            traceback.print_exc()
            try:
                await update.message.reply_text("❌ Error: Could not send message. Please try again.")
            except:
                pass
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command"""
        help_text = (
            "📖 How to use:\n\n"
            "1️⃣ Send a YouTube URL (video or playlist)\n"
            "2️⃣ Select quality/format\n"
            "3️⃣ Choose download method:\n"
            "   📤 Send via Telegram (for files < 50MB)\n"
            "   🔗 Get download link (for any file size)\n\n"
            "Commands:\n"
            "/start - Start the bot\n"
            "/download <url> - Download video\n"
            "/info <url> - Get video info\n"
            "/cancel - Cancel download\n\n"
            "💡 Tip: Large files (>50MB) will automatically use download links"
        )
        await update.message.reply_text(help_text)
    
    async def info_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /info command"""
        if not context.args:
            await update.message.reply_text("❌ Please provide a YouTube URL.\nUsage: /info <url>")
            return
        
        url = context.args[0]
        await self._send_video_info(update, url)
    
    async def download_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /download command"""
        if not context.args:
            await update.message.reply_text("❌ Please provide a YouTube URL.\nUsage: /download <url>")
            return
        
        # Join all args in case URL has spaces or special characters
        url = " ".join(context.args)
        print(f"DEBUG download_command: Received URL: {url}")
        print(f"DEBUG download_command: URL type: {type(url)}, length: {len(url)}")
        
        if not url or not isinstance(url, str):
            await update.message.reply_text(f"❌ Invalid URL type: {type(url)}")
            return
        
        if not url.startswith(('http://', 'https://')):
            await update.message.reply_text(f"❌ Invalid URL format. Must start with http:// or https://")
            return
        
        await self._handle_video_url(update, url)
    
    async def cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /cancel command"""
        user_id = str(update.effective_user.id)
        
        if user_id in self.active_downloads:
            download_info = self.active_downloads[user_id]
            # Mark as cancelled (actual cancellation would need download service integration)
            del self.active_downloads[user_id]
            await update.message.reply_text("✅ Download cancelled")
        else:
            await update.message.reply_text("❌ No active download to cancel")
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle text messages (YouTube URLs)"""
        print(f"📨 Received message from user {update.effective_user.id}: {update.message.text[:50]}")
        text = update.message.text
        
        # Check if it's a YouTube URL
        if "youtube.com" in text or "youtu.be" in text:
            await self._handle_video_url(update, text)
        else:
            await update.message.reply_text(
                "❌ Please send a valid YouTube URL or use /help for commands."
            )
    
    async def _handle_video_url(self, update: Update, url: str) -> None:
        """Handle YouTube URL - get info and show format options"""
        message = await update.message.reply_text("🔍 Fetching video information...")
        
        try:
            # Get video info using EXACTLY the same service method as web API
            # This ensures Telegram shows the same formats as the web interface
            loop = asyncio.get_event_loop()
            video_info = await loop.run_in_executor(None, self.video_info_service.get_video_info, url)
            
            if not video_info or not video_info.get('formats'):
                await message.edit_text("❌ Failed to fetch video information")
                return
            
            # Get formats - EXACTLY the same as web API receives
            formats = video_info.get('formats', [])
            print(f"DEBUG TELEGRAM: Using same video_info_service.get_video_info() as web API")
            print(f"DEBUG TELEGRAM: Formats array length: {len(formats)} (should match web API)")
            info_text = (
                f"📹 **{video_info['title']}**\n\n"
                f"⏱ Duration: {self._format_duration(video_info.get('duration', 0))}\n"
                f"📊 Available formats: {len(formats)}\n\n"
                "Select a format:"
            )
            
            # Create inline keyboard with format options
            keyboard = []
            # Show all formats (up to 15, same as web API)
            # Store URL with a unique ID to avoid callback_data length limits
            download_id = str(uuid.uuid4())[:8]
            
            # Validate and store URL
            if not url or not isinstance(url, str):
                await message.edit_text(f"❌ Invalid URL received: {type(url)}")
                return
            
            if not url.startswith(('http://', 'https://')):
                await message.edit_text(f"❌ Invalid URL format: {url[:50]}")
                return
            
            # Store URL with download_id
            self.pending_downloads[download_id] = url
            
            # Verify storage immediately
            stored_url = self.pending_downloads.get(download_id)
            if stored_url != url:
                print(f"ERROR: URL storage failed! Expected: {url}, Got: {stored_url}")
                await message.edit_text("❌ Error storing download session. Please try again.")
                return
            
            print(f"DEBUG: Found {len(formats)} formats for URL: {url[:50]}...")
            print(f"DEBUG: Stored URL with download_id: {download_id}")
            print(f"DEBUG: URL validation - starts with http: {url.startswith(('http://', 'https://'))}")
            print(f"DEBUG: URL length: {len(url)}")
            print(f"DEBUG: ✅ Verified stored URL: {stored_url[:50]}...")
            print(f"DEBUG: Total pending downloads now: {len(self.pending_downloads)}")
            
            # Debug: Print all formats received (same as web API)
            print(f"DEBUG TELEGRAM: Received {len(formats)} formats from video_info_service (same as web API)")
            print(f"DEBUG TELEGRAM: Full video_info keys: {list(video_info.keys())}")
            if len(formats) == 0:
                print(f"ERROR: No formats in video_info! video_info = {video_info}")
            for idx, fmt in enumerate(formats[:20], 1):  # Print first 20
                fmt_id = fmt.get('format_id', 'NO_ID')
                fmt_size = fmt.get('filesize') or 'NO_SIZE'
                print(f"  Format {idx}: {fmt.get('resolution')} {fmt.get('ext')} id={fmt_id} size={fmt_size} has_video={fmt.get('has_video')} has_audio={fmt.get('has_audio')}")
            
            # Use EXACTLY the same formats array as web API - no filtering at all
            # The video_info_service.get_video_info() returns the same formats for both web and Telegram
            # Just ensure format_id exists (use 'best' as fallback if missing)
            valid_formats = []
            for fmt in formats:
                # Ensure format_id exists - use 'best' if missing (same as web would handle it)
                if fmt.get('format_id') is None:
                    fmt['format_id'] = 'best'
                valid_formats.append(fmt)
            
            if not valid_formats:
                await message.edit_text("❌ No valid formats found for this video")
                return
            
            print(f"DEBUG TELEGRAM: Using {len(valid_formats)} formats (same as web API)")
            print(f"DEBUG TELEGRAM: Will create {len(valid_formats)} buttons")
            
            # Create buttons for ALL formats (Telegram supports up to 100 buttons)
            for i, fmt in enumerate(valid_formats):
                quality_label = fmt.get('resolution', 'Unknown')
                ext = fmt.get('ext', 'mp4')
                filesize = fmt.get('filesize', 0)
                size_str = self._format_file_size(filesize) if filesize else "Unknown"
                fps = fmt.get('fps')
                fps_str = f" {fps}fps" if fps else ""
                
                # Create button text with quality info
                button_text = f"{quality_label}{fps_str} ({ext}) - {size_str}"
                # Truncate if too long (Telegram button limit is ~64 chars)
                if len(button_text) > 60:
                    button_text = button_text[:57] + "..."
                
                # Use download_id instead of full URL to avoid callback_data length limits
                format_id = str(fmt.get('format_id', 'best'))
                # Sanitize format_id to avoid any issues with special characters
                format_id = format_id.replace(':', '_').replace('/', '_')
                callback_data = f"dl:{download_id}:{format_id}"
                
                # Verify callback_data length (Telegram limit is 64 bytes)
                callback_bytes = len(callback_data.encode('utf-8'))
                if callback_bytes > 64:
                    print(f"WARNING: Callback data too long ({callback_bytes} bytes): {callback_data}")
                    # Fallback: use 'best' if format_id is too long
                    callback_data = f"dl:{download_id}:best"
                
                # Telegram callback_data has 64 byte limit, so we use short IDs
                keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
                print(f"DEBUG: Button {i+1}: {button_text[:40]} -> {callback_data}")
            
            print(f"DEBUG: Created {len(keyboard)} format buttons")
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await message.edit_text(
                info_text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            await message.edit_text(f"❌ Error: {str(e)}")
    
    async def _send_video_info(self, update: Update, url: str) -> None:
        """Send video information"""
        message = await update.message.reply_text("🔍 Fetching video information...")
        
        try:
            # Use the same service as web API
            loop = asyncio.get_event_loop()
            video_info = await loop.run_in_executor(None, self.video_info_service.get_video_info, url)
            
            if not video_info:
                await message.edit_text("❌ Failed to fetch video information")
                return
            
            info_text = (
                f"📹 **{video_info['title']}**\n\n"
                f"⏱ Duration: {self._format_duration(video_info.get('duration', 0))}\n"
                f"📊 Formats available: {len(video_info.get('formats', []))}\n\n"
                "Send the URL again to download, or use /download <url>"
            )
            
            if video_info.get('thumbnail'):
                await update.message.reply_photo(
                    photo=video_info['thumbnail'],
                    caption=info_text,
                    parse_mode='Markdown'
                )
                await message.delete()
            else:
                await message.edit_text(info_text, parse_mode='Markdown')
                
        except Exception as e:
            await message.edit_text(f"❌ Error: {str(e)}")
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle callback queries (format selection and download options)"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        print(f"DEBUG: Received callback data: {data}")
        print(f"DEBUG: Callback data length: {len(data)} bytes")
        print(f"DEBUG: Callback data type: {type(data)}")
        
        # Check for old format first and give clear error
        if data.startswith("download:"):
            print(f"ERROR: OLD FORMAT DETECTED! This button is from before the fix.")
            print(f"ERROR: Old format: {data[:100]}")
            await query.message.reply_text(
                "❌ **OLD BUTTON DETECTED**\n\n"
                "This button uses the old format and won't work.\n\n"
                "**Please:**\n"
                "1. Restart the bot\n"
                "2. Send a NEW YouTube URL\n"
                "3. Use the NEW buttons\n\n"
                "Old buttons cannot be fixed - you need fresh ones!"
            )
            return
        
        if data.startswith("dl:"):
            # New format: dl:download_id:format_id
            try:
                parts = data.split(":", 2)
                print(f"DEBUG: Split callback data into {len(parts)} parts: {parts}")
                
                if len(parts) >= 3:
                    download_id = parts[1]
                    format_id = parts[2]
                    print(f"DEBUG: download_id={download_id}, format_id={format_id}")
                    print(f"DEBUG: Total pending downloads: {len(self.pending_downloads)}")
                    print(f"DEBUG: Available download IDs: {list(self.pending_downloads.keys())[:10]}")
                    print(f"DEBUG: Looking for download_id: '{download_id}'")
                    print(f"DEBUG: Full pending_downloads dict: {self.pending_downloads}")
                    
                    url = self.pending_downloads.get(download_id)
                    
                    if url:
                        print(f"DEBUG: ✅ Found URL: {url}")
                        print(f"DEBUG: URL type: {type(url)}, length: {len(url)}")
                        print(f"DEBUG: URL starts with http: {url.startswith(('http://', 'https://')) if isinstance(url, str) else False}")
                        
                        if not isinstance(url, str):
                            error_msg = f"❌ Invalid URL type: {type(url).__name__}"
                            print(f"ERROR: {error_msg}")
                            await query.message.reply_text(error_msg)
                            return
                            
                        if not url.startswith(('http://', 'https://')):
                            error_msg = f"❌ Invalid URL format: '{url[:50]}'"
                            print(f"ERROR: {error_msg}")
                            await query.message.reply_text(error_msg)
                            return
                            
                        if len(url) < 10:
                            error_msg = f"❌ URL too short: '{url}'"
                            print(f"ERROR: {error_msg}")
                            await query.message.reply_text(error_msg)
                            return
                        
                        print(f"DEBUG: ✅ URL validation passed, starting download...")
                        await self._start_download(query, url, format_id)
                    else:
                        error_msg = f"❌ Download session expired. download_id '{download_id}' not found."
                        print(f"ERROR: {error_msg}")
                        print(f"DEBUG: All pending download IDs: {list(self.pending_downloads.keys())}")
                        print(f"DEBUG: This usually means the bot was restarted. Please send the URL again.")
                        await query.message.reply_text(
                            "❌ Download session expired (bot may have restarted).\n\n"
                            "Please send the URL again to get fresh format options."
                        )
                else:
                    error_msg = f"❌ Invalid callback data format. Expected 3 parts, got {len(parts)}: {data}"
                    print(f"ERROR: {error_msg}")
                    await query.message.reply_text("❌ Invalid callback data. Please try again.")
            except Exception as e:
                error_msg = f"❌ Error processing callback: {str(e)}"
                print(f"ERROR: {error_msg}")
                import traceback
                traceback.print_exc()
                await query.message.reply_text(error_msg)
        elif data.startswith("download:"):
            # Legacy format - this is the problem! Old buttons still use this format
            print(f"DEBUG: Legacy callback format detected: {data}")
            print(f"ERROR: Old callback format still in use - URL will be split incorrectly!")
            try:
                # Try to handle it but warn user
                parts = data.split(":", 2)
                if len(parts) == 3:
                    # This will fail because URL contains colons
                    partial_url = parts[1]  # This will be just "https"!
                    format_id = parts[2]
                    print(f"ERROR: Legacy format detected - partial_url={partial_url}, format_id={format_id}")
            except:
                pass
            await query.message.reply_text(
                "❌ Please send the URL again to get updated format options.\n"
                "The old format buttons are no longer supported."
            )
        elif data.startswith("send_file:"):
            # Send file directly
            file_id = data.split(":", 1)[1]
            await self._send_file_to_user(query, file_id)
        elif data.startswith("send_link:"):
            # Send download link
            file_id = data.split(":", 1)[1]
            await self._send_download_link(query, file_id)
    
    async def _start_download(self, query, url: str, format_id: str) -> None:
        """Start downloading video"""
        user_id = str(query.from_user.id)
        message = await query.message.reply_text("📥 Starting download...")
        
        try:
            # Validate URL
            if not url or not url.startswith(('http://', 'https://')):
                print(f"ERROR: Invalid URL received: {url}")
                await message.edit_text(f"❌ Invalid URL: {url[:50] if url else 'None'}")
                return
            
            # Cleanup: remove all previous files before new download
            self._cleanup_downloads()
            
            print(f"DEBUG: Starting download - URL: {url[:80]}..., format_id: {format_id}")
            
            # Generate file ID
            file_id = str(uuid.uuid4())
            
            # Store download info
            self.active_downloads[user_id] = {
                'file_id': file_id,
                'url': url,
                'status': 'downloading'
            }
            
            # Update message
            await message.edit_text("📥 Downloading video... This may take a while.")
            
            # Download in background
            asyncio.create_task(self._download_video_async(file_id, url, format_id, message, user_id))
            
        except Exception as e:
            print(f"ERROR in _start_download: {e}")
            import traceback
            traceback.print_exc()
            await message.edit_text(f"❌ Error starting download: {str(e)}")
    
    async def _download_video_async(
        self,
        file_id: str,
        url: str,
        format_id: str,
        message,
        user_id: str
    ) -> None:
        """Download video asynchronously"""
        try:
            # CRITICAL: Validate URL before using it
            print(f"DEBUG _download_video_async: Received URL='{url}', type={type(url)}, length={len(url) if url else 0}")
            
            if not url:
                error_msg = "URL is None or empty"
                print(f"ERROR: {error_msg}")
                await message.edit_text(f"❌ {error_msg}")
                return
                
            if not isinstance(url, str):
                error_msg = f"URL is not a string: {type(url)}"
                print(f"ERROR: {error_msg}")
                await message.edit_text(f"❌ {error_msg}")
                return
                
            if not url.startswith(('http://', 'https://')):
                error_msg = f"Invalid URL format: '{url}' (doesn't start with http:// or https://)"
                print(f"ERROR: {error_msg}")
                await message.edit_text(f"❌ {error_msg}")
                return
                
            if len(url) < 10:  # Minimum reasonable URL length
                error_msg = f"URL too short: '{url}'"
                print(f"ERROR: {error_msg}")
                await message.edit_text(f"❌ {error_msg}")
                return
            
            print(f"DEBUG: URL validation passed: {url[:100]}...")
            
            progress_queue = asyncio.Queue()
            last_update_percentage = [0]
            
            def progress_hook(d):
                if d['status'] == 'downloading':
                    total = d.get('total_bytes', 0) or d.get('total_bytes_estimate', 0) or 1
                    downloaded = d.get('downloaded_bytes', 0)
                    percentage = (downloaded * 100) / total if total > 0 else 0
                    current_percentage = int(percentage)
                    
                    # Queue progress updates (throttle to every 10%)
                    if current_percentage >= last_update_percentage[0] + 10:
                        last_update_percentage[0] = current_percentage
                        try:
                            progress_queue.put_nowait((current_percentage, downloaded, total))
                        except Exception:
                            pass
            
            # Start progress monitor task
            async def monitor_progress():
                while True:
                    try:
                        percentage, downloaded, total = await asyncio.wait_for(
                            progress_queue.get(), timeout=1.0
                        )
                        await self._update_progress(message, percentage, downloaded, total)
                    except asyncio.TimeoutError:
                        continue
                    except Exception:
                        break
            
            monitor_task = asyncio.create_task(monitor_progress())
            
            # Format selection - use merging logic like main.py
            # This enables high quality downloads (1080p+) with audio
            if format_id:
                # Strictly respect the user's choice. 
                # Try to merge with best audio. If that fails (e.g. format is already merged), use format_id as is.
                # We do NOT fallback to 'best' because that causes the "low quality" issue the user reported.
                format_string = f"{format_id}+bestaudio/{format_id}"
            else:
                format_string = 'bestvideo+bestaudio/best'
            
            ydl_opts = {
                'format': format_string,
                'outtmpl': os.path.join(self.downloads_dir, f'{file_id}.%(ext)s'),
                'quiet': False,  # Set to False to see yt-dlp output for debugging
                'no_warnings': False,  # Show warnings to debug issues
                'progress_hooks': [progress_hook],
                'progress_hooks': [progress_hook],
                'merge_output_format': 'mp4',
            }
            
            if FFMPEG_LOCATION:
                ydl_opts['ffmpeg_location'] = FFMPEG_LOCATION
            
            # Run yt-dlp in executor to avoid blocking
            loop = asyncio.get_event_loop()
            try:
                # Final validation before calling yt-dlp
                print(f"DEBUG: About to call yt-dlp with URL: {url[:100]}...")
                print(f"DEBUG: Format ID: {format_id}")
                print(f"DEBUG: URL type: {type(url)}, length: {len(url)}")
                
                if not url or not isinstance(url, str):
                    raise ValueError(f"URL is invalid: {url} (type: {type(url)})")
                
                if not url.startswith(('http://', 'https://')):
                    raise ValueError(f"URL doesn't start with http:// or https://: '{url}'")
                
                if len(url) < 10:
                    raise ValueError(f"URL too short: '{url}'")
                
                print(f"DEBUG: All validations passed, calling yt-dlp...")
                print(f"DEBUG: yt-dlp options: {ydl_opts}")
                
                # Add timeout to prevent hanging
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        print(f"DEBUG: yt-dlp instance created, calling extract_info...")
                        # Use asyncio.wait_for to add a timeout
                        info = await asyncio.wait_for(
                            loop.run_in_executor(None, ydl.extract_info, url, True),
                            timeout=300.0  # 5 minute timeout
                        )
                        print(f"DEBUG: yt-dlp extract_info completed successfully")
                except asyncio.TimeoutError:
                    error_msg = "Download timeout: yt-dlp took too long (>5 minutes). The video might be very large or there's a network issue."
                    print(f"ERROR: {error_msg}")
                    await message.edit_text(f"❌ {error_msg}")
                    return
                except Exception as e:
                    error_msg = f"yt-dlp error: {str(e)}"
                    print(f"ERROR: {error_msg}")
                    import traceback
                    traceback.print_exc()
                    await message.edit_text(f"❌ Download failed: {error_msg}")
                    return
            finally:
                # Stop progress monitor
                monitor_task.cancel()
                try:
                    await monitor_task
                except asyncio.CancelledError:
                    pass
            
            ext = info.get('ext', 'mp4')
            filename = info.get('title', 'video')
            filepath = os.path.join(self.downloads_dir, f'{file_id}.{ext}')
            
            if os.path.exists(filepath):
                filesize = os.path.getsize(filepath)
                
                # Store download info for later use
                self.completed_downloads[file_id] = {
                    'filename': filename,
                    'filesize': filesize,
                    'ext': ext,
                    'user_id': user_id,
                    'filepath': filepath
                }
                
                # Show options: send file or send link
                download_url = f"{self.api_base_url}/api/download-file/{file_id}"
                size_str = self._format_file_size(filesize)
                
                options_text = (
                    f"✅ Download complete!\n\n"
                    f"📹 **{filename}**\n"
                    f"💾 Size: {size_str}\n\n"
                    f"Choose how to receive the file:"
                )
                
                # Create inline keyboard with options
                # Always show both options if channel is configured (channel supports up to 2GB)
                if self.channel_id:
                    # Channel configured - always show both options
                    keyboard = [
                        [
                            InlineKeyboardButton(
                                "📤 Send File to Channel",
                                callback_data=f"send_file:{file_id}"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "🔗 Get Download Link",
                                callback_data=f"send_link:{file_id}"
                            )
                        ]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                elif filesize < 50 * 1024 * 1024:  # 50MB limit for direct messages
                    # No channel configured, file is small enough for direct message
                    keyboard = [
                        [
                            InlineKeyboardButton(
                                "📤 Send File via Telegram",
                                callback_data=f"send_file:{file_id}"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "🔗 Get Download Link",
                                callback_data=f"send_link:{file_id}"
                            )
                        ]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                else:
                    # No channel configured, file too large for direct message
                    reply_markup = InlineKeyboardMarkup([
                        [InlineKeyboardButton(
                            "🔗 Get Download Link (File too large for Telegram)",
                            callback_data=f"send_link:{file_id}"
                        )]
                    ])
                    options_text = (
                        f"✅ Download complete!\n\n"
                        f"📹 **{filename}**\n"
                        f"💾 Size: {size_str}\n\n"
                        f"⚠️ File is too large for Telegram (50MB limit)\n"
                        f"Use the download link instead:"
                    )
                
                await message.edit_text(
                    options_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
                
                # Cleanup active download tracking
                if user_id in self.active_downloads:
                    del self.active_downloads[user_id]
            else:
                await message.edit_text("❌ File not found after download")
                
        except Exception as e:
            await message.edit_text(f"❌ Download failed: {str(e)}")
            if user_id in self.active_downloads:
                del self.active_downloads[user_id]
    
    def _upload_progress_callback(self, current, total):
        """Enhanced callback for upload progress with speed and ETA
        """
        import time
        
        # Initialize start time on first call
        if self.progress_start_time is None:
            self.progress_start_time = time.time()
            self.last_progress_update = time.time()
        
        percentage = (current / total) * 100 if total > 0 else 0
        self.current_file_progress = {
            "uploaded": current,
            "total": total,
            "percentage": percentage
        }
        
        # Calculate speed and ETA with minimum elapsed time to avoid 0B/s
        elapsed_time = time.time() - self.progress_start_time
        
        # Require at least 1 second elapsed to calculate speed
        if elapsed_time >= 1.0:
            speed = current / elapsed_time
            remaining_bytes = total - current
            eta_seconds = remaining_bytes / speed if speed > 0 else 0
            
            # Format speed
            speed_str = format_bytes(int(speed)) + "/s"
            
            # Format ETA
            if eta_seconds < 60:
                eta_str = f"{int(eta_seconds)}s"
            elif eta_seconds < 3600:
                eta_str = f"{int(eta_seconds/60)}m {int(eta_seconds%60)}s"
            else:
                eta_str = f"{int(eta_seconds/3600)}h {int((eta_seconds%3600)/60)}m"
        else:
            # Not enough time elapsed, show "Calculating..."
            speed_str = "Calculating..."
            eta_str = "Calculating..."
        
        # Update message every 5 seconds or every 10% or if it's the first/last update
        current_time = time.time()
        should_update = (
            (current_time - self.last_progress_update >= 5) or 
            (percentage % 10 < 1) or 
            (percentage >= 99) or
            (current == total)
        )
        
        if self.progress_message and should_update:
            try:
                progress_bar = create_progress_bar(percentage, 20)
                progress_text = f"""
⬆️ **Uploading File**
📄 **{self.current_file_name}**

{progress_bar} {percentage:.1f}%

📤 **Uploaded**: {format_bytes(current)} / {format_bytes(total)}
⚡ **Remaining**: {format_bytes(total - current)}
🚀 **Speed**: {speed_str}
⏱️ **ETA**: {eta_str}
"""
                # Schedule the async message edit without blocking
                # We use create_task to fire-and-forget the update
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(self.progress_message.edit_text(progress_text))
                except RuntimeError:
                    # No running loop, skip the update
                    pass
                self.last_progress_update = current_time
            except Exception as e:
                # Ignore edit errors (too many requests, etc.)
                pass
    
    
    def _download_progress_callback(self, current, total):
        """Enhanced callback for download progress with speed and ETA
        
        IMPORTANT: This MUST be a synchronous function because Pyrogram
        calls it directly and does not await it.
        """
        import time
        
        # Initialize start time on first call
        if self.progress_start_time is None:
            self.progress_start_time = time.time()
            self.last_progress_update = time.time()
        
        percentage = (current / total) * 100 if total > 0 else 0
        self.current_file_progress = {
            "downloaded": current,
            "total": total,
            "percentage": percentage
        }
        
        # Calculate speed and ETA with minimum elapsed time to avoid 0B/s
        elapsed_time = time.time() - self.progress_start_time
        
        # Require at least 1 second elapsed to calculate speed
        if elapsed_time >= 1.0:
            speed = current / elapsed_time
            remaining_bytes = total - current
            eta_seconds = remaining_bytes / speed if speed > 0 else 0
            
            # Format speed
            speed_str = format_bytes(int(speed)) + "/s"
            
            # Format ETA
            if eta_seconds < 60:
                eta_str = f"{int(eta_seconds)}s"
            elif eta_seconds < 3600:
                eta_str = f"{int(eta_seconds/60)}m {int(eta_seconds%60)}s"
            else:
                eta_str = f"{int(eta_seconds/3600)}h {int((eta_seconds%3600)/60)}m"
        else:
            # Not enough time elapsed, show "Calculating..."
            speed_str = "Calculating..."
            eta_str = "Calculating..."
        
        # Update message every 5 seconds or every 10% or if it's the first/last update
        current_time = time.time()
        should_update = (
            (current_time - self.last_progress_update >= 5) or 
            (percentage % 10 < 1) or 
            (percentage >= 99) or
            (current == total)
        )
        
        if self.progress_message and should_update:
            try:
                progress_bar = create_progress_bar(percentage, 20)
                progress_text = f"""
⬇️ **Downloading File**
📄 **{self.current_file_name}**

{progress_bar} {percentage:.1f}%

📥 **Downloaded**: {format_bytes(current)} / {format_bytes(total)}
⚡ **Remaining**: {format_bytes(total - current)}
🚀 **Speed**: {speed_str}
⏱️ **ETA**: {eta_str}
"""
                # Schedule the async message edit without blocking
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(self.progress_message.edit_text(progress_text))
                except RuntimeError:
                    # No running loop, skip the update
                    pass
                self.last_progress_update = current_time
            except Exception as e:
                # Ignore edit errors (too many requests, etc.)
                pass
    
    
    async def _send_file_to_user(self, query, file_id: str) -> None:
        """Send downloaded file directly to user via Telegram"""
        if file_id not in self.completed_downloads:
            await query.message.reply_text("❌ File not found or expired")
            return
        
        download_info = self.completed_downloads[file_id]
        filepath = download_info['filepath']
        filename = download_info['filename']
        filesize = download_info['filesize']
        ext = download_info['ext']
        
        if not os.path.exists(filepath):
            await query.message.reply_text("❌ File not found on server")
            return
        
        # Check file size - channels support up to 2GB with Userbot/MTProto
        TELEGRAM_BOT_LIMIT = 50 * 1024 * 1024  # 50MB for bots via HTTP
        TELEGRAM_MTPROTO_LIMIT = 2000 * 1024 * 1024  # 2GB for MTProto
        
        print(f"DEBUG: _send_file_to_user called with file_id={file_id}")
        print(f"DEBUG: File size: {self._format_file_size(filesize)}")
        print(f"DEBUG: Pyrogram client connected: {self.pyrogram_client.is_connected if self.pyrogram_client else 'No client'}")
        
        # Decide transfer method
        use_pyrogram = False
        if filesize > TELEGRAM_BOT_LIMIT:
            if self.pyrogram_client and self.pyrogram_client.is_connected:
                use_pyrogram = True
                print(f"DEBUG: File > 50MB ({self._format_file_size(filesize)}). Using Pyrogram/Userbot.")
            else:
                if not HAS_PYROGRAM:
                    reason = "Pyrogram library not installed"
                elif not (TELEGRAM_API_ID and TELEGRAM_API_HASH and TELEGRAM_SESSION_STRING):
                    reason = "MTProto Config missing (API_ID, HASH, or SESSION_STRING)"
                else:
                    reason = "Pyrogram client not connected"
                
                print(f"ERROR: Cannot upload large file - {reason}")
                await query.message.edit_text(
                    f"❌ File is too large for standard Bot API ({self._format_file_size(filesize)} > 50MB).\n"
                    f"Reason for no large file support: {reason}\n\n"
                    "Please use the download link option instead.",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(
                            "🔗 Get Download Link",
                            callback_data=f"send_link:{file_id}"
                        )
                    ]])
                )
                return

        if filesize > TELEGRAM_MTPROTO_LIMIT:
            await query.message.edit_text(
                f"❌ File is too large even for Premium ({self._format_file_size(filesize)} > 2GB limit).\n"
                "Please use the download link option instead.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        "🔗 Get Download Link",
                        callback_data=f"send_link:{file_id}"
                    )
                ]])
            )
            return
        
        # Always use channel if configured, regardless of file size
        use_channel = self.channel_id is not None
        
        try:
            if use_channel:
                await query.message.edit_text("📤 Starting upload to channel... Please wait.")
            else:
                await query.message.edit_text("📤 Starting upload...")
            
            # Add timeout for file upload - longer for large files
            # Base timeout: 5 minutes, add 1 minute per 100MB
            base_timeout = 300  # 5 minutes
            additional_timeout = (filesize // (100 * 1024 * 1024)) * 60  # 1 minute per 100MB
            upload_timeout = base_timeout + additional_timeout
            # Cap at 30 minutes maximum
            upload_timeout = min(upload_timeout, 1800)
            
            print(f"DEBUG: Upload timeout set to {upload_timeout} seconds ({upload_timeout/60:.1f} minutes) for file size {self._format_file_size(filesize)}")
            
            # Prepare progress monitoring
            last_update_time = [0]
            progress_message = [None]  # Container to hold message ref
            
            def upload_progress_callback(current, total):
                progress_state['current'] = current
                progress_state['total'] = total
            
            # Shared state for progress
            progress_state = {'current': 0, 'total': filesize, 'done': False, 'start_time': None}
            
            # Background task to update upload message
            last_percentage = [0]  # Track last percentage to avoid duplicate updates
            async def update_upload_message():
                import time
                while not progress_state['done']:
                    try:
                        current = progress_state['current']
                        total = progress_state['total']
                        
                        # Initialize start time on first progress
                        if current > 0 and progress_state['start_time'] is None:
                            progress_state['start_time'] = time.time()
                        
                        # Calculate percentage
                        percentage = int((current / total) * 100) if total > 0 else 0
                        
                        # Only update if percentage changed by at least 5% to avoid spam
                        if abs(percentage - last_percentage[0]) < 5 and percentage != 100:
                            await asyncio.sleep(2)
                            continue
                        
                        last_percentage[0] = percentage
                        
                        # Create progress bar
                        bar_length = 15
                        filled_length = int(bar_length * percentage // 100)
                        bar = '█' * filled_length + '░' * (bar_length - filled_length)
                        
                        size_current = self._format_file_size(current)
                        size_total = self._format_file_size(total)
                        
                        # Calculate speed and ETA
                        if progress_state['start_time'] and current > 0:
                            elapsed = time.time() - progress_state['start_time']
                            if elapsed > 0:
                                speed = current / elapsed
                                speed_str = format_bytes(int(speed)) + "/s"
                                remaining = total - current
                                eta_seconds = remaining / speed if speed > 0 else 0
                                if eta_seconds < 60:
                                    eta_str = f"{int(eta_seconds)}s"
                                elif eta_seconds < 3600:
                                    eta_str = f"{int(eta_seconds/60)}m {int(eta_seconds%60)}s"
                                else:
                                    eta_str = f"{int(eta_seconds/3600)}h {int((eta_seconds%3600)/60)}m"
                            else:
                                speed_str = "Calculating..."
                                eta_str = "Calculating..."
                        else:
                            speed_str = "Starting..."
                            eta_str = "Calculating..."
                        
                        msg_text = (
                            f"⬆️ **Uploading File**\n"
                            f"📄 **{filename[:40]}**\n\n"
                            f"[{bar}] {percentage}%\n\n"
                            f"📤 {size_current} / {size_total}\n"
                            f"🚀 Speed: {speed_str}\n"
                            f"⏱️ ETA: {eta_str}"
                        )
                        
                        # Update text if changed
                        try:
                            if query.message.text != msg_text:
                                await query.message.edit_text(msg_text, parse_mode='Markdown')
                        except Exception as e:
                            # Ignore "message is not modified" errors
                            if "message is not modified" not in str(e).lower():
                                print(f"DEBUG: Progress update error: {e}")
                                
                    except Exception as e:
                        print(f"ERROR in progress task: {e}")
                        
                    await asyncio.sleep(2)  # Update every 2 seconds
            
            # Start monitoring task
            monitor_task = asyncio.create_task(update_upload_message())
            
            print(f"DEBUG: Upload method - use_pyrogram={use_pyrogram}, use_channel={use_channel}")
            
            if use_pyrogram:
                # Pyrogram Upload Logic
                try:
                    print(f"DEBUG: Uploading via Pyrogram to {self.channel_id or query.message.chat.id}")
                    
                    # Ensure Pyrogram client is connected
                    if not self.pyrogram_client.is_connected:
                        print("WARNING: Pyrogram client not connected, attempting to connect...")
                        try:
                            await asyncio.wait_for(self.pyrogram_client.start(), timeout=10.0)
                            print("✅ Pyrogram client connected")
                        except Exception as conn_error:
                            print(f"ERROR: Failed to connect Pyrogram client: {conn_error}")
                            raise Exception(f"Pyrogram client not connected: {conn_error}")
                    else:
                        print("✅ Pyrogram client already connected")
                    
                    # Define progress callback for Pyrogram
                    # IMPORTANT: Pyrogram requires a SYNCHRONOUS callback, NOT async!
                    last_logged_percent = [0]
                    def pyro_progress(current, total):
                        if progress_state:
                            progress_state['current'] = current
                            progress_state['total'] = total
                            # Log every 10% to avoid spam
                            percent = int((current / total) * 100) if total > 0 else 0
                            if percent >= last_logged_percent[0] + 10:
                                last_logged_percent[0] = percent
                                print(f"DEBUG: Pyrogram upload progress: {percent}% ({self._format_file_size(current)} / {self._format_file_size(total)})")
                    
                    target_chat = self.channel_id if self.channel_id else query.message.chat.id
                    
                    # Handle private channel IDs which often need -100 prefix if not present
                    # But user should provide correct ID. Pyrogram handles both int and string (@username)
                    if isinstance(target_chat, str) and target_chat.replace('-','').isdigit():
                        target_chat = int(target_chat)
                    
                    
                    # Verify file exists before uploading
                    if not os.path.exists(filepath):
                        raise Exception(f"File not found: {filepath}")
                    
                    print(f"DEBUG: File verified at: {filepath}")
                    print(f"DEBUG: Target chat: {target_chat}")
                    print(f"DEBUG: Caption: {filename}")
                    
                    # Resolve peer first - this caches the channel in Pyrogram's session
                    try:
                        print(f"DEBUG: Resolving peer/channel {target_chat}...")
                        
                        # Method 1: Try to get the chat directly
                        try:
                            chat = await self.pyrogram_client.get_chat(target_chat)
                            print(f"DEBUG: Channel resolved via get_chat: {chat.title} (ID: {chat.id})")
                        except Exception as e1:
                            print(f"DEBUG: get_chat failed: {e1}")
                            
                            # Method 2: Try to manually create InputPeerChannel
                            # For private channels with -100 prefix, we can try to access them directly
                            try:
                                from pyrogram.raw.types import InputPeerChannel, PeerChannel
                                from pyrogram.raw.functions.channels import GetChannels
                                
                                print(f"DEBUG: Trying manual InputPeerChannel...")
                                
                                # Extract channel ID (remove -100 prefix)
                                if str(target_chat).startswith("-100"):
                                    channel_id = int(str(target_chat)[4:])  # Remove -100 prefix
                                    
                                    print(f"DEBUG: Channel ID: {channel_id}, trying to fetch...")
                                    
                                    # Try to get channel info using raw API with access_hash=0
                                    input_channel = InputPeerChannel(
                                        channel_id=channel_id,
                                        access_hash=0
                                    )
                                    
                                    # Get channel info
                                    result = await self.pyrogram_client.invoke(
                                        GetChannels(id=[input_channel])
                                    )
                                    print(f"DEBUG: Got channel via raw API: {result}")
                                    
                                    # Extract access_hash from result
                                    if result.chats and len(result.chats) > 0:
                                        channel_data = result.chats[0]
                                        access_hash = channel_data.access_hash
                                        print(f"DEBUG: Extracted access_hash: {access_hash}")
                                        
                                        # Save peer using update_peers (works with both MemoryStorage and SQLiteStorage)
                                        from pyrogram.raw.types import PeerChannel
                                        
                                        peer_id = int(f"-100{channel_id}")
                                        
                                        # Use update_peers to cache the channel
                                        await self.pyrogram_client.storage.update_peers([
                                            (peer_id, access_hash, "channel", None, None)
                                        ])
                                        print(f"DEBUG: Peer cached in storage with access_hash")
                                        
                                        # Try get_chat again
                                        chat = await self.pyrogram_client.get_chat(target_chat)
                                        print(f"DEBUG: Channel NOW resolved: {chat.title}")
                                    else:
                                        raise Exception("No channel data in response")
                                    
                            except Exception as e2:
                                print(f"DEBUG: Manual InputPeerChannel failed: {e2}")
                                
                                # Method 3: The userbot MUST be a member
                                print(f"ERROR: Cannot resolve private channel {target_chat}")
                                print(f"")
                                print(f"╔══════════════════════════════════════════════════════════╗")
                                print(f"║  SOLUTION: Add Userbot to Channel                        ║")
                                print(f"╠══════════════════════════════════════════════════════════╣")
                                print(f"║  The USERBOT account (not the bot) must join the channel ║")
                                print(f"║                                                          ║")
                                print(f"║  Steps:                                                  ║")
                                print(f"║  1. Log in to Telegram with the userbot account         ║")
                                print(f"║  2. Join/access channel: {str(target_chat):20s}        ║")
                                print(f"║  3. Send a test message in the channel                  ║")
                                print(f"║  4. Restart this bot                                    ║")
                                print(f"╚══════════════════════════════════════════════════════════╝")
                                
                                raise Exception(
                                    f"Userbot cannot access channel {target_chat}. "
                                    f"The userbot account (session string owner) must be a member of this channel."
                                )
                    except Exception as resolve_error:
                        print(f"ERROR: Failed to resolve channel: {resolve_error}")
                        raise
                    
                    # Add timeout to prevent hanging - use the calculated upload_timeout
                    print(f"DEBUG: Starting Pyrogram upload with {upload_timeout}s timeout...")
                    
                    # Set progress tracking variables
                    self.current_file_name = f"{filename}.{ext}"[:50]  # Limit filename length
                    self.progress_message = query.message
                    self.progress_start_time = None  # Reset for new upload
                    
                    # Check if file needs splitting (> 2GB)
                    MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB
                    
                    if filesize > MAX_FILE_SIZE:
                        # File is larger than 2GB, need to split
                        split_info = f"""
📦 **Large File Detected!**

📦 **File**: {filename[:40]}
📏 **Size**: {format_bytes(filesize)}
⚠️ **Action**: Splitting into parts (max 1.95GB each)

⏳ Splitting file...
"""
                        await query.message.edit_text(split_info)
                        
                        # Split the file
                        chunk_files = split_file(filepath)
                        num_parts = len(chunk_files)
                        
                        print(f"File split into {num_parts} parts")
                        
                        # Upload each chunk
                        for part_num, chunk_file in enumerate(chunk_files, 1):
                            chunk_size = os.path.getsize(chunk_file)
                            chunk_name = os.path.basename(chunk_file)
                            
                            # Reset progress timer for each chunk
                            self.progress_start_time = None
                            self.current_file_name = chunk_name[:50]
                            
                            # Create caption for this part
                            part_caption = f"📹 {filename}\n💾 Part {part_num}/{num_parts}\n📏 Size: {format_bytes(chunk_size)}"
                            
                            # Create initial upload progress for this part
                            initial_upload = f"""
⬆️ **Uploading Part {part_num}/{num_parts}**

📦 **File**: {chunk_name[:40]}
📏 **Size**: {format_bytes(chunk_size)}

{create_progress_bar(0, 20)} 0.0%

📤 Uploaded: 0B / {format_bytes(chunk_size)}
⚡ Starting upload...
"""
                            await query.message.edit_text(initial_upload)
                            
                            # Upload chunk directly to channel (like original code)
                            print(f"DEBUG: Uploading part {part_num}/{num_parts} directly to channel {target_chat}...")
                            sent_msg = await asyncio.wait_for(
                                self.pyrogram_client.send_document(
                                    chat_id=target_chat,
                                    document=chunk_file,
                                    caption=part_caption,
                                    file_name=chunk_name,
                                    progress=pyro_progress
                                ),
                                timeout=upload_timeout
                            )
                            print(f"DEBUG: Part {part_num}/{num_parts} uploaded successfully")
                            
                            # Clean up this chunk file
                            try:
                                if os.path.exists(chunk_file):
                                    os.remove(chunk_file)
                                    print(f"Deleted chunk file: {chunk_name}")
                            except Exception as e:
                                print(f"Failed to delete chunk file {chunk_name}: {e}")
                            
                            # Small delay between parts
                            if part_num < num_parts:
                                await asyncio.sleep(2)
                        
                        # All parts uploaded successfully
                        if self.channel_id:
                            msg_link = None
                            if self.channel_id and str(self.channel_id).startswith("-100"):
                                chan_id_short = str(self.channel_id).replace("-100", "")
                                msg_link = f"https://t.me/c/{chan_id_short}"
                            
                            await query.message.edit_text(
                                f"✅ Large file uploaded successfully!\n\n"
                                f"📹 {filename}\n"
                                f"💾 Size: {format_bytes(filesize)}\n"
                                f"📦 Parts: {num_parts}\n\n"
                                f"🔗 Check your channel: {self.channel_id}",
                                parse_mode='Markdown'
                            )
                        else:
                            await query.message.edit_text(
                                f"✅ Large file uploaded successfully!\n\n"
                                f"📹 {filename}\n"
                                f"💾 Size: {format_bytes(filesize)}\n"
                                f"📦 Parts: {num_parts}",
                                parse_mode='Markdown'
                            )
                    
                    else:
                        # File is small enough, upload normally
                        # WORKAROUND: send_document to channel hangs due to peer resolution issues
                        # Instead: Send to "me" (Saved Messages) first, then forward to channel
                        # This works because "me" is always cached and accessible
                        
                        # Create initial upload progress message
                        initial_upload = f"""
⬆️ **Uploading File**

📦 **File**: {filename[:40]}
📏 **Size**: {format_bytes(filesize)}

{create_progress_bar(0, 20)} 0.0%

📤 Uploaded: 0B / {format_bytes(filesize)}
⚡ Starting upload...
"""
                        await query.message.edit_text(initial_upload)
                        
                        # Upload directly to channel (like original code)
                        print(f"DEBUG: Uploading directly to channel {target_chat}...")
                        sent_msg = await asyncio.wait_for(
                            self.pyrogram_client.send_document(
                                chat_id=target_chat,
                                document=filepath,
                                caption=f"📹 {filename}\n💾 Size: {self._format_file_size(filesize)}",
                                file_name=f"{filename}.{ext}",
                                progress=pyro_progress
                            ),
                            timeout=upload_timeout
                        )
                        print(f"DEBUG: File uploaded to channel successfully")
                        
                        # If sent to channel, give link
                        if self.channel_id:
                            # Construct link
                            msg_link = sent_msg.link
                            if not msg_link and self.channel_id and str(self.channel_id).startswith("-100"):
                                # Manual link construction for private channels
                                chan_id_short = str(self.channel_id).replace("-100", "")
                                msg_link = f"https://t.me/c/{chan_id_short}/{sent_msg.id}"
                            
                            await query.message.edit_text(
                                f"📹 {filename}\n"
                                f"💾 Size: {self._format_file_size(filesize)}\n\n"
                                f"🔗 [Open in Channel]({msg_link})",
                                parse_mode='Markdown'
                            )
                        else:
                            await query.message.edit_text(
                                f"✅ Large File sent directly via Userbot!\n\n"
                                f"📹 {filename}\n"
                                f"💾 Size: {self._format_file_size(filesize)}",
                                parse_mode='Markdown'
                            )
                        
                        
                        
                except asyncio.TimeoutError:
                    print(f"ERROR: Pyrogram upload timed out after {upload_timeout}s")
                    raise Exception(f"Upload timed out after {upload_timeout/60:.1f} minutes. File may be too large or network is slow.")
                except Exception as e:
                    print(f"Pyrogram Upload Error: {e}")
                    import traceback
                    traceback.print_exc()
                    raise e
                        
            elif use_channel:
                    # Standard Bot API Channel Upload (Limit 50MB usually, but local server supports more)
                    # ... (Existing logic for Bot API Channel upload)
                    # Start monitoring task since we use reader
                     # Use ProgressReader
                    # Open with ProgressReader directly
                    reader = ProgressReader(filepath, upload_progress_callback)
                    try:
                        # Send to channel
                        bot = self.application.bot if self.application else None
                        if not bot:
                             raise Exception("Bot instance not available")
                        
                        # Authentication checks...
                        try:
                            member = await bot.get_chat_member(chat_id=self.channel_id, user_id=bot.id)
                            if member.status not in ['administrator', 'creator', 'member']:
                                raise Exception(f"Bot is not a member/admin. Status: {member.status}")
                        except Exception as member_error:
                             # ... (Existing error handling)
                             raise member_error

                        sent_message = await asyncio.wait_for(
                            bot.send_document(
                                chat_id=self.channel_id,
                                document=reader, # Pass our file-like object
                                filename=f"{filename}.{ext}",
                                caption=f"📹 {filename}\n💾 Size: {self._format_file_size(filesize)}"
                            ),
                            timeout=upload_timeout + 60
                        )
                        
                        # Send channel link to user
                        channel_username = self.channel_id if self.channel_id.startswith('@') else f"@{self.channel_id}"
                        channel_link = f"https://t.me/{channel_username.replace('@', '')}/{sent_message.message_id}" if not self.channel_id.startswith('-') else None
                        
                        if channel_link:
                            await query.message.edit_text(
                                f"✅ File sent to channel!\n\n"
                                f"📹 {filename}\n"
                                f"💾 Size: {self._format_file_size(filesize)}\n\n"
                                f"🔗 [Open in Channel]({channel_link})",
                                parse_mode='Markdown'
                            )
                        else:
                            await query.message.edit_text(
                                f"✅ File sent to channel!\n\n"
                                f"📹 {filename}\n"
                                f"💾 Size: {self._format_file_size(filesize)}\n\n"
                                f"Check your channel: {self.channel_id}",
                                parse_mode='Markdown'
                            )
                        
                    finally:
                        reader.close()


            else:
                # Send directly to user (files <50MB) via Bot API
                reader = ProgressReader(filepath, upload_progress_callback)
                try:
                    await asyncio.wait_for(
                        query.message.reply_document(
                            document=reader, # Pass our file-like object
                            filename=f"{filename}.{ext}",
                            caption=f"📹 {filename}\n💾 Size: {self._format_file_size(filesize)}"
                        ),
                        timeout=upload_timeout
                    )
                    await query.message.delete()
                finally:
                    reader.close()
                
        except asyncio.TimeoutError:
            await query.message.edit_text(
                f"❌ Upload timeout: File is too large to send via Telegram.\n"
                f"Size: {self._format_file_size(filesize)}\n\n"
                "Please use the download link option instead.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        "🔗 Get Download Link",
                        callback_data=f"send_link:{file_id}"
                    )
                ]])
            )
        except Exception as e:
            error_msg = str(e)
            print(f"ERROR sending file: {error_msg}")
            
            if "file is too large" in error_msg.lower() or "413" in error_msg or "timeout" in error_msg.lower():
                await query.message.edit_text(
                    f"❌ File is too large for Telegram ({self._format_file_size(filesize)}).\n"
                    "Please use the download link option instead.",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(
                            "🔗 Get Download Link",
                            callback_data=f"send_link:{file_id}"
                        )
                    ]])
                )
            else:
                await query.message.edit_text(
                    f"❌ Error sending file: {error_msg}\n\n"
                    "Try using the download link option instead.",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(
                            "🔗 Get Download Link",
                            callback_data=f"send_link:{file_id}"
                        )
                    ]])
                )
        finally:
            # Clean up shared state
            progress_state['done'] = True
            
            # Ensure monitor task stops
            try:
                monitor_task.cancel()
                await monitor_task
            except asyncio.CancelledError:
                pass
    
    async def _send_download_link(self, query, file_id: str) -> None:
        """Send download link to user"""
        if file_id not in self.completed_downloads:
            await query.message.reply_text("❌ File not found or expired")
            return
        
        download_info = self.completed_downloads[file_id]
        filename = download_info['filename']
        filesize = download_info['filesize']
        ext = download_info['ext']
        download_url = f"{self.api_base_url}/api/download-file/{file_id}"
        
        link_text = (
            f"🔗 **Download Link**\n\n"
            f"📹 {filename}\n"
            f"💾 Size: {self._format_file_size(filesize)}\n\n"
            f"Click the link below to download:\n"
            f"{download_url}\n\n"
            f"⚠️ Link expires in 3 days"
        )
        
        # Check if URL is localhost - Telegram doesn't allow localhost URLs in inline buttons
        is_localhost = 'localhost' in download_url or '127.0.0.1' in download_url or '0.0.0.0' in download_url
        
        if is_localhost:
            # For localhost, just send the text without an inline button
            # Users can copy the URL manually
            link_text += "\n\n⚠️ Note: This is a localhost URL. Copy and paste it into your browser."
            await query.message.edit_text(
                link_text,
                parse_mode='Markdown'
            )
        else:
            # For public URLs, use inline button
            await query.message.edit_text(
                link_text,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔗 Open Download Link", url=download_url)
                ]])
            )
    
    async def _update_progress(self, message, percentage: int, downloaded: int, total: int) -> None:
        """Update download progress message"""
        try:
            downloaded_str = self._format_file_size(downloaded)
            total_str = self._format_file_size(total)
            progress_text = f"📥 Downloading... {percentage}%\n{downloaded_str} / {total_str}"
            await message.edit_text(progress_text)
        except Exception:
            pass  # Ignore errors when updating progress (message might be deleted or edited)
    
    # Removed _get_video_info_async - now using VideoInfoService.get_video_info() directly
    # This ensures the Telegram bot shows the same formats as the web API
    
    def _format_duration(self, seconds: int) -> str:
        """Format duration in seconds to MM:SS or HH:MM:SS"""
        if not seconds:
            return "Unknown"
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        
        if hours > 0:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        return f"{minutes}:{secs:02d}"
    
    def _format_file_size(self, bytes: int) -> str:
        """Format file size"""
        if not bytes:
            return "Unknown"
        mb = bytes / (1024 * 1024)
        if mb < 1:
            kb = bytes / 1024
            return f"{kb:.2f} KB"
        return f"{mb:.2f} MB"
    
    def setup_handlers(self, application: Application) -> None:
        """Setup command and message handlers"""
        print("🔧 Setting up handlers...")
        # IMPORTANT: Add command handlers FIRST, before message handlers
        # Command handlers
        application.add_handler(CommandHandler("start", self.start_command))
        application.add_handler(CommandHandler("help", self.help_command))
        application.add_handler(CommandHandler("info", self.info_command))
        application.add_handler(CommandHandler("download", self.download_command))
        application.add_handler(CommandHandler("cancel", self.cancel_command))
        print("✅ Command handlers registered")
        
        # Callback query handler
        application.add_handler(CallbackQueryHandler(self.handle_callback))
        print("✅ Callback handler registered")
        
        # Message handler (for YouTube URLs) - must be last to not intercept commands
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        print("✅ Message handler registered")
    
    async def start_bot(self) -> None:
        """Start the Telegram bot"""
        if not self.bot_token:
            raise ValueError("Telegram bot token not provided")
        
        try:
            print(f"🤖 Starting Telegram bot with token: {self.bot_token[:10]}...")
            # Configure timeouts for large file uploads (30 minutes)
            from telegram.request import HTTPXRequest
            request = HTTPXRequest(
                connection_pool_size=8,
                read_timeout=1800,  # 30 minutes
                write_timeout=1800,  # 30 minutes
                connect_timeout=60
            )
            self.application = Application.builder().token(self.bot_token).request(request).build()
            self.setup_handlers(self.application)
            
            print("📡 Initializing bot...")
            await self.application.initialize()
            
            print("🚀 Starting bot...")
            await self.application.start()
            
            # Get bot info to verify connection
            bot_info = await self.application.bot.get_me()
            print(f"✅ Bot connected! Username: @{bot_info.username}")
            
            # Start Pyrogram client DIRECTLY (not in background task)
            # This ensures it binds to the same event loop as the bot
            if self.pyrogram_client:
                await self._start_pyrogram_client()

            print("🔄 Starting polling...")
            await self.application.updater.start_polling()
        except Exception as e:
            print(f"❌ Error starting bot: {e}")
            print(f"Error type: {type(e).__name__}")
            import traceback
            traceback.print_exc()
            raise
            raise

    async def _start_pyrogram_client(self):
        """Start Pyrogram client in background with retries"""
        print("⏳ Attempting to start Pyrogram Client (Background)...")
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Add timeout to prevent hanging indefinitely
                await asyncio.wait_for(self.pyrogram_client.start(), timeout=20.0)
                print("✅ Pyrogram Client started successfully")
                
                # Verify channel access
                if self.channel_id:
                    try:
                        # Try to get entity to cache it
                        chat = await self.pyrogram_client.get_chat(self.channel_id)
                        print(f"✅ Pyrogram has access to channel: {chat.title}")
                    except Exception as e:
                        print(f"⚠️ Pyrogram cannot access channel {self.channel_id}: {e}")
                
                # If successful, break retry loop
                return
                
            except asyncio.TimeoutError:
                print(f"❌ Pyrogram Client startup timed out (Attempt {attempt+1}/{max_retries})")
            except Exception as e:
                print(f"❌ Failed to start Pyrogram Client (Attempt {attempt+1}/{max_retries}): {e}")
            
            # Wait before retry if not last attempt
            if attempt < max_retries - 1:
                await asyncio.sleep(2)
        
        print("❌ Pyrogram Client failed to start after all retries. Large file uploads will fail.")
    async def stop_bot(self) -> None:
        """Stop the Telegram bot"""
        # Stop Pyrogram client
        if self.pyrogram_client:
            try:
                if self.pyrogram_client.is_connected:
                    await self.pyrogram_client.stop()
                    print("Pyrogram Client stopped")
            except Exception as e:
                print(f"Error stopping Pyrogram Client: {e}")

        if self.application:
            try:
                await self.application.updater.stop()
                await self.application.stop()
                await self.application.shutdown()
                print("🛑 Telegram bot stopped")
            except Exception as e:
                print(f"Error stopping Telegram bot: {e}")

