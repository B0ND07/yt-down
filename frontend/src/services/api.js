/** API service layer for making HTTP requests */
import axios from 'axios';
import { API_BASE, API_ENDPOINTS } from '../constants/api';

const api = axios.create({
  baseURL: API_BASE,
});

/**
 * Get playlist information
 * @param {string} url - YouTube playlist URL
 * @returns {Promise} Playlist information
 */
export const getPlaylistInfo = async (url) => {
  const response = await api.post(API_ENDPOINTS.PLAYLIST_INFO, { url });
  return response.data;
};

/**
 * Get video information and available formats
 * @param {string} url - YouTube video URL
 * @returns {Promise} Video information
 */
export const getVideoInfo = async (url) => {
  const response = await api.post(API_ENDPOINTS.VIDEO_INFO, { url });
  return response.data;
};

/**
 * Start a video download
 * @param {string} url - YouTube video URL
 * @param {string} quality - Video quality
 * @param {string} formatId - Format ID
 * @returns {Promise} Download response with file_id
 */
export const startDownload = async (url, quality, formatId) => {
  const response = await api.post(API_ENDPOINTS.DOWNLOAD, {
    url,
    quality,
    format_id: formatId,
  });
  return response.data;
};

/**
 * Get download progress
 * @param {string} fileId - File ID
 * @returns {Promise} Progress information
 */
export const getDownloadProgress = async (fileId) => {
  const response = await api.get(`${API_ENDPOINTS.PROGRESS}/${fileId}`);
  return response.data;
};

/**
 * Cancel a download
 * @param {string} fileId - File ID
 * @returns {Promise} Cancel response
 */
export const cancelDownload = async (fileId) => {
  const response = await api.post(`${API_ENDPOINTS.CANCEL}/${fileId}`);
  return response.data;
};

/**
 * Get Direct stream link
 * @param {string} url - YouTube video URL
 * @param {string} quality - Video quality
 * @param {string} formatId - Format ID
 * @returns {Promise} Direct link response
 */
export const getDirectLink = async (url, quality, formatId) => {
  const response = await api.post(API_ENDPOINTS.DIRECT_LINK, {
    url,
    quality,
    format_id: formatId,
  });
  return response.data;
};

/**
 * Batch download videos
 * @param {Array<string>} urls - Array of YouTube video URLs
 * @param {string} quality - Video quality
 * @param {string} formatId - Format ID
 * @returns {Promise} Batch download response
 */
export const batchDownload = async (urls, quality, formatId) => {
  const response = await api.post(API_ENDPOINTS.BATCH_DOWNLOAD, {
    urls,
    quality,
    format_id: formatId,
  });
  return response.data;
};

/**
 * Create ZIP file from file IDs
 * @param {Array<string>} fileIds - Array of file IDs
 * @returns {Promise} ZIP creation response
 */
export const createZip = async (fileIds) => {
  const response = await api.post(API_ENDPOINTS.CREATE_ZIP, {
    file_ids: fileIds,
  });
  return response.data;
};

/**
 * Get download file URL
 * @param {string} fileId - File ID
 * @returns {string} Download URL
 */
export const getDownloadFileUrl = (fileId) => {
  return `${API_BASE}${API_ENDPOINTS.DOWNLOAD_FILE}/${fileId}`;
};


