"""File utility functions"""
import os
import time
from typing import List


def cleanup_old_files(downloads_dir: str, validity_days: int) -> None:
    """Remove files older than validity_days"""
    try:
        current_time = time.time()
        for filename in os.listdir(downloads_dir):
            filepath = os.path.join(downloads_dir, filename)
            if os.path.isfile(filepath):
                file_age_days = (current_time - os.path.getmtime(filepath)) / 86400
                if file_age_days > validity_days:
                    os.remove(filepath)
                    print(f"Removed old file: {filename} (age: {file_age_days:.1f} days)")
    except Exception as e:
        print(f"Error during cleanup: {e}")


def cleanup_all_files(downloads_dir: str) -> None:
    """Remove all files from downloads directory"""
    try:
        for filename in os.listdir(downloads_dir):
            filepath = os.path.join(downloads_dir, filename)
            if os.path.isfile(filepath):
                os.remove(filepath)
        print("All files cleaned up")
    except Exception as e:
        print(f"Error during cleanup: {e}")


def find_files_by_id(downloads_dir: str, file_id: str) -> List[str]:
    """Find files that start with the given file_id"""
    return [f for f in os.listdir(downloads_dir) if f.startswith(file_id)]


