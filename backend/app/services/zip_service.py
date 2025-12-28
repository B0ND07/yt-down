"""Service for creating ZIP files"""
import os
import uuid
import zipfile
from typing import List, Dict
from ..config import DOWNLOADS_DIR
from ..utils.file_utils import find_files_by_id


class ZipService:
    """Service for creating ZIP archives"""
    
    def __init__(self):
        self.downloads_dir = DOWNLOADS_DIR
    
    def create_zip(self, file_ids: List[str]) -> Dict:
        """Create a ZIP file from downloaded files"""
        zip_id = str(uuid.uuid4())
        zip_path = os.path.join(self.downloads_dir, f'{zip_id}.zip')
        
        files_added = 0
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_id in file_ids:
                # Find the file with this ID
                files = find_files_by_id(self.downloads_dir, file_id)
                
                if files:
                    filepath = os.path.join(self.downloads_dir, files[0])
                    if os.path.exists(filepath):
                        # Use a cleaner filename in the zip
                        zipf.write(filepath, arcname=files[0])
                        files_added += 1
        
        if files_added == 0:
            # Remove empty zip
            if os.path.exists(zip_path):
                os.remove(zip_path)
            raise ValueError("No files found to zip")
        
        return {
            'success': True,
            'zip_id': zip_id,
            'zip_url': f'/api/download-file/{zip_id}',
            'files_count': files_added
        }
    
    def create_batch_zip(self, downloaded_files: List[Dict]) -> str:
        """Create a ZIP file from a list of downloaded file info"""
        zip_id = str(uuid.uuid4())
        zip_path = os.path.join(self.downloads_dir, f'{zip_id}.zip')
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_info in downloaded_files:
                if os.path.exists(file_info['path']):
                    zipf.write(file_info['path'], arcname=file_info['name'])
        
        return zip_id


