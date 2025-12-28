/** API configuration constants */
export const API_BASE = process.env.REACT_APP_API_BASE || 'http://localhost:8000';

export const API_ENDPOINTS = {
  PLAYLIST_INFO: '/api/playlist-info',
  VIDEO_INFO: '/api/video-info',
  DOWNLOAD: '/api/download',
  PROGRESS: '/api/progress',
  CANCEL: '/api/cancel',
  DOWNLOAD_FILE: '/api/download-file',
  DIRECT_LINK: '/api/direct-link',
  BATCH_DOWNLOAD: '/api/batch-download',
  CREATE_ZIP: '/api/create-zip',
  CLEANUP: '/api/cleanup',
};


